"""Gemini CLI reviewer provider.

Uses ``gemini -p`` as a read-only reviewer. The shared ``cli_reviewer`` module
extracts the required verdict from stdout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cli_reviewer import run_generic_cli_reviewer
from ..artifacts import write_text


def run_gemini_reviewer(
    *,
    prompt: str,
    config: dict[str, Any],
    cwd: Path,
    log_path: Path,
    command_key: str = "gemini",
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    """Run Gemini CLI as the reviewer."""

    model = str(config.get("models", {}).get("reviewer", "gemini-2.5-pro"))
    prompt_file = log_path.parent / f"{command_key}-reviewer.prompt.md"
    write_text(prompt_file, prompt)
    directive = (
        f"Read the review prompt file at {prompt_file} and output your verdict directly to stdout. "
        "The first non-whitespace text must be PASS or CHANGES_REQUESTED, followed by the Markdown review."
    )

    def _build_argv(
        *,
        command: list[str],
        prompt: str,
        model: str,
        output_file: str,
    ) -> list[str]:
        return [
            *command,
            "-p",
            prompt,
            "--model",
            model,
        ]

    return run_generic_cli_reviewer(
        prompt=directive,
        config=config,
        cwd=cwd,
        log_path=log_path,
        command_key=command_key,
        model=model,
        build_argv=_build_argv,
        timeout=timeout,
        env=env,
        expect_output_file=False,
        send_stdin=False,
    )
