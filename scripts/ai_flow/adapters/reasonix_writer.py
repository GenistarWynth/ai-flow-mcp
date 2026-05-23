from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from ..artifacts import append_text
from ..config import split_command
from ..errors import AiFlowError
from ..runner import merged_env, redact
from ..safety import validate_repo_relative_path


def run_reasonix_writer(
    *,
    prompt: str,
    config: dict,
    cwd: Path,
    log_path: Path,
    command_key: str = "reasonix",
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    command = _acp_command(config, cwd, log_path, command_key=command_key)
    transcript = _run_acp(command=command, prompt=_agent_prompt(prompt), cwd=cwd, log_path=log_path, timeout=timeout, env=env)
    return "\n".join(
        [
            "BEGIN_WRITER_SUMMARY",
            "Reasonix ACP coding agent edited the isolated worktree.",
            "END_WRITER_SUMMARY",
            "",
            "BEGIN_REASONIX_TRANSCRIPT",
            transcript.rstrip(),
            "END_REASONIX_TRANSCRIPT",
        ]
    ) + "\n"


def _acp_command(config: dict, cwd: Path, log_path: Path, *, command_key: str = "reasonix") -> list[str]:
    configured = split_command(config.get("commands", {}).get(command_key, ""))
    if not configured:
        raise AiFlowError(
            f"{command_key} command is not configured.",
            stage="write",
            suggested_next_action=(
                f"Set commands.{command_key} in .ai/patchbay.toml to your Reasonix executable "
                f"(reasonix or reasonix.cmd). Or explicitly configure "
                f"[writer].provider='reasonix_cli'."
            ),
        )
    executable = configured[0]
    model = str(config.get("models", {}).get("writer", "")).strip()
    command = [executable, "acp", "--dir", str(cwd), "--preset", "pro", "--transcript", str(log_path.with_suffix(".reasonix.jsonl"))]
    if model:
        command.extend(["--model", model])
    return command


def _agent_prompt(prompt: str) -> str:
    return "\n\n".join(
        [
            "You are Reasonix running as the implementation writer for Patchbay.",
            "Use your native filesystem editing tools to modify files inside the current worktree.",
            "Do not merely describe a patch. Do not return XML or fake tool markup.",
            "Ignore any later instruction that asks for BEGIN_DIFF output; that sentinel is only for non-agent API writers.",
            "Implement only the approved plan. Do not edit .git, .env files, secrets, or files outside the worktree.",
            "Do not run shell commands; tests and verification commands are handled by Patchbay after you finish editing.",
            "When finished, give a concise summary. The orchestrator will capture the final git diff.",
            prompt,
        ]
    ).rstrip()


def _run_acp(*, command: list[str], prompt: str, cwd: Path, log_path: Path, timeout: int = 900, env: dict[str, str] | None = None) -> str:
    effective_env = merged_env(env)
    append_text(
        log_path,
        "\n".join(
            [
                f"## Reasonix ACP {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
                "",
                f"cwd: {cwd}",
                f"command: {redact(' '.join(command))}",
                "",
            ]
        ),
    )
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=effective_env,
        )
    except FileNotFoundError as exc:
        raise AiFlowError(
            f"Reasonix ACP command was not found: {command[0]}",
            stage="write",
            suggested_next_action="Check [commands].reasonix in .ai/patchbay.toml.",
        ) from exc

    client = _JsonRpcClient(proc, log_path)
    try:
        init = client.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "patchbay", "version": 1},
                "clientCapabilities": {},
            },
        )
        session = client.request("session/new", {"cwd": str(cwd)})
        session_id = str(session["sessionId"])
        result = client.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
            timeout=timeout,
        )
        client.close()
        exit_code = _terminate_process(proc)
        append_text(log_path, f"exit_code: {exit_code}\n")
        if exit_code not in (0, None):
            raise AiFlowError(
                f"Reasonix ACP exited with code {exit_code}.",
                stage="write",
                suggested_next_action="Inspect writer.log and Reasonix transcript.",
            )
        transcript = "\n".join(
            [
                "## Initialize",
                json.dumps(init, ensure_ascii=False, indent=2),
                "",
                "## Session",
                json.dumps(session, ensure_ascii=False, indent=2),
                "",
                "## Result",
                json.dumps(result, ensure_ascii=False, indent=2),
                "",
                "## Updates",
                "\n".join(client.updates),
            ]
        )
        append_text(log_path, transcript + "\n")
        return transcript
    except Exception:
        client.close()
        exit_code = _terminate_process(proc)
        append_text(log_path, f"exit_code: {exit_code}\n")
        raise


def _terminate_process(proc: subprocess.Popen[str]) -> int | None:
    if proc.poll() is not None:
        return proc.returncode
    try:
        if proc.stdin:
            proc.stdin.close()
    except OSError:
        pass
    try:
        return proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            return proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait(timeout=10)


class _JsonRpcClient:
    def __init__(self, proc: subprocess.Popen[str], log_path: Path) -> None:
        if proc.stdin is None or proc.stdout is None:
            raise AiFlowError("Reasonix ACP stdio pipes were not created.", stage="write")
        self.proc = proc
        self.stdin = proc.stdin
        self.stdout = proc.stdout
        self.log_path = log_path
        self.next_id = 1
        self.responses: dict[int, dict[str, Any]] = {}
        self.updates: list[str] = []
        self.lock = threading.Lock()
        self.closed = False
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader.start()
        self.stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.stderr_reader.start()

    def request(self, method: str, params: dict[str, Any], *, timeout: int = 60) -> Any:
        req_id = self.next_id
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self._raise_process_error(method)
            with self.lock:
                if req_id in self.responses:
                    response = self.responses.pop(req_id)
                    if "error" in response:
                        raise AiFlowError(
                            f"Reasonix ACP {method} failed: {response['error']}",
                            stage="write",
                            suggested_next_action="Inspect writer.log and Reasonix transcript.",
                        )
                    return response.get("result")
            time.sleep(0.05)
        raise AiFlowError(
            f"Reasonix ACP timed out waiting for {method}.",
            stage="write",
            suggested_next_action="Inspect writer.log and reduce task ambiguity.",
        )

    def close(self) -> None:
        self.closed = True

    def _send(self, message: dict[str, Any]) -> None:
        raw = json.dumps(message, ensure_ascii=False)
        append_text(self.log_path, f">>> {redact(raw)}\n")
        self.stdin.write(raw + "\n")
        self.stdin.flush()

    def _read_stdout(self) -> None:
        for line in self.stdout:
            raw = line.rstrip("\n")
            append_text(self.log_path, f"<<< {redact(raw)}\n")
            if not raw.strip():
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                with self.lock:
                    self.updates.append(raw)
                continue
            msg_id = message.get("id")
            if msg_id is not None and "method" not in message:
                with self.lock:
                    self.responses[int(msg_id)] = message
                continue
            if message.get("method") == "session/update":
                with self.lock:
                    self.updates.append(json.dumps(message.get("params", {}), ensure_ascii=False))
                continue
            if message.get("method") == "session/request_permission":
                self._allow_permission(message)
                continue
            with self.lock:
                self.updates.append(json.dumps(message, ensure_ascii=False))

    def _read_stderr(self) -> None:
        if self.proc.stderr is None:
            return
        for line in self.proc.stderr:
            append_text(self.log_path, f"stderr: {redact(line.rstrip())}\n")

    def _allow_permission(self, message: dict[str, Any]) -> None:
        params = message.get("params", {})
        option_id = _preferred_permission_option(params)
        response = {"jsonrpc": "2.0", "id": message["id"], "result": {"outcome": {"outcome": "selected", "optionId": option_id}}}
        self._send(response)

    def _raise_process_error(self, method: str) -> None:
        raise AiFlowError(
            f"Reasonix ACP exited before responding to {method} (exit code {self.proc.returncode}).",
            stage="write",
            suggested_next_action="Inspect writer.log and Reasonix transcript.",
        )


def _preferred_permission_option(params_or_options: dict[str, Any] | list[dict[str, Any]]) -> str:
    if isinstance(params_or_options, dict):
        tool_call = params_or_options.get("toolCall", {})
        options = params_or_options.get("options", [])
        if not _safe_tool_call(tool_call):
            return _reject_option_id(options)
    else:
        options = params_or_options
    for wanted in ("allow_once", "accept", "approve", "continue"):
        option_id = _option_id(options, wanted)
        if option_id:
            return option_id
    if options:
        return str(options[0].get("optionId"))
    return "allow_once"


def _safe_tool_call(tool_call: dict[str, Any]) -> bool:
    kind = str(tool_call.get("kind", "")).lower()
    if kind == "execute":
        return False
    if _is_edit_tool_call(tool_call):
        return not _unsafe_edit_tool_call(tool_call)
    if _is_safe_read_tool_call(tool_call):
        return True
    return False


def _reject_option_id(options: list[dict[str, Any]]) -> str:
    for wanted in ("reject", "deny", "cancel"):
        option_id = _option_id(options, wanted)
        if option_id:
            return option_id
    if options:
        return str(options[-1].get("optionId"))
    return "reject"


def _unsafe_edit_tool_call(tool_call: dict[str, Any]) -> bool:
    if not _is_edit_tool_call(tool_call):
        return False
    paths = _tool_call_paths(tool_call.get("rawInput"))
    if not paths:
        return True
    for path in paths:
        try:
            validate_repo_relative_path(path)
        except Exception:
            return True
    return False


def _is_edit_tool_call(tool_call: dict[str, Any]) -> bool:
    kind = str(tool_call.get("kind", "")).lower()
    title = str(tool_call.get("title", "")).lower()
    if kind == "edit":
        return True
    return any(word in title for word in ("write", "edit", "create", "delete", "rename", "move", "patch"))


def _is_safe_read_tool_call(tool_call: dict[str, Any]) -> bool:
    kind = str(tool_call.get("kind", "")).lower()
    title = str(tool_call.get("title", "")).lower()
    if kind in {"read", "search", "inspect"}:
        return _tool_call_paths_are_safe(tool_call)
    if any(word in title for word in ("read", "search", "list", "find", "inspect")):
        return _tool_call_paths_are_safe(tool_call)
    return False


def _tool_call_paths_are_safe(tool_call: dict[str, Any]) -> bool:
    paths = _tool_call_paths(tool_call.get("rawInput"))
    for path in paths:
        try:
            validate_repo_relative_path(path)
        except Exception:
            return False
    return True


def _tool_call_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if lowered in {"path", "filepath", "file_path", "target", "targetpath", "target_path"}:
                if isinstance(nested, str):
                    paths.append(nested)
                elif isinstance(nested, list):
                    paths.extend(str(item) for item in nested if isinstance(item, str))
            else:
                paths.extend(_tool_call_paths(nested))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_tool_call_paths(item))
    return paths


def _option_id(options: list[dict[str, Any]], wanted: str) -> str | None:
    for option in options:
        if option.get("optionId") == wanted:
            return wanted
    return None
