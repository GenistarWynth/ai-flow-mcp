"""Shared CLI reviewer helpers.

Provider-agnostic subprocess lifecycle and verdict-file polling used by
``codex_reviewer.py`` and (via the provider registry) by other CLI-based
reviewer providers (claude_cli, gemini_cli).
"""

from __future__ import annotations

import os
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..artifacts import append_text, now_iso, read_text
from ..config import split_command
from ..errors import AiFlowError
from ..runner import format_command, merged_env, redact


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def read_verdict_file(path: Path) -> str:
    """Return the verdict text if *path* contains a complete verdict, else ``""``."""
    if not path.exists():
        return ""
    text = read_text(path).strip()
    if text.startswith("PASS") or text.startswith("CHANGES_REQUESTED"):
        return text
    return ""


def _message_text(message: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in message.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()


def extract_reviewer_output(output: str) -> str:
    """Extract a PASS / CHANGES_REQUESTED verdict from plain stdout or stream-json."""
    stripped = output.strip()
    if stripped.startswith("PASS") or stripped.startswith("CHANGES_REQUESTED"):
        return stripped

    best = ""
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event.get("result"), str):
            result = event["result"].strip()
            if result.startswith("PASS") or result.startswith("CHANGES_REQUESTED"):
                best = result
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        text = _message_text(message)
        if text.startswith("PASS") or text.startswith("CHANGES_REQUESTED"):
            best = text
    return best


def run_cli_until_verdict(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    input_text: str,
    output_file: Path | None,
    timeout: int = 900,
    env: dict[str, str] | None = None,
    send_stdin: bool = True,
    trust_early_output_file: bool = False,
) -> _CliResult:
    """Spawn *command*, feed *input_text* on stdin, and poll *output_file* for a verdict.

    Returns as soon as a complete verdict file is detected (stopping the subprocess
    early) or the process exits naturally.
    """
    effective_env = merged_env(env)
    append_text(
        log_path,
        "\n".join(
            [
                f"## Command {now_iso()}",
                "",
                f"cwd: {cwd}",
                f"command: {redact(format_command(command), effective_env)}",
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
            env=effective_env,
        )
    except FileNotFoundError as exc:
        result = _CliResult(returncode=127, stdout="", stderr=str(exc))
        _append_result(log_path, result, env=effective_env)
        return result

    if send_stdin and proc.stdin is not None:
        proc.stdin.write(input_text)
        proc.stdin.close()
    elif proc.stdin is not None:
        proc.stdin.close()

    stdout: list[str] = []
    stderr: list[str] = []
    stdout_thread = threading.Thread(target=_read_pipe, args=(proc.stdout, stdout), daemon=True)
    stderr_thread = threading.Thread(target=_read_pipe, args=(proc.stderr, stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    deadline = time.time() + timeout
    saw_verdict_file = False
    while time.time() < deadline:
        if output_file is not None and not saw_verdict_file and read_verdict_file(output_file):
            if trust_early_output_file:
                append_text(log_path, "\nReviewer verdict file is complete; stopping trusted CLI process.\n")
                _terminate_process_tree(proc)
                _join_threads(stdout_thread, stderr_thread)
                result = _CliResult(
                    returncode=0,
                    stdout="".join(stdout),
                    stderr="".join(stderr),
                )
                _append_result(log_path, result, env=effective_env)
                return result
            append_text(log_path, "\nReviewer verdict file is complete; waiting for CLI process to exit.\n")
            saw_verdict_file = True
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    if proc.poll() is None:
        exit_code = _terminate_process_tree(proc)
        _join_threads(stdout_thread, stderr_thread)
        stderr.append(f"\nTimed out after {timeout} seconds.")
        result = _CliResult(
            returncode=exit_code if exit_code is not None else 124,
            stdout="".join(stdout),
            stderr="".join(stderr),
        )
        _append_result(log_path, result, env=effective_env)
        return result

    exit_code = proc.returncode
    _join_threads(stdout_thread, stderr_thread)
    if proc.stdout is not None:
        proc.stdout.close()
    if proc.stderr is not None:
        proc.stderr.close()
    result = _CliResult(returncode=exit_code, stdout="".join(stdout), stderr="".join(stderr))
    _append_result(log_path, result, env=effective_env)
    return result


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class _CliResult:
    """Thin wrapper over subprocess outcome."""

    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_pipe(pipe: object, bucket: list[str]) -> None:
    if pipe is None:
        return
    for line in pipe:
        bucket.append(line)


def _join_threads(*threads: threading.Thread) -> None:
    for thread in threads:
        thread.join(timeout=2)


def _terminate_process_tree(proc: subprocess.Popen[str]) -> int | None:
    if proc.poll() is not None:
        return proc.returncode
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    else:
        proc.terminate()
    try:
        return proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait(timeout=10)


def _append_result(log_path: Path, result: _CliResult, *, env: dict[str, str] | None = None) -> None:
    append_text(
        log_path,
        "\n".join(
            [
                f"exit_code: {result.returncode}",
                "",
                "### stdout",
                "",
                redact(result.stdout, env).rstrip(),
                "",
                "### stderr",
                "",
                redact(result.stderr, env).rstrip(),
                "",
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Generic CLI reviewer runner — used by non-Codex provider modules
# ---------------------------------------------------------------------------


def run_generic_cli_reviewer(
    *,
    prompt: str,
    config: dict[str, Any],
    cwd: Path,
    log_path: Path,
    command_key: str,
    model: str,
    build_argv: Callable[..., list[str]],
    timeout: int = 900,
    env: dict[str, str] | None = None,
    expect_output_file: bool = True,
    send_stdin: bool = True,
    trust_early_output_file: bool = False,
) -> str:
    """Run a CLI-based reviewer using a provider-specific *build_argv* callback.

    Resolves the CLI command from ``config.commands.<command_key>``, builds the
    argument list via *build_argv*, then delegates to ``run_cli_until_verdict``
    for subprocess lifecycle and verdict-file polling.
    """
    command = split_command(config.get("commands", {}).get(command_key, command_key))
    if not command:
        raise AiFlowError(
            f"{command_key} command is not configured (commands.{command_key} is empty).",
            stage="review",
        )
    output_file = log_path.parent / f"{command_key}-reviewer.output.md"
    argv = build_argv(command=command, prompt=prompt, model=model, output_file=str(output_file))
    result = run_cli_until_verdict(
        argv,
        cwd=cwd,
        log_path=log_path,
        input_text=prompt,
        output_file=output_file if expect_output_file else None,
        timeout=timeout,
        env=env,
        send_stdin=send_stdin,
        trust_early_output_file=trust_early_output_file,
    )
    if result.returncode != 0:
        raise AiFlowError(
            f"Reviewer ({command_key}) failed with exit code {result.returncode}.",
            stage="review",
            suggested_next_action=f"Check {command_key} CLI login/configuration or rerun with --mock.",
        )
    if expect_output_file and output_file.exists():
        output = extract_reviewer_output(read_text(output_file))
        if output:
            return output
    extracted = extract_reviewer_output(result.stdout)
    if extracted:
        return extracted
    if not result.stdout.strip():
        raise AiFlowError(
            f"Reviewer ({command_key}) produced empty output.",
            stage="review",
        )
    raise AiFlowError(
        f"Reviewer ({command_key}) output did not start with PASS or CHANGES_REQUESTED.",
        stage="review",
        suggested_next_action=f"Adjust the {command_key} reviewer prompt or rerun with --mock.",
    )
