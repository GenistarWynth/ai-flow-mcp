from __future__ import annotations

from typing import Any


ACTION_GROUPS: dict[str, dict[str, str]] = {
    "background_polling": {
        "label": "Background polling",
        "reason": "Read progress from an active background job without advancing any gate.",
    },
    "routing": {
        "label": "Economy routing",
        "reason": "Inspect or repair the low-cost write/fix route.",
    },
    "setup": {
        "label": "Setup and readiness",
        "reason": "Run local setup, Skill, MCP, or readiness follow-ups.",
    },
    "diagnostics": {
        "label": "Diagnostics",
        "reason": "Open run views or diagnostic tabs without changing run state.",
    },
    "gate": {
        "label": "Gated run actions",
        "reason": "Actions that may require explicit plan or apply confirmation.",
    },
    "new_task": {
        "label": "New task",
        "reason": "Focus the composer or start a fresh Patchbay task.",
    },
    "commands": {
        "label": "Copyable commands",
        "reason": "Commands that can be copied or run outside the Agent.",
    },
    "local": {
        "label": "Local Agent",
        "reason": "Safe local Agent follow-ups.",
    },
}

ACTION_GROUP_ORDER = [
    "gate",
    "background_polling",
    "routing",
    "setup",
    "diagnostics",
    "new_task",
    "commands",
    "local",
]


def group_actions(actions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return a compact, stable grouping index for structured Agent actions."""
    grouped: dict[str, dict[str, Any]] = {}
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_id = _action_id(action)
        if not action_id:
            continue
        group_id = _action_group_id(action)
        group = grouped.setdefault(group_id, _new_group(group_id))
        if action_id not in group["action_ids"]:
            group["action_ids"].append(action_id)
            group["count"] = len(group["action_ids"])
    return [grouped[group_id] for group_id in ACTION_GROUP_ORDER if group_id in grouped]


def _new_group(group_id: str) -> dict[str, Any]:
    definition = ACTION_GROUPS.get(group_id, ACTION_GROUPS["local"])
    return {
        "id": group_id,
        "label": definition["label"],
        "reason": definition["reason"],
        "action_ids": [],
        "count": 0,
    }


def _action_id(action: dict[str, Any]) -> str:
    return str(action.get("id") or action.get("name") or action.get("message") or action.get("command") or "").strip()


def _action_group_id(action: dict[str, Any]) -> str:
    action_id = _action_id(action).lower()
    kind = str(action.get("kind") or "").lower()
    message = str(action.get("message") or "").lower()
    command = str(action.get("command") or "").lower()
    tab = str(action.get("tab") or "").lower()
    haystack = " ".join((action_id, kind, message, command, tab))

    if action_id.startswith("poll_"):
        return "background_polling"
    if _has_any(haystack, ("economy", "routing", "route", "reasonix", "deepseek", "cheap_writer", "provider command")):
        return "routing"
    if _has_any(haystack, ("readiness", "doctor", "setup", "install", "skill", "mcp")):
        return "setup"
    if kind in {"open_run", "diagnostic_tab"} or _has_any(haystack, ("trace", "diff", "artifact", "log", "open_", "inspect")):
        return "diagnostics"
    if kind == "focus_composer" or _has_any(haystack, ("start_new_task", "new task", "composer")):
        return "new_task"
    if _has_any(haystack, ("approve", "apply", "continue")):
        return "gate"
    if kind == "command" or command:
        return "commands"
    return "local"


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
