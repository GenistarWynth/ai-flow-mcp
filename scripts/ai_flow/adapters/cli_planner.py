"""Shared CLI planner helpers.

Provider-agnostic functions for building planner prompts, parsing
stream-json output, and extracting plan / error text.  Used by
``claude_planner.py`` and (via the provider registry) by other
CLI-based planner providers (codex_cli, gemini_cli).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..artifacts import append_text, read_text, write_text
from ..config import split_command
from ..errors import AiFlowError
from ..runner import run_logged
from ..usage import metrics_from_text, with_usage

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _prompt_template() -> str:
    return read_text(Path(__file__).resolve().parents[1] / "prompts" / "planner.md")


def build_planner_prompt(task: str, context: str) -> str:
    return "\n\n".join(
        [
            _prompt_template().rstrip(),
            "# User Task",
            task,
            "# Repository Context",
            context,
        ]
    ).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Stream-json parsing (Claude-compatible format)
# ---------------------------------------------------------------------------


def has_plan_json_block(text: str) -> bool:
    """Return True if *text* contains the plan JSON sentinel block."""
    return "BEGIN_AI_FLOW_PLAN_JSON" in text and "END_AI_FLOW_PLAN_JSON" in text


def extract_plain_stdout_plan(output: str) -> str | None:
    """Return the sentinel plan block and following Markdown from plain stdout."""
    begin = output.find("BEGIN_AI_FLOW_PLAN_JSON")
    end = output.find("END_AI_FLOW_PLAN_JSON", begin if begin >= 0 else 0)
    if begin < 0 or end < 0:
        return None
    return output[begin:].strip()


def _message_text(message: dict) -> str:
    """Extract concatenated text from a stream-json message's ``content`` array."""
    parts: list[str] = []
    for item in message.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()


def extract_stream_json_plan(output: str) -> str | None:
    """Walk stream-json lines and return the last assistant text that contains a plan JSON block."""
    best: str | None = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Some hosts put the plan in the result block when using stream-json + --bare.
        if isinstance(event.get("result"), str) and has_plan_json_block(event["result"]):
            best = event["result"].strip()
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        text = _message_text(message)
        if text and has_plan_json_block(text):
            best = text
    return best


def extract_stream_json_error(output: str) -> str | None:
    """Walk stream-json lines and return the last error message."""
    best: str | None = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result" and event.get("is_error") and isinstance(event.get("result"), str):
            best = event["result"].strip()
        if event.get("type") != "assistant" or not event.get("error"):
            continue
        message = event.get("message")
        if isinstance(message, dict):
            text = _message_text(message)
            if text:
                best = text
    return best


def failure_detail(stdout: str, stderr: str) -> str:
    """Return a one-line failure detail from stdout/stderr, preferring stream-json errors."""
    stream_error = extract_stream_json_error(stdout)
    if stream_error:
        return stream_error
    detail = (stdout or stderr or "no error output").strip()
    return detail.splitlines()[0] if detail else "no error output"


def is_retryable_connection_failure(stdout: str, stderr: str) -> bool:
    """Return True if the failure looks like a transient connection issue."""
    detail = failure_detail(stdout, stderr)
    return "ConnectionRefused" in detail or "Unable to connect to API" in detail


# ---------------------------------------------------------------------------
# Generic CLI planner runner — used by non-Claude provider modules
# ---------------------------------------------------------------------------


def run_generic_cli_planner(
    *,
    task: str,
    context: str,
    config: dict[str, Any],
    cwd: Path,
    log_path: Path,
    command_key: str,
    build_argv: Callable[..., list[str]],
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    """Run a CLI-based planner using a provider-specific *build_argv* callback.

    Writes the full planner prompt to a file, then invokes the CLI with a short
    instruction to read that file and return a plan.  Parses stdout for the
    ``BEGIN_AI_FLOW_PLAN_JSON`` / ``END_AI_FLOW_PLAN_JSON`` sentinel block.
    """
    command = split_command(config.get("commands", {}).get(command_key, command_key))
    if not command:
        raise AiFlowError(
            f"{command_key} command is not configured (commands.{command_key} is empty).",
            stage="plan",
        )
    model = str(config.get("models", {}).get("planner", ""))
    prompt = build_planner_prompt(task, context)
    prompt_file = log_path.parent / f"{command_key}-planner.prompt.md"
    write_text(prompt_file, prompt)

    short_prompt = (
        f"Read the planner prompt file at {prompt_file} and answer in stdout "
        "using the exact BEGIN_AI_FLOW_PLAN_JSON / END_AI_FLOW_PLAN_JSON sentinel format "
        "followed by Markdown. Keep the plan concise: schema-complete JSON plus Markdown "
        "under 80 lines. Do not modify repository files."
    )

    argv = build_argv(command=command, prompt=short_prompt, model=model)
    result = run_logged(argv, cwd=cwd, log_path=log_path, timeout=timeout, env=env)
    usage_metrics = metrics_from_text(result.stdout)

    # Try stream-json recovery first (some CLI tools support it)
    stream_text = extract_stream_json_plan(result.stdout)
    if stream_text:
        append_text(log_path, "\nRecovered planner output from stream-json assistant event.\n")
        return with_usage(stream_text, usage_metrics)
    plain_text = extract_plain_stdout_plan(result.stdout)
    if plain_text:
        return with_usage(plain_text, usage_metrics)

    if not result.ok:
        detail = failure_detail(result.stdout, result.stderr)
        raise AiFlowError(
            f"Planner ({command_key}) failed with exit code {result.exit_code}: {detail}",
            stage="plan",
            suggested_next_action=f"Check {command_key} CLI login/configuration or rerun with --mock.",
        )

    if not result.stdout.strip():
        raise AiFlowError(
            f"Planner ({command_key}) produced empty output.",
            stage="plan",
        )

    return with_usage(result.stdout, usage_metrics)
