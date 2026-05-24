from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .trace import list_trace


ARTIFACT_PURPOSES: dict[str, str] = {
    "TASK.md": "original task",
    "PLAN.md": "approved plan",
    "plan.json": "machine-readable plan",
    "APPROVAL.json": "plan approval",
    "STATUS.json": "run state",
    "BASE_COMMIT": "base commit",
    "WORKTREE_PATH": "isolated worktree path",
    "IMPLEMENTATION.md": "writer summary",
    "FINAL.diff": "candidate patch",
    "TEST.log": "test evidence",
    "REVIEW.md": "review verdict",
    "FIXES.md": "fix history",
    "events.jsonl": "cross-host event log",
    "trace.jsonl": "agent/tool trace log",
    "JOB.json": "background job metadata",
    "RUN.lock": "active phase lock",
    "git.log": "git operation log",
    "writer.log": "writer log",
    "claude-planner.log": "planner log",
    "codex-reviewer.log": "reviewer log",
}

ACTION_TO_TOOL: dict[str, str] = {
    "approve": "patchbay_approve",
    "write": "patchbay_write",
    "test": "patchbay_test",
    "review": "patchbay_review",
    "fix": "patchbay_fix",
    "apply": "patchbay_apply",
    "cleanup": "patchbay_cleanup",
}

HUMAN_CONFIRMATION_ACTIONS = {"approve", "apply"}


def build_handoff_context(
    *,
    run_path: Path,
    status_data: dict[str, Any],
    since_event: int = 0,
    since_trace: int = 0,
    include_trace: bool = False,
) -> dict[str, Any]:
    """Build a read-only handoff digest from run artifacts and status data."""
    events = _event_timeline(run_path, since=since_event)
    traces = _trace_timeline(run_path, since=since_trace) if include_trace else []
    timeline = sorted([*events, *traces], key=_timeline_sort_key)
    provider_trail = _provider_trail(run_path)
    next_actions = annotate_next_actions(status_data)
    return {
        "run_id": status_data.get("run_id", run_path.name),
        "handoff_summary": _handoff_summary(status_data, next_actions),
        "status": status_data.get("status"),
        "current_phase": status_data.get("current_phase"),
        "gate_state": status_data.get("gate_state", {}),
        "next_actions": next_actions,
        "provider_trail": provider_trail,
        "artifacts": describe_artifacts(run_path, status_data.get("artifacts", [])),
        "timeline": timeline,
        "cursors": {
            "event": _raw_line_count(run_path / "events.jsonl"),
            "trace": _raw_line_count(run_path / "trace.jsonl"),
        },
    }


def annotate_next_actions(status_data: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for name in status_data.get("next_commands", []) or []:
        safe = _is_action_safe(name, status_data)
        actions.append(
            {
                "name": name,
                "safe": safe,
                "tool": ACTION_TO_TOOL.get(name, f"patchbay_{name}"),
                "requires_human_confirmation": name in HUMAN_CONFIRMATION_ACTIONS,
                "reason": _action_reason(name, status_data, safe),
            }
        )
    return actions


def describe_artifacts(run_path: Path, artifact_names: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for name in artifact_names:
        items.append(
            {
                "name": name,
                "purpose": _artifact_purpose(name),
                "path": str(run_path / name),
            }
        )
    return items


def _artifact_purpose(name: str) -> str:
    if name in ARTIFACT_PURPOSES:
        return ARTIFACT_PURPOSES[name]
    if name.endswith(".log"):
        return "phase log"
    if name.endswith(".md"):
        return "markdown artifact"
    if name.endswith(".diff"):
        return "patch diff"
    if name.endswith(".json"):
        return "structured artifact"
    if name.endswith(".jsonl"):
        return "append-only stream"
    return "run artifact"


def _is_action_safe(name: str, status_data: dict[str, Any]) -> bool:
    if name == "apply":
        gate = status_data.get("gate_state", {}) or {}
        return bool(
            status_data.get("status") == "REVIEWED_PASS"
            and status_data.get("review_result") == "PASS"
            and status_data.get("tests_passed")
            and gate.get("ready_to_apply")
        )
    return True


def _action_reason(name: str, status_data: dict[str, Any], safe: bool) -> str:
    if name == "approve":
        return "Plan is ready for human approval before implementation."
    if name == "apply":
        if safe:
            return "Tests passed and review returned PASS; human confirmation is still required."
        return "Apply is blocked until tests pass and review returns PASS."
    if name == "fix":
        return "Review requested changes; run the configured fixer before retesting."
    if name == "review":
        return "Tests completed; run read-only review next."
    if name == "test":
        return "Implementation diff is ready; run configured test evidence next."
    if name == "write":
        return "Plan was approved; writer may work inside the isolated worktree."
    if name == "cleanup":
        return "Run is applied; cleanup can remove the isolated worktree."
    return f"Run the {name} phase next."


def _handoff_summary(status_data: dict[str, Any], next_actions: list[dict[str, Any]]) -> str:
    run_id = status_data.get("run_id", "")
    status = status_data.get("status", "UNKNOWN")
    phase = status_data.get("current_phase", "")
    if next_actions:
        next_text = ", ".join(action["name"] for action in next_actions)
    else:
        next_text = "none"
    return f"Run {run_id} is {status} in phase {phase}; next safe action: {next_text}."


def _event_timeline(run_path: Path, *, since: int = 0) -> list[dict[str, Any]]:
    path = run_path / "events.jsonl"
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < since or not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    entries.append(_normalize_event(record, index=index))
    except Exception:
        return []
    return entries


def _trace_timeline(run_path: Path, *, since: int = 0) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in list_trace(run_path, since=since):
        item = {
            "source": "trace",
            "index": record.get("index", 0),
            "timestamp": record.get("timestamp", ""),
            "phase": record.get("phase", ""),
            "action": record.get("action", ""),
            "status": record.get("status", ""),
        }
        for key in ("agent", "tool", "path", "detail", "raw"):
            if key in record:
                item[key] = record[key]
        entries.append(item)
    return entries


def _normalize_event(record: dict[str, Any], *, index: int) -> dict[str, Any]:
    item = {
        "source": "event",
        "index": index,
        "timestamp": record.get("timestamp", ""),
        "phase": record.get("phase", ""),
        "action": record.get("action", ""),
        "status": record.get("status", ""),
    }
    for key in ("run_id", "provider", "model", "detail", "artifact_paths", "duration_ms", "next_action"):
        if key in record:
            item[key] = record[key]
    return item


def _provider_trail(run_path: Path) -> list[dict[str, Any]]:
    trail: list[dict[str, Any]] = []
    for item in _event_timeline(run_path, since=0):
        if not (item.get("provider") or item.get("model")):
            continue
        trail.append(
            {
                "phase": item.get("phase", ""),
                "provider": item.get("provider", ""),
                "model": item.get("model", ""),
                "status": item.get("status", ""),
                "timestamp": item.get("timestamp", ""),
            }
        )
    return trail


def _raw_line_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except Exception:
        return 0


def _timeline_sort_key(item: dict[str, Any]) -> tuple[str, int, int]:
    source_rank = 0 if item.get("source") == "event" else 1
    return (str(item.get("timestamp", "")), source_rank, int(item.get("index") or 0))
