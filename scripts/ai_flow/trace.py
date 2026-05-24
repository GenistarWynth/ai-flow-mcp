"""Structured trace stream for agent/tool activity.

Trace records live beside ``events.jsonl`` as ``trace.jsonl``. Events remain
the coarse cross-phase status log; trace is the lower-level stream for ACP
messages, stdout/stderr snippets, tool permissions, and redacted raw payloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import append_text, now_iso
from .runner import redact

TRACE_FILE = "trace.jsonl"
SECRET_KEY_MARKERS = ("key", "token", "secret", "password", "credential", "authorization", "cookie")
REDACTED_TEXT_KEYS = {"prompt"}
TRUNCATED_TEXT_KEYS = {"content", "diff", "log", "message", "patch", "stderr", "stdout", "text"}
MAX_RAW_TEXT_LENGTH = 500


def trace_path(run_dir: Path) -> Path:
    return run_dir / TRACE_FILE


def append_trace(
    run_dir: Path,
    *,
    phase: str,
    agent: str = "",
    action: str,
    tool: str = "",
    path: str = "",
    status: str = "",
    detail: str = "",
    raw: Any | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "timestamp": now_iso(),
        "phase": phase,
        "action": action,
    }
    if agent:
        record["agent"] = agent
    if tool:
        record["tool"] = tool
    if path:
        record["path"] = path
    if status:
        record["status"] = status
    if detail:
        record["detail"] = redact(str(detail), env=env)
    if raw is not None:
        record["raw"] = _redact_payload(raw, env=env)
    append_text(trace_path(run_dir), json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def list_trace(run_dir: Path, *, since: int = 0, phase: str | None = None) -> list[dict[str, Any]]:
    path = trace_path(run_dir)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
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
                if isinstance(record, dict):
                    record = dict(record)
                    record["index"] = index
                    entries.append(record)
    except Exception:
        return []
    return entries


def trace_count(run_dir: Path) -> int:
    path = trace_path(run_dir)
    if not path.exists():
        return 0
    try:
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    count += 1
        return count
    except Exception:
        return 0


def _redact_payload(value: Any, *, env: dict[str, str] | None = None) -> Any:
    secret_values: list[str] = []

    def sanitize(item: Any, key: str = "") -> Any:
        normalized_key = key.lower()
        if isinstance(item, dict):
            return {str(nested_key): sanitize(nested_value, str(nested_key)) for nested_key, nested_value in item.items()}
        if isinstance(item, list):
            return [sanitize(nested, key) for nested in item]
        if isinstance(item, str):
            if any(marker in normalized_key for marker in SECRET_KEY_MARKERS):
                if len(item) >= 6:
                    secret_values.append(item)
                return "***REDACTED***"
            if normalized_key in REDACTED_TEXT_KEYS:
                return f"***REDACTED:{normalized_key}:{len(item)} chars***"
            if normalized_key in TRUNCATED_TEXT_KEYS or len(item) > MAX_RAW_TEXT_LENGTH:
                return _truncate_raw_text(item)
        return item

    sanitized = sanitize(value)
    raw = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, default=str)
    redacted = redact(raw, env=env, extra_values=secret_values)
    try:
        return json.loads(redacted)
    except json.JSONDecodeError:
        return redacted


def _truncate_raw_text(value: str) -> str:
    if len(value) <= MAX_RAW_TEXT_LENGTH:
        return value
    return f"{value[:MAX_RAW_TEXT_LENGTH]}... [truncated {len(value) - MAX_RAW_TEXT_LENGTH} chars]"
