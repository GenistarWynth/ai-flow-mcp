"""Append-only JSONL event log for cross-phase visibility.

Every phase start, success, error, and retry writes a one-line JSON record
to ``.ai/runs/<run_id>/events.jsonl``.  The CLI ``patchbay events <run_id>``
and the MCP tool ``patchbay_events`` surface this log to any host so every
agent/phase can see what others did or are currently doing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import append_text, now_iso

EVENTS_FILE = "events.jsonl"


def events_path(run_dir: Path) -> Path:
    return run_dir / EVENTS_FILE


def append_event(
    run_dir: Path,
    *,
    phase: str,
    provider: str = "",
    model: str = "",
    action: str,
    status: str,
    detail: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Write an event record and return it.

    *phase*    — "plan" | "write" | "test" | "review" | "fix" | "apply" | "approve"
    *action*   — "start" | "success" | "error" | "retry" | "approve_granted" | "apply_granted" | "apply_denied"
    *status*   — short machine-readable tag (e.g. "PASS", "CHANGES_REQUESTED", "ERROR")
    *detail*   — human-readable summary or error message
    """
    record: dict[str, Any] = {
        "timestamp": now_iso(),
        "phase": phase,
        "action": action,
        "status": status,
    }
    if run_id:
        record["run_id"] = run_id
    if provider:
        record["provider"] = provider
    if model:
        record["model"] = model
    if detail:
        record["detail"] = detail
    append_text(events_path(run_dir), json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def list_events(
    run_dir: Path,
    *,
    since: int = 0,
    phase: str | None = None,
) -> list[dict[str, Any]]:
    """Return all events after index *since* (0-indexed), optionally filtered by phase."""
    path = events_path(run_dir)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            if index < since:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if phase and record.get("phase") != phase:
                continue
            events.append(record)
    except Exception:
        return []
    return events


def latest_event(run_dir: Path) -> dict[str, Any] | None:
    """Return the most recent event, or None if no events exist."""
    all_events = list_events(run_dir)
    return all_events[-1] if all_events else None


def event_count(run_dir: Path) -> int:
    """Return the total number of events for this run."""
    path = events_path(run_dir)
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0
