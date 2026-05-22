from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

from ..artifacts import append_text, now_iso, read_text
from ..config import split_command
from ..errors import AiFlowError
from ..runner import format_command, redact


def run_mock_reviewer(*, prompt: str) -> str:
    if "AI_FLOW_FORCE_CHANGES_REQUESTED" in prompt:
        return "\n".join(
            [
                "CHANGES_REQUESTED",
                "",
                "Blocking Issues:",
                "1. Mock reviewer was asked to request changes.",
                "",
                "Non-blocking Suggestions:",
                "1. None.",
                "",
                "Required Fixes:",
                "1. Remove the AI_FLOW_FORCE_CHANGES_REQUESTED marker.",
            ]
        ) + "\n"
    return "\n".join(
        [
            "PASS",
            "",
            "Summary:",
            "Mock review passed. No external Codex invocation was used.",
        ]
    ) + "\n"


def run_codex_reviewer(
    *,
    prompt: str,
    config: dict,
    cwd: Path,
    log_path: Path,
) -> str:
    command = split_command(config.get("commands", {}).get("codex", "codex"))
    if not command:
        raise AiFlowError("Codex command is not configured.", stage="review")
    model = str(config.get("models", {}).get("reviewer", "gpt-5.5"))
    output_file = log_path.parent / "codex-reviewer.output.md"
    argv = [
        *command,
        "exec",
        "-c",
        "model_reasoning_effort=high",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_file),
        "--model",
        model,
        "-",
    ]
    result = _run_codex_until_verdict(argv, cwd=cwd, log_path=log_path, input_text=prompt, output_file=output_file)
    if output_file.exists():
        output = read_text(output_file).strip()
        if output:
            return output
    if not result.ok:
        raise AiFlowError(
            f"Codex reviewer failed with exit code {result.exit_code}.",
            stage="review",
            suggested_next_action="Check Codex CLI login/configuration or rerun with --mock.",
        )
    if not result.stdout.strip():
        raise AiFlowError("Codex reviewer produced empty output.", stage="review")
    return result.stdout


def _run_codex_until_verdict(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    input_text: str,
    output_file: Path,
    timeout: int = 900,
) -> _CodexResult:
    append_text(
        log_path,
        "\n".join(
            [
                f"## Command {now_iso()}",
                "",
                f"cwd: {cwd}",
                f"command: {redact(format_command(command))}",
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
        )
    except FileNotFoundError as exc:
        result = _CodexResult(exit_code=127, stdout="", stderr=str(exc))
        _append_codex_result(log_path, result)
        return result

    if proc.stdin is not None:
        proc.stdin.write(input_text)
        proc.stdin.close()

    stdout: list[str] = []
    stderr: list[str] = []
    stdout_thread = threading.Thread(target=_read_pipe, args=(proc.stdout, stdout), daemon=True)
    stderr_thread = threading.Thread(target=_read_pipe, args=(proc.stderr, stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    deadline = time.time() + timeout
    early_verdict = ""
    while time.time() < deadline:
        early_verdict = _read_verdict_file(output_file)
        if early_verdict:
            append_text(log_path, "\nReviewer verdict file is complete; stopping Codex CLI process.\n")
            exit_code = _terminate_process_tree(proc)
            _join_threads(stdout_thread, stderr_thread)
            result = _CodexResult(exit_code=exit_code if exit_code is not None else 0, stdout="".join(stdout), stderr="".join(stderr))
            _append_codex_result(log_path, result)
            return result
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    if proc.poll() is None:
        exit_code = _terminate_process_tree(proc)
        _join_threads(stdout_thread, stderr_thread)
        early_verdict = _read_verdict_file(output_file)
        stderr.append(f"\nTimed out after {timeout} seconds.")
        result = _CodexResult(exit_code=exit_code if exit_code is not None else 124, stdout="".join(stdout), stderr="".join(stderr))
        _append_codex_result(log_path, result)
        return result

    exit_code = proc.returncode
    _join_threads(stdout_thread, stderr_thread)
    result = _CodexResult(exit_code=exit_code, stdout="".join(stdout), stderr="".join(stderr))
    _append_codex_result(log_path, result)
    return result


class _CodexResult:
    def __init__(self, *, exit_code: int, stdout: str, stderr: str) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _read_pipe(pipe: object, bucket: list[str]) -> None:
    if pipe is None:
        return
    for line in pipe:
        bucket.append(line)


def _join_threads(*threads: threading.Thread) -> None:
    for thread in threads:
        thread.join(timeout=2)


def _read_verdict_file(path: Path) -> str:
    if not path.exists():
        return ""
    text = read_text(path).strip()
    if text.startswith("PASS") or text.startswith("CHANGES_REQUESTED"):
        return text
    return ""


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


def _append_codex_result(log_path: Path, result: _CodexResult) -> None:
    append_text(
        log_path,
        "\n".join(
            [
                f"exit_code: {result.exit_code}",
                "",
                "### stdout",
                "",
                redact(result.stdout).rstrip(),
                "",
                "### stderr",
                "",
                redact(result.stderr).rstrip(),
                "",
            ]
        ),
    )
