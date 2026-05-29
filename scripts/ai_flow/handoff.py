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

PHASE_LABELS: dict[str, str] = {
    "plan": "规划",
    "approve": "批准",
    "write": "实现",
    "test": "测试",
    "review": "审查",
    "fix": "修复",
    "apply": "应用",
    "cleanup": "清理",
    "error": "错误",
}

ACTION_LABELS: dict[str, str] = {
    "approve": "批准计划",
    "write": "开始实现",
    "test": "运行测试",
    "review": "开始审查",
    "fix": "执行修复",
    "apply": "应用补丁",
    "cleanup": "清理运行",
    "start": "开始",
    "success": "完成",
    "gate": "门禁",
    "status": "状态更新",
    "error": "错误",
    "failed": "失败",
    "retry": "重试",
    "approve_granted": "批准已记录",
    "apply_granted": "应用已确认",
    "apply_denied": "应用被阻止",
    "queued": "已排队",
}

STATUS_LABELS: dict[str, str] = {
    "NEW": "待规划",
    "PLANNED": "等待批准",
    "APPROVED": "等待实现",
    "IMPLEMENTING": "实现中",
    "IMPLEMENTED": "等待测试",
    "TESTING": "测试中",
    "TESTED": "等待审查",
    "REVIEWING": "审查中",
    "REVIEWED_PASS": "审查通过",
    "REVIEWED_CHANGES_REQUESTED": "需要修复",
    "FIXING": "修复中",
    "APPLIED": "已应用",
    "FAILED": "失败",
    "RUNNING": "运行中",
    "QUEUED": "已排队",
    "READY": "就绪",
    "PASS": "通过",
    "CHANGES_REQUESTED": "需要修改",
    "SUCCESS": "成功",
    "ERROR": "错误",
}


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
    artifacts = describe_artifacts(run_path, status_data.get("artifacts", []))
    return {
        "run_id": status_data.get("run_id", run_path.name),
        "handoff_summary": _handoff_summary(status_data, next_actions),
        "status": status_data.get("status"),
        "current_phase": status_data.get("current_phase"),
        "gate_state": status_data.get("gate_state", {}),
        "failure_recovery": status_data.get("failure_recovery"),
        "run_metrics": status_data.get("run_metrics", {}),
        "next_actions": next_actions,
        "provider_trail": provider_trail,
        "artifacts": artifacts,
        "timeline": timeline,
        "agent_activity": _agent_activity(
            status_data=status_data,
            next_actions=next_actions,
            timeline=timeline,
            artifacts=artifacts,
            include_state_message=since_event <= 0 and since_trace <= 0,
        ),
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


def _agent_activity(
    *,
    status_data: dict[str, Any],
    next_actions: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    artifacts: list[dict[str, str]],
    include_state_message: bool = True,
) -> dict[str, Any]:
    status = str(status_data.get("status") or "")
    phase = str(status_data.get("current_phase") or "")
    gate_state = status_data.get("gate_state", {}) or {}
    next_action = _primary_next_action(next_actions)
    tone = _run_tone(status_data, next_action)
    current_step = {
        "phase": phase,
        "label": _phase_label(phase),
        "status": status,
        "status_label": _status_label(status),
        "summary": _current_step_summary(status_data, next_action),
    }
    messages = [_activity_message(item, index) for index, item in enumerate(timeline)]
    if not messages and include_state_message:
        messages = [_state_message(status_data)]
    return {
        "headline": _activity_headline(status_data, next_action),
        "tone": tone,
        "current_step": current_step,
        "next_action": next_action,
        "conversation_state": _conversation_state(status_data, next_action, next_actions, tone),
        "gate_cards": _gate_cards(status_data, gate_state),
        "health_cards": _health_cards(status_data),
        "messages": messages,
        "artifacts": artifacts,
    }


def _conversation_state(
    status_data: dict[str, Any],
    next_action: dict[str, Any] | None,
    next_actions: list[dict[str, Any]],
    tone: str,
) -> dict[str, Any]:
    status = str(status_data.get("status") or "")
    phase = str(status_data.get("current_phase") or "")
    task = str(status_data.get("task") or "")
    suggestions = [_suggested_action(action) for action in next_actions]
    return {
        "task": task,
        "status": status,
        "status_label": _status_label(status),
        "phase": phase,
        "phase_label": _phase_label(phase),
        "tone": tone,
        "next_step": _conversation_next_step(status_data, next_action),
        "composer_placeholder": _composer_placeholder(status_data, next_action),
        "suggestions": suggestions,
    }


def _suggested_action(action: dict[str, Any]) -> dict[str, Any]:
    name = str(action.get("name") or "")
    return {
        "id": name,
        "label": ACTION_LABELS.get(name, _phase_label(name)),
        "action": name,
        "safe": bool(action.get("safe")),
        "tool": action.get("tool", ACTION_TO_TOOL.get(name, f"patchbay_{name}")),
        "requires_human_confirmation": bool(action.get("requires_human_confirmation")),
        "reason": action.get("reason", ""),
    }


def _conversation_next_step(status_data: dict[str, Any], next_action: dict[str, Any] | None) -> str:
    status = str(status_data.get("status") or "")
    if next_action:
        label = str(next_action.get("label") or next_action.get("name") or "下一步")
        reason = str(next_action.get("reason") or "")
        if next_action.get("requires_human_confirmation"):
            return f"需要你确认后，Patchbay Agent 才会执行“{label}”。{reason}"
        return f"可以继续执行“{label}”。{reason}"
    if status == "APPLIED":
        return "补丁已应用。你可以在诊断里查看产物，或清理本次运行。"
    if status == "FAILED":
        recovery = status_data.get("failure_recovery") if isinstance(status_data.get("failure_recovery"), dict) else {}
        return str(recovery.get("suggested_next_action") or status_data.get("suggested_next_action") or "运行遇到错误，请查看诊断日志。")
    return "当前没有可执行动作。你可以查看诊断，或输入新任务创建新的运行。"


def _composer_placeholder(status_data: dict[str, Any], next_action: dict[str, Any] | None) -> str:
    if next_action:
        label = str(next_action.get("label") or next_action.get("name") or "下一步")
        if next_action.get("requires_human_confirmation"):
            return f"输入“确认”或点击“{label}”继续"
        return f"输入“继续”或点击“{label}”"
    status = str(status_data.get("status") or "")
    if status == "FAILED":
        return "输入“修复”或打开诊断查看错误"
    return "输入新任务，或写下本地备注"


def _primary_next_action(next_actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not next_actions:
        return None
    selected = next((action for action in next_actions if action.get("safe")), next_actions[0])
    action = dict(selected)
    name = str(action.get("name") or "")
    action["label"] = ACTION_LABELS.get(name, _phase_label(name))
    return action


def _activity_headline(status_data: dict[str, Any], next_action: dict[str, Any] | None) -> str:
    run_id = status_data.get("run_id", "")
    status = str(status_data.get("status") or "")
    phase = str(status_data.get("current_phase") or "")
    if status == "FAILED":
        return f"Patchbay Agent 在{_phase_label(phase)}阶段遇到错误。"
    if status == "APPLIED":
        return "Patchbay Agent 已将审查通过的补丁应用到当前工作区。"
    if status == "REVIEWED_CHANGES_REQUESTED":
        return "Patchbay Agent 收到审查修改意见，下一步需要修复。"
    if next_action:
        return f"Patchbay Agent 已准备好执行：{next_action.get('label', next_action.get('name'))}。"
    if phase:
        return f"Patchbay Agent 当前处于{_phase_label(phase)}阶段。"
    return f"Patchbay Agent 正在跟踪运行 {run_id}。"


def _current_step_summary(status_data: dict[str, Any], next_action: dict[str, Any] | None) -> str:
    if status_data.get("error"):
        return str(status_data.get("error"))
    if next_action:
        return str(next_action.get("reason") or "")
    status = str(status_data.get("status") or "")
    if status == "APPLIED":
        return "补丁已应用，可以清理本次运行。"
    if status == "FAILED":
        recovery = status_data.get("failure_recovery") if isinstance(status_data.get("failure_recovery"), dict) else {}
        return str(recovery.get("error") or status_data.get("error") or recovery.get("suggested_next_action") or "检查日志后继续。")
    return "暂无可执行动作。"


def _gate_cards(status_data: dict[str, Any], gate_state: dict[str, Any]) -> list[dict[str, Any]]:
    review_result = gate_state.get("review_result") or status_data.get("review_result")
    ready_to_apply = bool(gate_state.get("ready_to_apply"))
    status = str(status_data.get("status") or "")
    return [
        {
            "key": "approval",
            "label": "批准",
            "status": "done" if gate_state.get("approved") else "pending",
            "tone": "success" if gate_state.get("approved") else "idle",
            "detail": "计划已批准" if gate_state.get("approved") else "等待人工批准计划",
        },
        {
            "key": "tests",
            "label": "测试",
            "status": "pass" if gate_state.get("tests_passed") else "pending",
            "tone": "success" if gate_state.get("tests_passed") else "idle",
            "detail": "测试通过" if gate_state.get("tests_passed") else "等待测试证据",
        },
        {
            "key": "review",
            "label": "审查",
            "status": review_result or "pending",
            "tone": _review_tone(review_result),
            "detail": _review_detail(review_result),
        },
        {
            "key": "apply",
            "label": "应用",
            "status": "applied" if status == "APPLIED" else "ready" if ready_to_apply else "blocked",
            "tone": "success" if status == "APPLIED" else "ready" if ready_to_apply else "blocked",
            "detail": "已应用到当前工作区" if status == "APPLIED" else "可以应用" if ready_to_apply else "需通过测试和审查",
        },
    ]


def _health_cards(status_data: dict[str, Any]) -> list[dict[str, Any]]:
    run_metrics = status_data.get("run_metrics") if isinstance(status_data.get("run_metrics"), dict) else {}
    routing = run_metrics.get("routing_evidence") if isinstance(run_metrics.get("routing_evidence"), dict) else {}
    health = routing.get("economy_health") if isinstance(routing.get("economy_health"), dict) else {}
    if not health:
        return []
    status = str(health.get("status") or "unknown")
    severity = str(health.get("severity") or "")
    coverage = routing.get("coverage") if isinstance(routing.get("coverage"), dict) else {}
    percent = coverage.get("observed_economy_percent")
    actions = routing.get("actions") if isinstance(routing.get("actions"), list) else []
    action = next((item for item in actions if isinstance(item, dict) and item.get("safe") is not False), None)
    return [
        {
            "key": "economy_route",
            "label": "Economy route",
            "status": status,
            "tone": _health_tone(status, severity),
            "detail": str(health.get("summary") or routing.get("summary") or ""),
            "recommendation": str(health.get("recommendation") or ""),
            "next_action": str(health.get("next_action") or ""),
            "action": action or _health_action(health),
            "coverage_percent": percent if isinstance(percent, (int, float)) else None,
        }
    ]


def _health_action(health: dict[str, Any]) -> dict[str, Any] | None:
    next_action = str(health.get("next_action") or "")
    if next_action == "apply_economy_profile":
        return {
            "id": "apply_economy_profile",
            "label": "Apply economy profile",
            "kind": "local_agent",
            "message": "apply economy profile",
            "safe": True,
            "reason": "Routes write/fix to the configured Reasonix/DeepSeek economy profile.",
        }
    if next_action == "inspect_routing_events":
        return {
            "id": "inspect_routing_events",
            "label": "Inspect routing events",
            "kind": "diagnostic_tab",
            "tab": "Trace",
            "safe": True,
            "reason": "Open provider events to inspect the non-economy write/fix provider evidence.",
        }
    if next_action == "wait_for_routing_evidence":
        return {
            "id": "wait_for_routing_evidence",
            "label": "Watch provider events",
            "kind": "diagnostic_tab",
            "tab": "Trace",
            "safe": True,
            "reason": "Open events while write/fix phases produce provider evidence.",
        }
    return None


def _health_tone(status: str, severity: str) -> str:
    if status == "healthy" or severity == "ok":
        return "success"
    if status == "pending_evidence" or severity == "info":
        return "ready"
    if status in {"drift", "not_configured"} or severity == "warning":
        return "blocked"
    return "idle"


def _activity_message(item: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    phase = str(item.get("phase") or "")
    action = str(item.get("action") or "")
    status = str(item.get("status") or "")
    source = str(item.get("source") or "event")
    index = item.get("index", fallback_index)
    return {
        "id": f"{source}-{index}-{item.get('timestamp', fallback_index)}",
        "kind": _message_kind(item),
        "timestamp": item.get("timestamp", ""),
        "phase": phase,
        "title": _message_title(phase, action, status),
        "body": str(item.get("detail") or ""),
        "status": status,
        "status_label": _status_label(status),
        "tone": _event_tone(item),
        "artifacts": item.get("artifact_paths", []),
        "provider": item.get("provider", item.get("agent", "")),
        "model": item.get("model", ""),
        "tool": item.get("tool", item.get("next_action", "")),
    }


def _state_message(status_data: dict[str, Any]) -> dict[str, Any]:
    status = str(status_data.get("status") or "")
    phase = str(status_data.get("current_phase") or "")
    return {
        "id": "state-summary",
        "kind": "state",
        "timestamp": status_data.get("updated_at", ""),
        "phase": phase,
        "title": _message_title(phase, "status", status),
        "body": _status_label(status),
        "status": status,
        "status_label": _status_label(status),
        "tone": _run_tone(status_data, None),
        "artifacts": [],
        "provider": "",
        "model": "",
        "tool": "",
    }


def _message_kind(item: dict[str, Any]) -> str:
    action = str(item.get("action") or "")
    if action in {"gate", "approve_granted", "apply_granted", "apply_denied"}:
        return "gate"
    if str(item.get("status") or "").upper() in {"ERROR", "FAILED"} or action in {"error", "failed"}:
        return "error"
    if item.get("source") == "trace":
        return "agent"
    return "event"


def _message_title(phase: str, action: str, status: str) -> str:
    phase_text = _phase_label(phase)
    action_text = ACTION_LABELS.get(action, action or "状态更新")
    status_text = _status_label(status)
    if status:
        return f"{phase_text} · {action_text} · {status_text}"
    return f"{phase_text} · {action_text}"


def _run_tone(status_data: dict[str, Any], next_action: dict[str, Any] | None) -> str:
    status = str(status_data.get("status") or "")
    if status == "FAILED":
        return "failed"
    if status == "APPLIED":
        return "success"
    if status == "REVIEWED_CHANGES_REQUESTED":
        return "blocked"
    if status in {"IMPLEMENTING", "TESTING", "REVIEWING", "FIXING", "RUNNING"}:
        return "running"
    if next_action:
        return "ready" if next_action.get("safe") else "blocked"
    return "idle"


def _event_tone(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "").upper()
    action = str(item.get("action") or "")
    if status in {"ERROR", "FAILED"} or action in {"error", "failed", "apply_denied"}:
        return "failed"
    if status in {"CHANGES_REQUESTED"}:
        return "blocked"
    if status in {"PASS", "SUCCESS"} or action in {"success", "approve_granted", "apply_granted"}:
        return "success"
    if status in {"RUNNING", "QUEUED"} or action in {"start", "retry", "queued"}:
        return "running"
    if status in {"READY"} or action == "gate":
        return "ready"
    return "idle"


def _review_tone(review_result: Any) -> str:
    if review_result == "PASS":
        return "success"
    if review_result == "CHANGES_REQUESTED":
        return "blocked"
    return "idle"


def _review_detail(review_result: Any) -> str:
    if review_result == "PASS":
        return "审查通过"
    if review_result == "CHANGES_REQUESTED":
        return "审查要求修改"
    return "等待审查"


def _phase_label(phase: str) -> str:
    return PHASE_LABELS.get(phase, phase or "空闲")


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status or "未知")


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
