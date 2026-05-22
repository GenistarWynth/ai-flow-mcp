"""Claude Code reviewer provider.

Uses ``claude -p --output-format stream-json`` with plan permission mode as a
read-only reviewer. The shared ``cli_reviewer`` module extracts the required
verdict from stdout / stream-json output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cli_reviewer import run_generic_cli_reviewer
from ..artifacts import write_text


def run_claude_reviewer(
    *,
    prompt: str,
    config: dict[str, Any],
    cwd: Path,
    log_path: Path,
    command_key: str = "claude",
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    """Run Claude Code CLI as the reviewer."""

    model = str(config.get("models", {}).get("reviewer", "claude-opus-4-7"))
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
            "--permission-mode",
            "plan",
            "--bare",
            "--output-format",
            "stream-json",
            "--verbose",
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
