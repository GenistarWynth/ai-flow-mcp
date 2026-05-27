from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from . import service
from .artifacts import read_text
from .config import load_config
from .errors import StateError
from .events import append_event
from .state import (
    APPLIED,
    APPROVED,
    FAILED,
    IMPLEMENTED,
    IMPLEMENTING,
    PLANNED,
    REVIEWED_CHANGES_REQUESTED,
    REVIEWED_PASS,
    REVIEWING,
    TESTED,
    TESTING,
)


SCHEMA_VERSION = 1
AGENT_LOCK_FILE = "AGENT.lock"
PLAN_CONFIRMATION = "plan_approved"
APPLY_CONFIRMATION = "apply_approved"


def agent_message(
    cwd: Path,
    message: str,
    *,
    run_id: str | None = None,
    confirmation: str = "none",
    include: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = service.resolve_root(cwd)
    text = (message or "").strip()
    intent = _classify_intent(text, has_run=bool(run_id), confirmation=confirmation)
    if not run_id and intent == "start":
        if not text:
            return _error_response("请告诉 Patchbay 要规划什么任务。", action="start")
        result = service.plan(root, task=text)
        run_id = result["run_id"]
        _append_agent_event(root, run_id, action="waiting_for_approval", status="WAITING_FOR_APPROVAL", detail="计划已生成，等待批准。", next_action="approve_plan")
        return _agent_response(
            root,
            run_id,
            action="start",
            reply="计划已生成。请先审阅计划，再批准开始实现。",
            requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
            include=_merge_include(include, {"plan": True, "events_since": 0}),
        )
    if not run_id:
        return _error_response("继续已有 Patchbay 对话需要提供 run_id。", action=intent)

    if intent == "approve_and_run":
        if confirmation != PLAN_CONFIRMATION:
            return _agent_response(
                root,
                run_id,
                action="approve_and_run",
                reply="开始实现前需要先明确批准计划。",
                requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
                include=_merge_include(include, {"plan": True}),
            )
        result = agent_autopilot(root, run_id, approve_plan=True)
        response = _agent_response(
            root,
            run_id,
            action="approve_and_run",
            reply=result["reply"],
            requires_confirmation=result.get("requires_confirmation"),
            include=include,
            extra={"autopilot": result},
        )
        return _with_autopilot_error(response, result)
    if intent == "apply":
        if confirmation != APPLY_CONFIRMATION:
            return _agent_response(
                root,
                run_id,
                action="apply",
                reply="应用变更需要明确批准。请先审阅最终 diff，再应用到当前工作区。",
                requires_confirmation=_confirmation("apply_approval", "apply", APPLY_CONFIRMATION),
                include=_merge_include(include, {"diff": True, "review": True}),
            )
        service.apply(root, run_id)
        _append_agent_event(root, run_id, action="applied", status="APPLIED", detail="已应用审查通过的 diff。", next_action="cleanup")
        return _agent_response(root, run_id, action="apply", reply="已将审查通过的 diff 应用到当前工作区。", include=include)
    if intent == "continue":
        result = agent_autopilot(root, run_id)
        response = _agent_response(
            root,
            run_id,
            action="continue",
            reply=result["reply"],
            requires_confirmation=result.get("requires_confirmation"),
            include=include,
            extra={"autopilot": result},
        )
        return _with_autopilot_error(response, result)
    if intent == "diff":
        return _agent_response(root, run_id, action="diff", reply="这是当前最终 diff。", include=_merge_include(include, {"diff": True}))
    if intent == "artifact":
        return _agent_response(root, run_id, action="artifact", reply="这是请求的运行产物。", include=_merge_include(include, {"plan": True, "review": True}))
    return agent_status(root, run_id, since=int((include or {}).get("events_since", 0) or 0), include=include)


def agent_status(cwd: Path, run_id: str, *, since: int = 0, include: dict[str, Any] | None = None) -> dict[str, Any]:
    root = service.resolve_root(cwd)
    return _agent_response(
        root,
        run_id,
        action="status",
        reply=_reply_for_status(service.status(root, run_id)),
        include=_merge_include(include, {"events_since": since}),
    )


def agent_autopilot(
    cwd: Path,
    run_id: str,
    *,
    max_fix_rounds: int | None = None,
    approve_plan: bool = False,
) -> dict[str, Any]:
    root = service.resolve_root(cwd)
    run_path, _ = service._load_run(root, run_id)
    _acquire_agent_lock(run_path)
    try:
        _append_agent_event(root, run_id, action="start", status="RUNNING", detail="Agent autopilot started.", next_action="advance")
        while True:
            current = service.status(root, run_id)
            status_value = str(current.get("status", ""))
            if status_value == PLANNED:
                if not approve_plan:
                    _append_agent_event(root, run_id, action="waiting_for_approval", status="WAITING_FOR_APPROVAL", detail="需要批准计划。", next_action="approve_plan")
                    return _autopilot_result(
                        root,
                        run_id,
                        "开始实现前需要先明确批准计划。",
                        requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
                    )
                service.approve(root, run_id)
                _append_agent_event(root, run_id, action="decision", status="APPROVED", detail="已记录计划批准。", next_action="write")
                continue
            if status_value == APPROVED:
                service.write(root, run_id)
                continue
            if status_value == IMPLEMENTED:
                service.test(root, run_id)
                continue
            if status_value == TESTED:
                service.review(root, run_id)
                continue
            if status_value == REVIEWED_CHANGES_REQUESTED:
                if _fix_iterations_exhausted(root, current, max_fix_rounds):
                    _append_agent_event(root, run_id, action="stopped", status="STOPPED", detail="已达到修复轮次上限。", next_action="inspect")
                    return _autopilot_result(root, run_id, "已达到修复轮次上限。继续前请检查 REVIEW.md 和 TEST.log。")
                service.fix(root, run_id)
                continue
            if status_value == REVIEWED_PASS and current.get("tests_passed"):
                _append_agent_event(root, run_id, action="ready_to_apply", status="READY_TO_APPLY", detail="测试和审查均已通过。", next_action="apply")
                return _autopilot_result(
                    root,
                    run_id,
                    "实现已通过测试和审查。请审阅 diff；如果要应用到当前工作区，请明确批准应用。",
                    requires_confirmation=_confirmation("apply_approval", "apply", APPLY_CONFIRMATION),
                )
            if status_value in {IMPLEMENTING, TESTING, REVIEWING}:
                return _autopilot_result(root, run_id, "Patchbay 阶段正在运行。请轮询状态或事件查看进度。")
            if status_value == FAILED:
                _append_agent_event(root, run_id, action="stopped", status="FAILED", detail=str(current.get("error") or "运行失败。"), next_action="inspect")
                return _autopilot_result(root, run_id, "运行失败。继续前请检查返回的产物和事件。")
            if status_value == APPLIED:
                return _autopilot_result(root, run_id, "审查通过的 diff 已经应用。")
            return _autopilot_result(root, run_id, f"当前状态为 {status_value}，没有可自动执行的动作。")
    except Exception as exc:
        try:
            _append_agent_event(root, run_id, action="error", status="ERROR", detail=str(exc), next_action="inspect")
        except Exception:
            pass
        return _autopilot_result(root, run_id, f"Agent 已停止：{exc}", ok=False, error=str(exc))
    finally:
        _release_agent_lock(run_path)


def start_background_agent(cwd: Path, run_id: str, *, max_fix_rounds: int | None = None) -> dict[str, Any]:
    # v1 keeps the background job model phase-oriented. The API is present so
    # callers have one service surface; long model phases can still be polled
    # through events while the foreground agent advances between phases.
    result = agent_autopilot(cwd, run_id, max_fix_rounds=max_fix_rounds)
    return {"background": False, "phase": "agent", "run_id": run_id, "result": result}


def _classify_intent(message: str, *, has_run: bool, confirmation: str) -> str:
    text = message.strip().lower()
    if confirmation == PLAN_CONFIRMATION:
        return "approve_and_run"
    if confirmation == APPLY_CONFIRMATION:
        return "apply"
    if not has_run:
        return "start"
    if _has_any(text, ("apply", "应用", "套用")):
        return "apply"
    if _has_any(text, ("approve", "approved", "confirm", "确认", "批准", "同意")):
        return "approve_and_run"
    if _has_any(text, ("continue", "go on", "resume", "继续", "推进")):
        return "continue"
    if _has_any(text, ("diff", "patch", "补丁", "变更")):
        return "diff"
    if _has_any(text, ("artifact", "plan", "review", "log", "产物", "计划", "日志")):
        return "artifact"
    return "status"


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _fix_iterations_exhausted(root: Path, status_data: dict[str, Any], max_fix_rounds: int | None) -> bool:
    configured = int(load_config(root).get("writer", {}).get("max_repair_iterations", 2))
    limit = configured if max_fix_rounds is None else min(int(max_fix_rounds), configured)
    return int(status_data.get("fix_iterations") or 0) >= limit


def _autopilot_result(
    root: Path,
    run_id: str,
    reply: str,
    *,
    requires_confirmation: dict[str, Any] | None = None,
    ok: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    current = service.status(root, run_id)
    return {
        "run_id": run_id,
        "ok": ok,
        "reply": reply,
        "status": current,
        "requires_confirmation": requires_confirmation,
        "next_actions": _next_actions_for_status(current),
        "error": error,
    }


def _agent_response(
    root: Path,
    run_id: str,
    *,
    action: str,
    reply: str,
    requires_confirmation: dict[str, Any] | None = None,
    include: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = service.status(root, run_id)
    effective_include = _merge_include(include, _auto_include_for_status(current))
    since = int(effective_include.get("events_since", 0) or 0)
    response: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "action": action,
        "reply": reply,
        "run_id": run_id,
        "status": current,
        "events": service.events(root, run_id, since=since, phase=effective_include.get("event_phase") or None),
        "artifacts": _included_artifacts(root, run_id, effective_include),
        "diff": service.diff(root, run_id) if effective_include.get("diff") else None,
        "requires_confirmation": requires_confirmation or _required_confirmation_for_status(current),
        "next_actions": _next_actions_for_status(current),
        "error": None,
    }
    if extra:
        response.update(extra)
    return response


def _with_autopilot_error(response: dict[str, Any], autopilot: dict[str, Any]) -> dict[str, Any]:
    if autopilot.get("ok") is False:
        response["ok"] = False
        response["error"] = autopilot.get("error") or autopilot.get("reply")
    return response


def _error_response(message: str, *, action: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "action": action,
        "reply": message,
        "run_id": None,
        "status": None,
        "events": None,
        "artifacts": {},
        "diff": None,
        "requires_confirmation": None,
        "next_actions": [],
        "error": message,
    }


def _included_artifacts(root: Path, run_id: str, include: dict[str, Any]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    names: list[tuple[str, int | None]] = []
    if include.get("plan"):
        names.append(("PLAN.md", None))
    if include.get("review"):
        names.append(("REVIEW.md", None))
    artifact = str(include.get("artifact") or "").strip()
    if artifact:
        names.append((artifact, _optional_int(include.get("artifact_tail"))))
    for name, tail in names:
        try:
            artifacts[name] = service.artifact(root, run_id, name, tail=tail)
        except Exception as exc:
            artifacts[name] = {"error": str(exc)}
    return artifacts


def _auto_include_for_status(status_data: dict[str, Any]) -> dict[str, Any]:
    status_value = status_data.get("status")
    if status_value == PLANNED:
        return {"plan": True}
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        return {"review": True, "diff": True}
    if status_value == FAILED:
        return {"review": True, "artifact": "TEST.log", "artifact_tail": 120}
    return {}


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _merge_include(include: dict[str, Any] | None, defaults: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    if include:
        merged.update(include)
    return merged


def _required_confirmation_for_status(status_data: dict[str, Any]) -> dict[str, Any] | None:
    if status_data.get("status") == PLANNED:
        return _confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION)
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        return _confirmation("apply_approval", "apply", APPLY_CONFIRMATION)
    return None


def _confirmation(kind: str, required_action: str, confirmation: str) -> dict[str, Any]:
    return {
        "type": kind,
        "required_action": required_action,
        "confirmation": confirmation,
    }


def _next_actions_for_status(status_data: dict[str, Any]) -> list[str]:
    if status_data.get("status") == PLANNED:
        return ["approve_and_run", "status", "events", "artifact"]
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        return ["apply", "diff", "status", "events"]
    status_value = str(status_data.get("status") or "")
    if status_value in {APPROVED, IMPLEMENTED, TESTED, REVIEWED_CHANGES_REQUESTED}:
        return ["continue", "status", "events"]
    if status_value == FAILED:
        return ["status", "events", "artifact", "diff"]
    if status_value == APPLIED:
        return ["status", "events"]
    return ["status", "events"]


def _reply_for_status(status_data: dict[str, Any]) -> str:
    if status_data.get("status") == PLANNED:
        return "计划已生成，正在等待批准。"
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        return "测试和审查已通过，正在等待明确批准应用。"
    if status_data.get("status") == FAILED:
        return f"运行在 {status_data.get('stage') or '未知阶段'} 失败：{status_data.get('error') or ''}".strip()
    return f"运行状态：{status_data.get('status')}。"


def _append_agent_event(root: Path, run_id: str, **kwargs: Any) -> None:
    run_path, _ = service._load_run(root, run_id)
    append_event(run_path, phase="agent", run_id=run_id, **kwargs)


def _agent_lock_path(run_path: Path) -> Path:
    return run_path / AGENT_LOCK_FILE


def _acquire_agent_lock(run_path: Path) -> None:
    path = _agent_lock_path(run_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        raise StateError(
            f"Agent 正在运行：{read_text(path, default='').strip()}",
            stage="agent",
            suggested_next_action="轮询 Agent 状态和事件，直到当前运行结束。",
        )
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"pid={os.getpid()}\nstarted_at={time.time()}\n")


def _release_agent_lock(run_path: Path) -> None:
    path = _agent_lock_path(run_path)
    if path.exists():
        path.unlink()
