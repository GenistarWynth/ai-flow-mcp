from __future__ import annotations

import json
import re
from pathlib import Path

from ..artifacts import append_text, read_text, write_text
from ..config import split_command
from ..errors import AiFlowError
from ..plan_schema import empty_plan
from ..runner import run_logged


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


def run_mock_planner(task: str, context: str) -> str:
    plan = empty_plan(task)
    return "\n".join(
        [
            "BEGIN_AI_FLOW_PLAN_JSON",
            json.dumps(plan, ensure_ascii=False, indent=2),
            "END_AI_FLOW_PLAN_JSON",
            "",
            "# Mock Implementation Plan",
            "",
            f"Task: {task}",
            "",
            "1. Create `AI_FLOW_MOCK_OUTPUT.md` in the isolated worktree.",
            "2. Write the task text and a deterministic marker.",
            "3. Review the resulting diff and pass in mock mode.",
        ]
    ) + "\n"


def run_claude_planner(
    *,
    task: str,
    context: str,
    config: dict,
    cwd: Path,
    log_path: Path,
) -> str:
    command = split_command(config.get("commands", {}).get("claude", "claude"))
    if not command:
        raise AiFlowError("Claude command is not configured.", stage="plan")
    model = str(config.get("models", {}).get("planner", "claude-opus-4-7"))
    prompt = build_planner_prompt(task, context)
    prompt_file = log_path.parent / "claude-planner.prompt.md"
    write_text(prompt_file, prompt)
    short_prompt = (
        f"Read the planner prompt file at {prompt_file} and answer in stdout "
        "using the exact BEGIN_AI_FLOW_PLAN_JSON / END_AI_FLOW_PLAN_JSON sentinel format followed by Markdown. "
        "Keep the plan concise: schema-complete JSON plus Markdown under 80 lines. "
        "Do not modify repository files."
    )
    plans_dir = Path.home() / ".claude" / "plans"
    before = _latest_plan_mtime(plans_dir)
    transcript_dirs = _claude_project_dirs(cwd)
    transcript_before = _latest_transcript_mtime(transcript_dirs)
    result = None
    stream_text = None
    max_invocations = int(config.get("planner", {}).get("max_invocations", 1))
    for invocation in range(max(1, max_invocations)):
        if invocation:
            append_text(log_path, f"\nRetrying Claude planner invocation {invocation + 1}/{max_invocations}.\n")
        result = run_logged(
            _claude_print_command(command, short_prompt, model),
            cwd=cwd,
            log_path=log_path,
            timeout=900,
        )
        stream_text = _extract_stream_json_plan(result.stdout)
        if stream_text or result.ok or not _is_retryable_connection_failure(result.stdout, result.stderr):
            break
    assert result is not None
    if stream_text:
        append_text(log_path, "\nRecovered planner output from Claude stream-json assistant event.\n")
        return stream_text
    if not result.ok:
        transcript_text = _read_newest_transcript_plan(
            transcript_dirs,
            after=transcript_before,
            prompt_marker=str(prompt_file),
        )
        if transcript_text:
            append_text(log_path, "\nRecovered planner output from Claude transcript.\n")
            return transcript_text
        detail = _failure_detail(result.stdout, result.stderr)
        suggested = "Check Claude Code login/configuration or rerun with --mock."
        if "ConnectionRefused" in detail or "Unable to connect to API" in detail:
            suggested = (
                "The Claude API endpoint refused the connection. Check the configured Anthropic-compatible "
                "base URL/upstream logs, then rerun the plan stage."
            )
        raise AiFlowError(
            f"Claude planner failed with exit code {result.exit_code}: {detail}",
            stage="plan",
            suggested_next_action=suggested,
        )
    if not _has_plan_json_block(result.stdout):
        plan_text = _read_newest_plan(plans_dir, after=before)
        if not plan_text:
            plan_text = _read_latest_plan(plans_dir)
        if plan_text:
            return plan_text
        transcript_text = _read_newest_transcript_plan(
            transcript_dirs,
            after=transcript_before,
            prompt_marker=str(prompt_file),
        )
        if transcript_text:
            append_text(log_path, "\nRecovered planner output from Claude transcript.\n")
            return transcript_text
    if not result.stdout.strip():
        raise AiFlowError("Claude planner produced empty output.", stage="plan")
    return result.stdout


def _claude_print_command(command: list[str], prompt: str, model: str) -> list[str]:
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


def _failure_detail(stdout: str, stderr: str) -> str:
    stream_error = _extract_stream_json_error(stdout)
    if stream_error:
        return stream_error
    detail = (stdout or stderr or "no error output").strip()
    return detail.splitlines()[0] if detail else "no error output"


def _is_retryable_connection_failure(stdout: str, stderr: str) -> bool:
    detail = _failure_detail(stdout, stderr)
    return "ConnectionRefused" in detail or "Unable to connect to API" in detail


def _extract_stream_json_plan(output: str) -> str | None:
    best: str | None = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event.get("result"), str) and _has_plan_json_block(event["result"]):
            best = event["result"].strip()
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        text = _message_text(message)
        if text and _has_plan_json_block(text):
            best = text
    return best


def _extract_stream_json_error(output: str) -> str | None:
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


def _claude_project_dirs(cwd: Path) -> list[Path]:
    projects = Path.home() / ".claude" / "projects"
    if not projects.exists():
        return []
    normalized = str(cwd.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")
    exact = projects / normalized
    return [exact] if exact.exists() and exact.is_dir() else []


def _latest_transcript_mtime(dirs: list[Path]) -> float:
    mtimes: list[float] = []
    for directory in dirs:
        mtimes.extend(path.stat().st_mtime for path in directory.glob("*.jsonl") if path.is_file())
    return max(mtimes, default=0.0)


def _read_newest_transcript_plan(dirs: list[Path], *, after: float, prompt_marker: str) -> str | None:
    candidates: list[Path] = []
    for directory in dirs:
        candidates.extend(path for path in directory.glob("*.jsonl") if path.is_file() and path.stat().st_mtime > after)
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        text = _read_transcript_plan(path, prompt_marker=prompt_marker)
        if text:
            return text
    return None


def _read_transcript_plan(path: Path, *, prompt_marker: str) -> str | None:
    best: str | None = None
    saw_current_prompt = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "user" and prompt_marker in json.dumps(event.get("message", {}), ensure_ascii=False):
            saw_current_prompt = True
            continue
        if not saw_current_prompt:
            continue
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        text = _message_text(message)
        if text and _has_plan_json_block(text):
            best = text
    return best


def _message_text(message: dict) -> str:
    parts: list[str] = []
    for item in message.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()


def _has_plan_json_block(text: str) -> bool:
    return bool(
        re.search(
            r"(?m)^BEGIN_AI_FLOW_PLAN_JSON\s*$.*?^END_AI_FLOW_PLAN_JSON\s*$",
            text,
            flags=re.DOTALL | re.MULTILINE,
        )
    )


def _latest_plan_mtime(plans_dir: Path) -> float:
    if not plans_dir.exists():
        return 0.0
    mtimes = [path.stat().st_mtime for path in plans_dir.glob("*.md") if path.is_file()]
    return max(mtimes, default=0.0)


def _read_newest_plan(plans_dir: Path, *, after: float) -> str | None:
    if not plans_dir.exists():
        return None
    candidates = [path for path in plans_dir.glob("*.md") if path.is_file() and path.stat().st_mtime >= after]
    if not candidates:
        return None
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return newest.read_text(encoding="utf-8", errors="replace")


def _read_latest_plan(plans_dir: Path) -> str | None:
    if not plans_dir.exists():
        return None
    candidates = [path for path in plans_dir.glob("*.md") if path.is_file()]
    if not candidates:
        return None
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return newest.read_text(encoding="utf-8", errors="replace")
