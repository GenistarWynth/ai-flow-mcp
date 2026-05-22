"""Codex CLI planner provider.

Uses ``codex exec --sandbox read-only`` with the planner prompt on stdin.
The shared ``cli_planner`` module handles prompt construction and output parsing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cli_planner import run_generic_cli_planner


def _codex_exec_command(command: list[str], prompt: str, model: str) -> list[str]:
    return [
        *command,
        "exec",
        "-c",
        "model_reasoning_effort=high",
        "--sandbox",
        "read-only",
        "--model",
        model,
        prompt,
    ]


def run_codex_planner(
    *,
    task: str,
    context: str,
    config: dict[str, Any],
    cwd: Path,
    log_path: Path,
    command_key: str = "codex",
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    """Run Codex CLI as the planner."""

    def _build_argv(*, command: list[str], prompt: str, model: str) -> list[str]:
        return _codex_exec_command(command, prompt, model)

    return run_generic_cli_planner(
        task=task,
        context=context,
        config=config,
        cwd=cwd,
        log_path=log_path,
        command_key=command_key,
        build_argv=_build_argv,
        timeout=timeout,
        env=env,
    )
