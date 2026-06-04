"""Codex CLI reviewer provider.

Uses ``codex exec --output-last-message`` with a read-only sandbox.  The
subprocess lifecycle and verdict-file polling are handled by the shared
``cli_reviewer`` module.
"""

from __future__ import annotations

from pathlib import Path

from .cli_reviewer import (
    extract_reviewer_output,
    read_verdict_file,
    run_cli_until_verdict,
)
from ..artifacts import read_text
from ..config import split_command
from ..errors import AiFlowError
from ..usage import metrics_from_text, with_usage


# ---------------------------------------------------------------------------
# Public entry points (also referenced by the provider registry)
# ---------------------------------------------------------------------------


def run_mock_reviewer(*, prompt: str, **kwargs: object) -> str:
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
    command_key: str = "codex",
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    command = split_command(config.get("commands", {}).get(command_key, command_key))
    if not command:
        raise AiFlowError(f"{command_key} command is not configured.", stage="review")
    model = str(config.get("models", {}).get("reviewer", "gpt-5.5"))
    output_file = log_path.parent / f"{command_key}-reviewer.output.md"
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
    result = run_cli_until_verdict(
        argv,
        cwd=cwd,
        log_path=log_path,
        input_text=prompt,
        output_file=output_file,
        timeout=timeout,
        env=env,
        trust_early_output_file=True,
    )
    usage_metrics = metrics_from_text(result.stdout)
    if output_file.exists():
        output = extract_reviewer_output(read_text(output_file))
        if output:
            return with_usage(output, usage_metrics)
    if result.returncode != 0:
        raise AiFlowError(
            f"Reviewer ({command_key}) failed with exit code {result.returncode}.",
            stage="review",
            suggested_next_action=f"Check {command_key} CLI login/configuration or rerun with --mock.",
        )
    if not result.stdout.strip():
        raise AiFlowError(f"Reviewer ({command_key}) produced empty output.", stage="review")
    output = extract_reviewer_output(result.stdout)
    if output:
        return with_usage(output, usage_metrics)
    raise AiFlowError(
        f"Reviewer ({command_key}) output did not start with PASS or CHANGES_REQUESTED.",
        stage="review",
        suggested_next_action=f"Adjust the {command_key} reviewer prompt or rerun with --mock.",
    )


# ---------------------------------------------------------------------------
# Backward-compatible re-exports from cli_reviewer
# ---------------------------------------------------------------------------

_read_verdict_file = read_verdict_file
