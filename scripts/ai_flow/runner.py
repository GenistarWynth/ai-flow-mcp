from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .artifacts import append_text, now_iso


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _sensitive_values(
    env: dict[str, str] | None = None,
    extra_values: Iterable[str] | None = None,
) -> list[str]:
    source = dict(os.environ)
    if env:
        source.update(env)
    values: list[str] = []
    needles = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    for name, value in source.items():
        if any(needle in name.upper() for needle in needles) and len(value) >= 6:
            values.append(value)
    if extra_values:
        values.extend(value for value in extra_values if len(value) >= 6)
    return values


def redact(
    text: str,
    env: dict[str, str] | None = None,
    extra_values: Iterable[str] | None = None,
) -> str:
    result = text
    for value in _sensitive_values(env, extra_values):
        result = result.replace(value, "***REDACTED***")
    return result


def format_command(command: str | Iterable[str]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(str(part) for part in command)


def merged_env(env: dict[str, str] | None = None) -> dict[str, str] | None:
    if env is None:
        return None
    result = dict(os.environ)
    result.update({str(key): str(value) for key, value in env.items()})
    return result


def run_logged(
    command: str | list[str],
    *,
    cwd: Path,
    log_path: Path,
    input_text: str | None = None,
    shell: bool = False,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    command_text = format_command(command)
    effective_env = merged_env(env)
    append_text(
        log_path,
        "\n".join(
            [
                f"## Command {now_iso()}",
                "",
                f"cwd: {cwd}",
                f"command: {redact(command_text, effective_env)}",
                "",
            ]
        ),
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=shell,
            timeout=timeout,
            env=effective_env,
            check=False,
        )
        result = CommandResult(
            command=command_text,
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        result = CommandResult(
            command=command_text,
            exit_code=124,
            stdout=stdout,
            stderr=(stderr + f"\nTimed out after {timeout} seconds.").strip(),
        )
    except FileNotFoundError as exc:
        result = CommandResult(command=command_text, exit_code=127, stdout="", stderr=str(exc))

    append_text(
        log_path,
        "\n".join(
            [
                f"exit_code: {result.exit_code}",
                "",
                "### stdout",
                "",
                redact(result.stdout, effective_env).rstrip(),
                "",
                "### stderr",
                "",
                redact(result.stderr, effective_env).rstrip(),
                "",
            ]
        ),
    )
    return result
