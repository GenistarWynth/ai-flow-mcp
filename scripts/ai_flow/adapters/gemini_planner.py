"""Gemini CLI planner provider.

Uses ``gemini -p`` with the planner prompt inline.  The shared ``cli_planner``
module handles prompt construction and output parsing.

Note: the ``gemini`` CLI does not support stream-json, so the generic planner
falls back to plain stdout capture and sentinel-block extraction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cli_planner import run_generic_cli_planner


def run_gemini_planner(
    *,
    task: str,
    context: str,
    config: dict[str, Any],
    cwd: Path,
    log_path: Path,
    command_key: str = "gemini",
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    """Run Gemini CLI as the planner."""

    def _build_argv(*, command: list[str], prompt: str, model: str) -> list[str]:
        return [
            *command,
            "-p",
            prompt,
            "--model",
            model,
        ]

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
