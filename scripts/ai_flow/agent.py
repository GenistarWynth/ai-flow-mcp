from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from . import service
from .action_contract import group_actions
from .artifacts import now_iso, read_text
from .config import economy_target, load_config
from .config_wizard import run_config_wizard
from .doctor import run_doctor
from .errors import StateError
from .events import append_event
from .mcp_install import HOST_ALIASES, normalize_mcp_host
from .routing import profile_routing_digest as _profile_routing_digest, route_label as _route_label
from .setup_flow import run_setup, _without_mcp_followup_actions, _without_mcp_followup_text
from .skill_contract import skill_contract_summary
from .state import (
    APPLIED,
    APPROVED,
    FAILED,
    FIXING,
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
INHERITED_AGENT_LOCK_ENV = "PATCHBAY_INHERITED_AGENT_LOCK"
AGENT_LOCK_TOKEN_ENV = "PATCHBAY_AGENT_LOCK_TOKEN"
PLAN_CONFIRMATION = "plan_approved"
APPLY_CONFIRMATION = "apply_approved"
TASK_INTENT_WORDS = {
    "add",
    "build",
    "change",
    "create",
    "fix",
    "implement",
    "improve",
    "modify",
    "optimize",
    "refactor",
    "repair",
    "test",
    "update",
    "write",
}
CHINESE_TASK_INTENT_WORDS = (
    "新增",
    "增加",
    "实现",
    "修复",
    "构建",
    "创建",
    "优化",
    "改进",
    "重构",
    "修改",
    "测试",
    "编写",
    "开发",
    "做一个",
    "做个",
    "写一个",
    "写个",
)

IMPLICIT_LOCAL_TOOL_PREFERENCE_PHRASES = (
    "use browser skill",
    "use chrome skill",
    "use the browser skill",
    "use the chrome skill",
    "use built-in browser",
    "use the built-in browser",
    "use your built-in browser",
    "built-in browser",
    "browser skill",
    "chrome skill",
    "自带浏览器",
    "内置浏览器",
    "浏览器功能",
    "浏览器 skill",
)


UNATTENDED_PLAN_APPROVAL_PHRASES = (
    "approved in advance",
    "assume approved",
    "assume yes",
    "continue without asking",
    "do not ask me",
    "don't ask me",
    "dont ask me",
    "go ahead without asking",
    "no need to ask",
    "no need to confirm",
    "full access",
    "complete access",
    "approve yourself",
    "confirm yourself",
    "you have permission",
    "you have all permissions",
    "\u4e0d\u8981\u95ee\u6211",
    "\u4e0d\u8981\u518d\u95ee\u6211",
    "\u4e0d\u8981\u518d\u8be2\u95ee\u6211",
    "\u522b\u95ee\u6211",
    "\u522b\u518d\u95ee\u6211",
    "\u522b\u627e\u6211",
    "\u522b\u518d\u627e\u6211",
    "\u4e0d\u9700\u8981\u786e\u8ba4",
    "\u4e0d\u9700\u5411\u6211\u786e\u8ba4",
    "\u4e0d\u7528\u786e\u8ba4",
    "\u4e0d\u7528\u5411\u6211\u786e\u8ba4",
    "\u4e0d\u5fc5\u5411\u6211\u786e\u8ba4",
    "\u4e0d\u8981\u5411\u6211\u786e\u8ba4",
    "\u65e0\u9700\u786e\u8ba4",
    "\u65e0\u9700\u5411\u6211\u786e\u8ba4",
    "\u6240\u6709\u6743\u9650\u90fd\u7ed9\u4f60",
    "\u6240\u6709\u6743\u9650\u5168\u90fd\u7ed9\u4f60",
    "\u6240\u6709\u6743\u9650\u5168\u90e8\u7ed9\u4f60",
    "\u5168\u90e8\u6743\u9650\u90fd\u7ed9\u4f60",
    "\u6743\u9650\u90fd\u7ed9\u4f60",
    "\u5b8c\u5168\u8bbf\u95ee\u6743\u9650",
    "\u6211\u7ed9\u4f60\u5b8c\u5168\u8bbf\u95ee\u6743\u9650",
    "\u81ea\u5df1\u5141\u8bb8",
    "\u81ea\u5df1\u786e\u8ba4",
    "\u4f60\u81ea\u5df1\u51b3\u5b9a",
    "\u4f60\u81ea\u5df1\u6279\u51c6",
    "\u6211\u4e0d\u5728\u8eab\u8fb9",
    "\u6211\u6839\u672c\u4e0d\u5728\u8eab\u8fb9",
    "\u6839\u672c\u4e0d\u5728\u8eab\u8fb9",
    "\u4eba\u4e0d\u5728",
)


def agent_message(
    cwd: Path,
    message: str,
    *,
    run_id: str | None = None,
    confirmation: str = "none",
    include: dict[str, Any] | None = None,
    max_fix_rounds: int | None = None,
    background: bool = False,
) -> dict[str, Any]:
    """Conversational entry point for MCP, CLI, and web clients.

    The agent routes natural-language commands onto the existing Patchbay
    workflow. It never bypasses the plan approval or apply gates.
    """
    root = service.resolve_root(cwd)
    text = (message or "").strip()
    intent = _classify_intent(text, has_run=bool(run_id), confirmation=confirmation)
    if intent == "doctor":
        return _doctor_response(root, text)
    if intent == "help":
        return _help_response(root, run_id=run_id, include=include)
    if intent == "runs":
        return _runs_response(root)
    if intent == "reasonix_command_configure":
        return _reasonix_command_configure_response(root, text)
    if intent == "custom_provider_command_configure":
        return _custom_provider_command_configure_response(root, text)
    if intent == "custom_provider_setup":
        return _custom_provider_setup_response(root, text)
    if intent == "profile_apply":
        return _profile_apply_response(root)
    if intent == "profile_show":
        return _profile_show_response(root, run_id=run_id)
    if intent == "next_step":
        return _next_step_response(root, run_id=run_id, include=include)
    if intent == "gate_status":
        return _gate_status_response(root, run_id=run_id, include=include)
    if intent == "missing_run":
        return _missing_run_response(root, text)
    if intent == "local_mode":
        return _local_mode_response(root, text, run_id=run_id)
    if intent == "setup":
        return _setup_response(root, text)
    if intent == "metrics_latest":
        return _latest_metrics_response(root, text)
    if intent == "latest_view":
        return _latest_view_response(root, text)
    if intent == "metrics":
        assert run_id is not None
        return _metrics_response(root, run_id)
    if background:
        return _start_background_agent(
            root,
            text,
            run_id=run_id,
            confirmation=confirmation,
            include=include,
            max_fix_rounds=max_fix_rounds,
            intent=intent,
        )
    if not run_id and intent == "start":
        if not text:
            return _error_response("Tell Patchbay what task to plan.", action="start")
        planned = service.plan(root, task=text)
        run_id = planned["run_id"]
        _append_agent_event(
            root,
            run_id,
            action="waiting_for_approval",
            status="WAITING_FOR_APPROVAL",
            detail="Plan generated; waiting for explicit approval.",
            next_action="approve_plan",
        )
        routing_preview = _routing_preview(root)
        return _agent_response(
            root,
            run_id,
            action="start",
            reply=(
                "Plan generated. Review PLAN.md, then approve before implementation. "
                + routing_preview["reply_suffix"]
            ),
            requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
            include=_merge_include(include, {"plan": True, "events_since": 0}),
            extra={
                "profile": routing_preview["profile"],
                "routing": routing_preview["routing"],
                "actions": routing_preview["actions"],
            },
        )

    if not run_id:
        return _error_response("Continuing a Patchbay run requires run_id.", action=intent)

    if intent == "background_cancel":
        result = service.cancel_background_job(root, run_id)
        return _agent_response(
            root,
            run_id,
            action="background_cancel",
            reply=str(result.get("reply") or "Background cancellation requested."),
            include=include,
            extra={
                "ok": bool(result.get("ok")),
                "canceled": bool(result.get("canceled")),
                "background_job": result.get("background_job"),
                "cancel_result": result.get("cancel_result"),
                "error": result.get("error"),
            },
        )

    if intent == "approve_and_run":
        message_confirms_plan = _is_unattended_plan_approval(text)
        if confirmation != PLAN_CONFIRMATION and not message_confirms_plan:
            return _agent_response(
                root,
                run_id,
                action="approve_and_run",
                reply="Implementation requires explicit plan approval.",
                requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
                include=_merge_include(include, {"plan": True}),
            )
        autopilot = agent_autopilot(root, run_id, approve_plan=True, max_fix_rounds=max_fix_rounds)
        response = _agent_response(
            root,
            run_id,
            action="approve_and_run",
            reply=str(autopilot["reply"]),
            requires_confirmation=autopilot.get("requires_confirmation"),
            include=include,
            extra={
                "autopilot": autopilot,
                "confirmation_source": "message" if message_confirms_plan and confirmation != PLAN_CONFIRMATION else "token",
            },
        )
        return _with_autopilot_error(response, autopilot)

    if intent == "apply":
        current = service.status(root, run_id)
        if not _apply_ready(current):
            diagnosis = _gate_diagnosis(current)
            message = _gate_status_reply(run_id, diagnosis)
            if "Apply is blocked" not in message:
                message += " Apply is blocked until tests pass and review returns PASS."
            return _agent_response(
                root,
                run_id,
                action="apply",
                reply=message,
                include=include,
                extra={
                    "ok": False,
                    "error": message,
                    "gate_diagnosis": diagnosis,
                    "actions": _gate_status_actions(run_id, current, include_open_run=False),
                },
            )
        if confirmation != APPLY_CONFIRMATION:
            return _agent_response(
                root,
                run_id,
                action="apply",
                reply="Applying changes requires explicit approval after reviewing the final diff.",
                requires_confirmation=_confirmation("apply_approval", "apply", APPLY_CONFIRMATION),
                include=_merge_include(include, {"diff": True, "review": True}),
            )
        service.apply(root, run_id)
        _append_agent_event(
            root,
            run_id,
            action="applied",
            status="APPLIED",
            detail="Reviewed diff applied to the current workspace.",
            next_action="cleanup",
        )
        return _agent_response(root, run_id, action="apply", reply="Applied reviewed diff to the current workspace.", include=include)

    if intent == "continue":
        autopilot = agent_autopilot(root, run_id, max_fix_rounds=max_fix_rounds)
        response = _agent_response(
            root,
            run_id,
            action="continue",
            reply=str(autopilot["reply"]),
            requires_confirmation=autopilot.get("requires_confirmation"),
            include=include,
            extra={"autopilot": autopilot},
        )
        return _with_autopilot_error(response, autopilot)

    if intent == "context":
        return _agent_response(
            root,
            run_id,
            action="context",
            reply="Current run handoff context.",
            include=_merge_include(include, {"events_since": 0}),
            extra=_run_view_response_extra(text, default_tab="Overview"),
        )

    if intent == "events":
        return _agent_response(
            root,
            run_id,
            action="events",
            reply="Current run event timeline.",
            include=_merge_include(include, {"events_since": 0, "include_trace": True}),
            extra=_run_view_response_extra(text, default_tab="Trace"),
        )

    if intent == "diff":
        return _agent_response(
            root,
            run_id,
            action="diff",
            reply="Current final diff.",
            include=_merge_include(include, {"diff": True}),
            extra=_run_view_response_extra(text, default_tab="Diff"),
        )

    if intent == "artifact":
        return _agent_response(
            root,
            run_id,
            action="artifact",
            reply="Requested run artifacts.",
            include=_merge_include(include, {"plan": True, "review": True}),
            extra=_run_view_response_extra(text, default_tab="Artifacts"),
        )

    return _agent_response(
        root,
        run_id,
        action="status",
        reply=_reply_for_status(service.status(root, run_id)),
        include=_merge_include(include, {"events_since": int((include or {}).get("events_since", 0) or 0)}),
        extra=_run_view_response_extra(text),
    )


def _start_background_agent(
    root: Path,
    message: str,
    *,
    run_id: str | None,
    confirmation: str,
    include: dict[str, Any] | None,
    max_fix_rounds: int | None,
    intent: str,
) -> dict[str, Any]:
    if not run_id and intent == "start":
        if not message:
            return _error_response("Tell Patchbay what task to plan.", action="start")
        job = service.start_background_phase(root, "plan", task=message)
        _append_agent_event_by_path(
            Path(str(job["run_dir"])),
            run_id=str(job["run_id"]),
            action="queued",
            status="QUEUED",
            detail="Background planning job started.",
            next_action="poll_status",
        )
        routing_preview = _routing_preview(root)
        return _background_pending_response(
            action="start",
            run_id=str(job["run_id"]),
            reply=(
                "Planning started in the background. Poll status, context, or events for progress. "
                + routing_preview["reply_suffix"]
            ),
            job=job,
            extra={
                "profile": routing_preview["profile"],
                "routing": routing_preview["routing"],
                "routing_actions": routing_preview["actions"],
            },
        )

    if not run_id:
        return _error_response("Continuing a Patchbay run requires run_id.", action=intent)

    if intent in {"context", "events", "diff", "artifact", "status"}:
        return agent_message(
            root,
            message,
            run_id=run_id,
            confirmation=confirmation,
            include=include,
            max_fix_rounds=max_fix_rounds,
        )

    if intent == "apply":
        return _agent_response(
            root,
            run_id,
            action="apply",
            reply="Background apply is not supported. Review the final diff and confirm apply in the foreground.",
            include=include,
            extra={"ok": False, "error": "background apply is not supported"},
        )

    message_confirms_plan = _is_unattended_plan_approval(message)
    if intent == "approve_and_run" and confirmation != PLAN_CONFIRMATION and not message_confirms_plan:
        return _agent_response(
            root,
            run_id,
            action="approve_and_run",
            reply="Implementation requires explicit plan approval.",
            requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
            include=_merge_include(include, {"plan": True}),
        )

    current = service.status(root, run_id)
    active_job = _active_background_job(current)
    if active_job:
        return _background_already_running_response(root, run_id, action=intent, job=active_job, include=include)
    if intent == "continue" and (current.get("status") == PLANNED or _apply_ready(current)):
        return agent_message(
            root,
            message,
            run_id=run_id,
            confirmation=confirmation,
            include=include,
            max_fix_rounds=max_fix_rounds,
        )

    if intent not in {"approve_and_run", "continue"}:
        return agent_message(
            root,
            message,
            run_id=run_id,
            confirmation=confirmation,
            include=include,
            max_fix_rounds=max_fix_rounds,
        )

    run_path, _ = service._load_run(root, run_id)
    lock_token = uuid.uuid4().hex
    _acquire_agent_lock(run_path, token=lock_token)
    command = _background_agent_command(
        root=root,
        message=message or "continue",
        run_id=run_id,
        confirmation=confirmation,
        include=include or {},
        max_fix_rounds=max_fix_rounds,
    )
    job_started = time.time()
    background_actions = service.background_followup_actions(run_id)
    pending_job = {
        "background": True,
        "kind": "agent",
        "phase": "agent",
        "action": intent,
        "pid": None,
        "run_id": run_id,
        "command": command,
        "started_at": now_iso(),
        "started_at_epoch": job_started,
        "root": str(root),
        "run_dir": str(run_path),
        "events_path": str(run_path / "events.jsonl"),
        "trace_path": str(run_path / "trace.jsonl"),
        "actions": background_actions,
    }
    service._record_job(run_path, pending_job)
    _append_agent_event(
        root,
        run_id,
        action="queued",
        status="QUEUED",
        detail="Background agent turn queued.",
        next_action="poll_status",
    )
    env = dict(os.environ)
    env[INHERITED_AGENT_LOCK_ENV] = "agent"
    env[AGENT_LOCK_TOKEN_ENV] = lock_token
    env["PATCHBAY_BACKGROUND_ROOT"] = str(root)
    env["PATCHBAY_BACKGROUND_RUN_DIR"] = str(run_path)
    env["PATCHBAY_BACKGROUND_SOURCE_SCRIPTS"] = str(Path(__file__).resolve().parents[1])
    try:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except Exception:
        _release_agent_lock(run_path, token=lock_token)
        raise

    job = {**pending_job, "pid": process.pid}
    early_exit = process.poll()
    if early_exit is not None:
        _release_agent_lock(run_path, token=lock_token)
        job["exit_code"] = early_exit
        job["finished_at"] = now_iso()
        job["finished_at_epoch"] = time.time()
    service._record_job(run_path, job)
    if early_exit is None:
        service._track_background_process(
            process,
            run_path,
            on_exit=lambda _exit_code: _release_agent_lock(run_path, token=lock_token),
        )
    response = _agent_response(
        root,
        run_id,
        action=intent,
        reply="Background agent turn started. Poll status, context, or events for progress.",
        include=include,
        extra={"background": True, "job": job, "background_job": service.summarize_background_job(job)},
    )
    response["requires_confirmation"] = None
    response["next_actions"] = _background_next_actions()
    response["actions"] = background_actions
    return _with_action_groups(response)


def _active_background_job(status_data: dict[str, Any]) -> dict[str, Any] | None:
    job = status_data.get("background_job") if isinstance(status_data.get("background_job"), dict) else None
    if not job:
        return None
    if job.get("active") or job.get("status") == "running":
        return job
    return None


def _background_already_running_response(
    root: Path,
    run_id: str,
    *,
    action: str,
    job: dict[str, Any],
    include: dict[str, Any] | None,
) -> dict[str, Any]:
    actions = list(job.get("actions") or service.background_followup_actions(run_id))
    response = _agent_response(
        root,
        run_id,
        action=action,
        reply="A background agent turn is already running. Poll status, context, or events for progress.",
        include=include,
        extra={"background": True, "already_running": True, "background_job": job, "actions": actions},
    )
    response["requires_confirmation"] = None
    response["next_actions"] = _background_next_actions()
    return response


def _background_agent_command(
    *,
    root: Path,
    message: str,
    run_id: str,
    confirmation: str,
    include: dict[str, Any],
    max_fix_rounds: int | None,
) -> list[str]:
    runner = """
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def exit_code(value):
    if isinstance(value, int):
        return value
    return 0 if value is None else 1

def mark_finished(run_dir, code):
    job_path = Path(run_dir) / "JOB.json"
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job["exit_code"] = code
        job["finished_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        job["finished_at_epoch"] = time.time()
        temp_path = job_path.with_name(f".{job_path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8", newline="\\n") as handle:
                json.dump(job, handle, indent=2, ensure_ascii=False, sort_keys=True)
                handle.write("\\n")
            temp_path.replace(job_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass

root = Path(os.environ["PATCHBAY_BACKGROUND_ROOT"])
source_scripts = Path(os.environ.get("PATCHBAY_BACKGROUND_SOURCE_SCRIPTS", ""))
for candidate in (root / "scripts", source_scripts):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

code = 0
try:
    from ai_flow.cli import main
    result = main(sys.argv[1:])
    code = exit_code(result)
    raise SystemExit(result)
except SystemExit as exc:
    code = exit_code(exc.code)
    raise
except BaseException:
    code = 1
    raise
finally:
    run_dir = os.environ.get("PATCHBAY_BACKGROUND_RUN_DIR")
    if run_dir:
        mark_finished(run_dir, code)
    token = os.environ.get("PATCHBAY_AGENT_LOCK_TOKEN")
    if run_dir and token:
        lock_path = Path(run_dir) / "AGENT.lock"
        try:
            lines = lock_path.read_text(encoding="utf-8").splitlines()
            if token in lines:
                lock_path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
""".strip()
    command = [
        sys.executable,
        "-c",
        runner,
        "agent",
        "message",
        message,
        "--run-id",
        run_id,
        "--confirmation",
        confirmation or "none",
        "--json",
    ]
    if max_fix_rounds is not None:
        command.extend(["--max-fix-rounds", str(max_fix_rounds)])
    if include.get("plan"):
        command.append("--include-plan")
    if include.get("review"):
        command.append("--include-review")
    if include.get("diff"):
        command.append("--include-diff")
    return command


def _background_next_actions() -> list[str]:
    return ["status", "context", "events"]


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
        for _ in range(20):
            current = service.status(root, run_id)
            status_value = str(current.get("status", ""))
            if status_value == PLANNED:
                if not approve_plan:
                    _append_agent_event(
                        root,
                        run_id,
                        action="waiting_for_approval",
                        status="WAITING_FOR_APPROVAL",
                        detail="Plan approval is required.",
                        next_action="approve_plan",
                    )
                    return _autopilot_result(
                        root,
                        run_id,
                        "Implementation requires explicit plan approval.",
                        requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
                    )
                service.approve(root, run_id)
                _append_agent_event(root, run_id, action="decision", status="APPROVED", detail="Plan approval recorded.", next_action="write")
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
                    _append_agent_event(
                        root,
                        run_id,
                        action="stopped",
                        status="STOPPED",
                        detail="Maximum fix iterations reached.",
                        next_action="inspect",
                    )
                    return _autopilot_result(root, run_id, "Maximum fix iterations reached. Inspect REVIEW.md and TEST.log before continuing.")
                service.fix(root, run_id)
                continue
            if status_value == REVIEWED_PASS and current.get("tests_passed"):
                _append_agent_event(
                    root,
                    run_id,
                    action="ready_to_apply",
                    status="READY_TO_APPLY",
                    detail="Tests and review passed.",
                    next_action="apply",
                )
                return _autopilot_result(
                    root,
                    run_id,
                    "Implementation passed tests and review. Review the diff, then explicitly approve apply.",
                    requires_confirmation=_confirmation("apply_approval", "apply", APPLY_CONFIRMATION),
                )
            if status_value == REVIEWED_PASS:
                tests_status = str(current.get("tests_status") or "NOT_RUN")
                _append_agent_event(
                    root,
                    run_id,
                    action="blocked",
                    status="BLOCKED",
                    detail=f"Review passed, but apply is blocked because tests_status is {tests_status}.",
                    next_action="configure_tests",
                )
                return _autopilot_result(
                    root,
                    run_id,
                    f"Review passed, but apply is blocked because tests_status is {tests_status}. Configure tests or explicitly allow skipped tests.",
                )
            if status_value in {IMPLEMENTING, TESTING, REVIEWING, FIXING}:
                return _autopilot_result(root, run_id, "A Patchbay phase is already running. Poll status, context, or events for progress.")
            if status_value == FAILED:
                recovery = current.get("failure_recovery") or _failure_recovery_summary(current)
                _append_agent_event(
                    root,
                    run_id,
                    action="stopped",
                    status="FAILED",
                    detail=str(current.get("error") or "Run failed."),
                    next_action="inspect",
                )
                return _autopilot_result(
                    root,
                    run_id,
                    "Run failed. Inspect artifacts and events before continuing.",
                    ok=False,
                    error=str(current.get("error") or "Run failed."),
                    extra={"recovery": recovery},
                )
            if status_value == APPLIED:
                return _autopilot_result(root, run_id, "Reviewed diff is already applied.")
            return _autopilot_result(root, run_id, f"Current status is {status_value}; no automatic action is available.")
        return _autopilot_result(root, run_id, "Agent stopped after reaching the internal step limit.", ok=False, error="step limit reached")
    except StateError as exc:
        blocker = None
        try:
            blocker = service.status(root, run_id).get("blocked_next_action")
        except Exception:
            blocker = None
        if blocker:
            action = blocker.get("action") if isinstance(blocker.get("action"), dict) else {}
            try:
                _append_agent_event(
                    root,
                    run_id,
                    action="blocked",
                    status="BLOCKED",
                    detail=str(exc),
                    next_action=str(action.get("message") or "readiness"),
                )
            except Exception:
                pass
            return _autopilot_result(
                root,
                run_id,
                f"Agent stopped before starting the next phase: {exc}",
                ok=False,
                error=str(exc),
                extra={"blocker": blocker},
            )
        try:
            _append_agent_event(root, run_id, action="error", status="ERROR", detail=str(exc), next_action="inspect")
        except Exception:
            pass
        return _autopilot_result(root, run_id, f"Agent stopped: {exc}", ok=False, error=str(exc))
    except Exception as exc:
        try:
            _append_agent_event(root, run_id, action="error", status="ERROR", detail=str(exc), next_action="inspect")
        except Exception:
            pass
        return _autopilot_result(root, run_id, f"Agent stopped: {exc}", ok=False, error=str(exc))
    finally:
        _release_agent_lock(run_path)


def _classify_intent(message: str, *, has_run: bool, confirmation: str) -> str:
    text = message.strip().lower()
    if confirmation == PLAN_CONFIRMATION:
        return "approve_and_run"
    if confirmation == APPLY_CONFIRMATION:
        return "apply"
    if _is_reasonix_command_configure_intent(text):
        return "reasonix_command_configure"
    if _is_custom_provider_command_configure_intent(text):
        return "custom_provider_command_configure"
    if _is_custom_economy_provider_setup_intent(text):
        return "custom_provider_setup"
    profile_intent = _config_profile_intent(text)
    if profile_intent:
        return profile_intent
    if _is_doctor_intent(text):
        return "doctor"
    if _is_help_intent(text):
        return "help"
    if _is_setup_intent(text):
        return "setup"
    if _is_local_mode_intent(text):
        return "local_mode"
    if _is_background_cancel_intent(text):
        return "background_cancel" if has_run else "missing_run"
    if _is_next_step_query(text):
        return "next_step"
    if _is_gate_status_query(text):
        return "gate_status"
    if _is_metrics_intent(text):
        return "metrics" if has_run else "metrics_latest"
    if not has_run:
        if _is_unattended_plan_approval(text):
            return "missing_run"
        if _is_runs_intent(text):
            return "runs"
        if _is_run_bound_intent(text):
            if _is_gate_changing_run_request(text):
                return "missing_run"
            if _missing_run_requested_view(text):
                return "latest_view"
            return "missing_run"
        return "start"
    if _is_unattended_plan_approval(text):
        return "approve_and_run"
    if _has_any(text, ("apply", "应用", "套用")):
        return "apply"
    if _has_any(text, ("approve", "approved", "confirm", "确认", "批准", "同意")):
        return "approve_and_run"
    if _has_any(text, ("continue", "go on", "resume", "next", "继续", "推进", "下一步")):
        return "continue"
    if _has_any(text, ("diff", "patch", "补丁", "变更", "差异", "改动")):
        return "diff"
    if text in {"context", "handoff", "poll context", "run context"} or _has_any(text, ("handoff context", "run handoff")):
        return "context"
    if text in {"activity", "event", "events", "poll events", "trace"} or _has_any(text, ("event timeline", "run events")):
        return "events"
    if _is_metrics_intent(text):
        return "metrics"
    if _has_any(text, ("artifact", "plan", "review", "log", "logs", "产物", "计划", "审查", "评审", "日志", "失败", "错误", "报错", "原因", "为什么")):
        return "artifact"
    return "status"


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text))


def _has_task_intent(text: str, words: set[str] | None = None) -> bool:
    token_words = words if words is not None else _words(text)
    return bool(token_words & TASK_INTENT_WORDS) or _has_any(text, CHINESE_TASK_INTENT_WORDS)


def _is_help_intent(text: str) -> bool:
    if text in {"?", "help", "usage", "commands", "帮助", "怎么用", "如何使用", "使用说明", "新手引导", "入门"}:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if _has_any(text, ("怎么用", "如何使用", "使用说明", "使用文档", "新手引导", "入门", "帮我使用")):
        return True
    return bool(words & {"help", "usage", "commands"}) and bool(words & {"patchbay", "agent", "command", "commands"})


def _is_runs_intent(text: str) -> bool:
    if text in {
        "status",
        "runs",
        "recent",
        "recent runs",
        "list runs",
        "show runs",
        "状态",
        "运行",
        "最近运行",
        "查看运行",
        "查看最近运行",
        "打开最近运行",
        "最近任务",
        "任务列表",
        "运行列表",
    }:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if _has_any(text, ("查看运行", "查看最近运行", "打开最近运行", "显示运行", "列出运行", "运行列表", "最近任务", "任务列表")):
        return True
    if "runs" in words:
        return True
    if "status" in words:
        return bool(words & {"agent", "latest", "list", "patchbay", "recent", "run", "runs", "show", "current"})
    return "recent" in words and bool(words & {"run", "runs"})


def _is_next_step_query(text: str) -> bool:
    if not text:
        return False
    if text in {
        "next",
        "next step",
        "what next",
        "what's next",
        "what should i do next",
        "what do i do next",
        "what now",
        "now what",
        "下一步",
        "下一步是什么",
        "接下来",
        "接下来做什么",
        "现在该干什么",
        "现在做什么",
        "下一步该做什么",
        "后续怎么做",
    }:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if "next" in words and bool(words & {"do", "now", "should", "step", "what"}):
        return True
    return _has_any(text, ("下一步", "接下来做什么", "现在该干什么", "现在做什么", "后续怎么做"))


def _is_gate_status_query(text: str) -> bool:
    if not text:
        return False
    if text in {
        "blockers",
        "blocked",
        "gate",
        "gate status",
        "gates",
        "what is blocked",
        "what is blocking apply",
        "why blocked",
        "why can't i apply",
        "why cannot i apply",
        "why is apply blocked",
        "门禁",
        "门禁状态",
        "卡住了",
        "为什么不能应用",
        "为什么不能 apply",
        "为什么不能套用",
        "为什么被阻塞",
        "哪个门禁没过",
        "哪些门禁没过",
    }:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if words & {"blocked", "blocker", "blockers", "gate", "gates"}:
        return bool(words & {"apply", "current", "is", "patchbay", "run", "status", "why", "what"})
    if "apply" in text and _has_any(text, ("why", "can't", "cannot", "blocked", "blocking")):
        return True
    return _has_any(text, ("门禁", "卡住", "阻塞", "不能应用", "不能 apply", "不能套用", "没过")) and _has_any(
        text, ("为什么", "原因", "哪个", "哪些", "状态", "查看", "显示")
    )


def _config_profile_intent(text: str) -> str | None:
    if not text:
        return None
    if text in {
        "config profile show",
        "cost profile",
        "economy",
        "economy profile",
        "profile status",
        "routing profile",
        "show economy profile",
        "show routing profile",
    }:
        return "profile_show"
    words = _words(text)
    if re.search(r"providers\.[a-z0-9_-]+\.command", text) and bool(
        words & {"current", "is", "missing", "read", "show", "status", "what", "why", "inspect"}
    ):
        return "profile_show"
    if _is_routing_show_query(text, words):
        return "profile_show"
    if text in {
        "apply economy profile",
        "enable economy profile",
        "patchbay config profile apply economy",
        "use economy profile",
        "use economy routing",
    }:
        return "profile_apply"
    if _has_any(text, ("启用经济路由", "应用经济路由", "经济型路由", "经济路由", "使用便宜模型", "使用低成本模型")):
        return "profile_apply"
    if _has_any(text, ("查看经济路由", "查看路由配置", "路由状态", "经济路由状态")):
        return "profile_show"
    if _is_task_message_that_mentions_routing_tool(text, words):
        return None
    chinese_profile_intent = _chinese_economy_profile_intent(text)
    if chinese_profile_intent:
        return chinese_profile_intent
    routing_scope = {"cost", "deepseek", "economy", "profile", "reasonix", "route", "routing"}
    if "profile" in words and bool(words & {"show", "status", "read", "inspect"}):
        return "profile_show" if bool(words & routing_scope) else None
    if bool(words & {"deepseek", "economy", "reasonix"}) and bool(words & {"show", "status", "read", "inspect"}):
        return "profile_show"
    apply_words = {"apply", "assign", "delegate", "enable", "handle", "route", "run", "switch", "use"}
    write_fix_words = {"bulk", "fix", "implementation", "repair", "routine", "simple", "write", "writer"}
    if bool(words & {"deepseek", "economy", "reasonix"}) and bool(words & apply_words):
        return "profile_apply"
    if bool(words & {"deepseek", "economy", "reasonix"}) and bool(words & write_fix_words) and (
        bool(words & {"for", "on", "to"}) or _has_any(text, ("用", "使用", "让", "交给", "给", "走", "路由", "干", "跑", "省钱"))
    ):
        return "profile_apply"
    if bool(words & {"cheap", "cost", "lower", "low", "economy"}) and bool(words & {"model", "models", "routing", "route", "profile"}):
        return "profile_apply" if bool(words & (apply_words | write_fix_words | {"optimize"})) else "profile_show"
    return None


def _is_task_message_that_mentions_routing_tool(text: str, words: set[str]) -> bool:
    if not _has_task_intent(text, words):
        return False
    if _has_any(
        text,
        (
            "便宜",
            "低价",
            "廉价",
            "成本更低",
            "降低成本",
            "降本",
            "低成本",
            "经济",
            "省钱",
            "性价比",
            "大量",
            "简单",
            "低难度",
            "路由",
            "交给",
            "切到",
            "换成",
        ),
    ):
        return False
    return _has_any(text, ("流程", "功能", "模块", "页面", "系统", "代码", "bug", "问题", "任务"))


def _is_routing_show_query(text: str, words: set[str]) -> bool:
    question_words = {"are", "can", "current", "do", "does", "how", "is", "should", "status", "what", "which", "who", "will"}
    work_words = {"fix", "implementation", "repair", "write", "writer"}
    model_words = {"model", "models", "provider", "providers"}
    economy_words = {"cheap", "cheaper", "cost", "deepseek", "economy", "low", "lower", "reasonix"}
    has_question_shape = "?" in text or "？" in text or bool(words & question_words)
    if has_question_shape and bool(words & model_words) and bool(words & (work_words | {"phase", "phases", "profile", "route", "routing"})):
        return True
    if has_question_shape and bool(words & work_words) and bool(words & economy_words):
        return True
    if has_question_shape and bool(words & {"profile", "route", "routing"}) and bool(words & (economy_words | model_words)):
        return True
    if bool(words & {"profile", "route", "routing"}) and bool(words & {"active", "configured", "current", "read", "show", "status", "using"}):
        return True
    chinese_model_query = _has_any(
        text,
        (
            "什么模型",
            "哪个模型",
            "哪种模型",
            "什么 provider",
            "哪个 provider",
            "当前模型",
            "现在模型",
            "模型状态",
            "当前路由",
            "现在路由",
            "路由状态",
        ),
    )
    if chinese_model_query and _has_any(text, ("写手", "写代码", "实现", "修复", "路由", "模型", "provider", "便宜", "低成本", "deepseek", "reasonix")):
        return True
    return False


def _chinese_economy_profile_intent(text: str) -> str | None:
    if not text:
        return None
    economy_terms = (
        "deepseek",
        "便宜",
        "低价",
        "廉价",
        "成本更低",
        "降低成本",
        "降本",
        "低成本",
        "经济",
        "省钱",
        "性价比",
    )
    policy_work_terms = (
        "写手",
        "写作",
        "写代码",
        "简单工作",
        "简单任务",
        "大量",
        "低难度",
        "便宜模型",
        "低成本模型",
        "writer",
        "write",
        "fix",
        "repair",
        "implementation",
    )
    if not _has_any(text, economy_terms + ("reasonix",)):
        return None
    if _has_any(text, ("查看", "状态", "检查", "当前", "现在", "只看", "读一下")):
        return "profile_show"
    if _has_task_intent(text) and not _has_any(text, economy_terms) and not _has_any(text, policy_work_terms):
        return None
    if not _has_any(text, policy_work_terms + ("实现", "修复", "writer/fix")):
        return None
    if _has_any(text, ("用", "使用", "让", "交给", "给", "走", "路由", "干", "跑", "配置", "启用", "切到", "换成")):
        return "profile_apply"
    return None


def _is_custom_economy_provider_setup_intent(text: str) -> bool:
    if not text:
        return False
    words = _words(text)
    if bool(words & {"support", "feature"}) and bool(words & {"add", "build", "implement"}):
        return False
    setup_words = {"add-cli", "configure", "install", "register", "setup"}
    economy_words = {"cheap", "cheaper", "cost", "deepseek", "economy", "low", "lower"}
    provider_words = {"cli", "provider", "providers", "wrapper", "writer"}
    if bool(words & setup_words) and bool(words & economy_words) and bool(words & provider_words):
        return True
    return _has_any(text, ("配置", "注册", "安装", "接入")) and _has_any(
        text, ("deepseek", "便宜", "低成本", "经济", "省钱", "性价比")
    ) and _has_any(text, ("provider", "cli", "wrapper", "写手", "写代码", "实现", "修复"))


def _is_custom_provider_command_configure_intent(text: str) -> bool:
    if not text or _has_task_intent(text):
        return False
    if "configure_economy_provider_command" in text:
        return True
    if "--set-value" in text and re.search(r"providers\.[a-z0-9_-]+\.command", text):
        return True
    if re.search(r"providers\.[a-z0-9_-]+\.command\s*(?:=|to|as)\s+\S", text):
        return True
    words = _words(text)
    command_scope = bool(words & {"command", "cmd", "executable", "path", "wrapper"})
    provider_scope = bool(words & {"provider", "providers", "economy", "cheap_writer", "writer", "wrapper"})
    setup_scope = bool(words & {"configure", "set", "setup", "install", "use", "using"})
    return command_scope and provider_scope and setup_scope


def _is_reasonix_command_configure_intent(text: str) -> bool:
    if text in {
        "configure reasonix",
        "configure reasonix command",
        "configure commands.reasonix",
        "set reasonix command",
        "set commands.reasonix",
        "patchbay config --set-key commands.reasonix --set-value reasonix",
    }:
        return True
    words = _words(text)
    if "reasonix" not in words:
        return False
    chinese_command_scope = "commands.reasonix" in text or _has_any(text, ("命令", "路径", "可执行", "程序"))
    if chinese_command_scope:
        if _has_any(text, ("配置", "设置", "设为", "指定", "安装", "命令是", "路径是")):
            return True
        if _has_any(text, ("使用", "用")) and not _has_task_intent(text, words):
            return True
    return bool(words & {"configure", "set", "setup", "install"}) and bool(words & {"command", "commands", "executable", "path"})


def _is_setup_intent(text: str) -> bool:
    if text in {
        "setup",
        "patchbay setup",
        "setup patchbay",
        "install patchbay",
        "patchbay install",
        "install skill",
        "install codex skill",
        "install patchbay skill",
        "patchbay skill install",
        "mcp install",
        "install mcp",
        "setup mcp",
        "register mcp",
        "configure mcp",
        "安装 skill",
        "安装 codex skill",
        "安装 patchbay skill",
        "安装 codex 技能",
        "安装 patchbay 技能",
        "注册 mcp",
        "安装 mcp",
        "配置 mcp",
        "接入 mcp",
    }:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if _has_any(text, ("初始化 patchbay", "安装 patchbay", "配置 patchbay", "设置 patchbay", "帮助我配置 patchbay", "帮我配置 patchbay")):
        return True
    if _has_any(text, ("安装", "初始化", "配置", "接入", "注册")) and _explicit_setup_host_from_message(text):
        return True
    if bool(words & {"configure", "install", "register", "setup"}) and bool(words & {"mcp", "skill"}) and _explicit_setup_host_from_message(text):
        return True
    if bool(words & {"configure", "install", "register", "setup"}) and "patchbay" in words and bool(words & {"mcp", "skill"}):
        return True
    if "patchbay" not in words:
        return False
    if _has_any(text, ("帮助我配置", "帮我配置", "配置", "设置", "初始化", "接入")):
        return True
    return bool(words & {"install", "installation", "setup"})


def _is_local_mode_intent(text: str) -> bool:
    if _has_task_intent(text):
        return False
    return _is_mcp_avoidance_intent(text, _words(text))


def _setup_host_from_message(text: str) -> str:
    return _explicit_setup_host_from_message(text) or "codex"


def _setup_options_from_message(text: str) -> dict[str, bool]:
    normalized = text.lower()
    words = _words(normalized)
    explicit_skip_mcp = _is_mcp_avoidance_intent(normalized, words) or _has_skip_scope(words, "mcp") or _has_any(
        normalized,
        (
            "without mcp",
            "no mcp",
            "omit mcp",
            "mcp false",
            "mcp off",
            "avoid mcp",
            "do not use mcp",
            "do not register mcp",
            "dont use mcp",
            "dont register mcp",
            "don't use mcp",
            "don't register mcp",
            "local only",
            "local-only",
            "skill only",
            "不注册 mcp",
            "不要注册 mcp",
            "跳过 mcp",
            "不用 mcp",
            "不要 mcp",
            "只装 skill",
            "只安装 skill",
        ),
    )
    explicit_skip_skill = _has_skip_scope(words, "skill") or _has_any(
        normalized,
        (
            "without skill",
            "no skill",
            "omit skill",
            "skill false",
            "skill off",
            "do not install skill",
            "dont install skill",
            "don't install skill",
            "不安装 skill",
            "不要安装 skill",
            "跳过 skill",
            "不用 skill",
            "只注册 mcp",
        ),
    )
    skill_only = (
        not explicit_skip_skill
        and "skill" in words
        and "mcp" not in words
        and bool(words & {"configure", "install", "setup"})
    )
    mcp_only = (
        not explicit_skip_mcp
        and "mcp" in words
        and "skill" not in words
        and bool(words & {"configure", "install", "register", "setup"})
    )
    return {
        "skip_mcp": explicit_skip_mcp or skill_only,
        "skip_skill": explicit_skip_skill or mcp_only,
    }


def _is_mcp_avoidance_intent(text: str, words: set[str] | None = None) -> bool:
    token_words = words if words is not None else _words(text)
    if _has_task_intent(text, token_words):
        return False
    if _has_any(text, IMPLICIT_LOCAL_TOOL_PREFERENCE_PHRASES):
        return True
    if "mcp" not in token_words and "mcp" not in text:
        return False
    if bool(
        token_words
        & {
            "avoid",
            "disable",
            "except",
            "instead",
            "local",
            "localonly",
            "no",
            "omit",
            "skip",
            "without",
        }
    ) and (
        "mcp" in token_words or "mcp" in text
    ):
        return True
    return _has_any(
        text,
        (
            "avoid mcp",
            "do not use mcp",
            "don't use mcp",
            "dont use mcp",
            "no mcp",
            "without mcp",
            "local only",
            "local-only",
            "skill only",
            "browser skill instead of mcp",
            "chrome skill instead of mcp",
            "built-in browser instead of mcp",
            "use browser skill",
            "use chrome skill",
            "不要用 mcp",
            "不要用这个 mcp",
            "不要用这个mcp",
            "不要再用 mcp",
            "不要再用这个 mcp",
            "不要再用这个mcp",
            "不走 mcp",
            "不走mcp",
            "别用 mcp",
            "别用这个 mcp",
            "别用这个mcp",
            "别再用 mcp",
            "别再用这个 mcp",
            "别再用这个mcp",
            "不用 mcp",
            "不用这个 mcp",
            "不用这个mcp",
            "走本地",
            "走本地模式",
            "只用本地",
            "只用本地工具",
            "少用 mcp",
            "少用这个 mcp",
            "少用这个mcp",
            "少用 mcp 工具",
            "少用这个 mcp 工具",
            "不要 mcp",
            "自带浏览器",
            "浏览器 skill",
            "chrome skill",
            "只用 skill",
            "只装 skill",
            "只安装 skill",
            "本地模式",
        ),
    )


def _has_skip_scope(words: set[str], scope: str) -> bool:
    if f"skip_{scope}" in words:
        return True
    if scope not in words:
        return False
    return bool(words & {"disable", "except", "no", "omit", "skip", "without"})


def _explicit_setup_host_from_message(text: str) -> str | None:
    normalized = re.sub(r"[\s_]+", " ", text.strip().lower().replace("-", " ").replace("=", " "))
    if not normalized:
        return None
    host_phrases = sorted({_normalize_host_phrase(phrase) for phrase in HOST_ALIASES}, key=len, reverse=True)
    for phrase in host_phrases:
        if re.search(rf"(?:--host\s+|host\s+|for\s+|to\s+)?{re.escape(phrase)}\b", normalized):
            if phrase == "codex" and not re.search(r"(?:--host\s+|host\s+|for\s+|to\s+)codex\b", normalized):
                continue
            return normalize_mcp_host(phrase)
    return None


def _normalize_host_phrase(phrase: str) -> str:
    return re.sub(r"[\s_]+", " ", phrase.strip().lower().replace("-", " "))


def _is_metrics_intent(text: str) -> bool:
    if text in {
        "cost",
        "costs",
        "efficiency",
        "metrics",
        "performance",
        "run metrics",
        "stats",
        "statistics",
        "token usage",
        "tokens",
        "成本",
        "耗时",
        "效率",
        "性价比",
    }:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if _has_any(text, ("成本", "耗时", "效率", "性价比")) and _has_any(text, ("看", "查看", "显示", "统计", "报告", "读")):
        return True
    metric_words = {"cost", "costs", "duration", "efficiency", "metrics", "performance", "stats", "statistics", "token", "tokens"}
    scope_words = {"current", "latest", "patchbay", "run", "this", "usage"}
    return bool(words & metric_words) and bool(words & scope_words)


def _is_run_bound_intent(text: str) -> bool:
    if text in {
        "apply",
        "approve",
        "approved",
        "artifact",
        "artifacts",
        "cancel",
        "cancel background job",
        "cancel job",
        "confirm",
        "continue",
        "context",
        "cost",
        "diff",
        "events",
        "handoff",
        "handoff context",
        "metrics",
        "log",
        "logs",
        "next",
        "patch",
        "poll context",
        "poll events",
        "review",
        "resume",
        "run context",
        "run handoff",
        "stop background job",
        "stop job",
        "tokens",
        "trace",
        "应用",
        "批准",
        "成本",
        "确认",
        "继续",
        "下一步",
        "耗时",
        "效率",
        "补丁",
        "变更",
        "计划",
        "日志",
    }:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if _is_background_cancel_intent(text):
        return True
    if _is_chinese_run_bound_request(text):
        return True
    if _has_any(text, ("补丁", "变更", "差异", "改动", "事件", "跟踪", "轨迹", "日志", "产物", "计划", "审查", "评审")) and _has_any(
        text, ("看", "查看", "打开", "显示", "读", "列出")
    ):
        return True
    if _has_any(text, ("失败", "错误", "报错", "失败原因", "错误原因")) and _has_any(text, ("看", "查看", "打开", "显示", "读", "为什么", "原因")):
        return True
    if words & {"approve", "approved", "confirm"}:
        return bool(words & {"approval", "current", "latest", "patchbay", "plan", "run", "this"})
    if words & {"continue", "resume"}:
        return bool(words & {"current", "last", "latest", "phase", "run", "step", "this", "worktree"})
    if "apply" in words:
        return bool(words & {"changes", "diff", "final", "patch", "reviewed"})
    if "next" in words:
        return bool(words & {"phase", "run", "step"})
    if words & {"artifact", "context", "diff", "events", "log", "logs", "patch", "trace"}:
        return bool(words & {"current", "get", "last", "latest", "open", "run", "show", "this", "view"})
    if words & {"error", "errors", "fail", "failed", "failure"}:
        return bool(words & {"current", "did", "inspect", "last", "latest", "open", "reason", "run", "show", "this", "view", "what", "why"})
    if "review" in words:
        return bool(words & {"current", "get", "last", "latest", "open", "run", "show", "this", "view"})
    return False


def _is_chinese_run_bound_request(text: str) -> bool:
    if _has_any(text, ("取消后台", "停止后台", "中止后台", "取消任务", "停止任务", "中止任务")):
        return True
    if _has_any(text, ("继续", "推进", "下一步", "接着", "恢复")):
        return True
    if _has_any(text, ("确认", "批准", "同意")) and _has_any(text, ("计划", "方案", "plan")):
        return True
    if _has_any(text, ("应用补丁", "应用变更", "应用改动", "应用修改", "套用补丁", "套用变更", "套用改动", "合并补丁")):
        return True
    return False


def _is_background_cancel_intent(text: str) -> bool:
    if not text:
        return False
    if text in {"cancel", "cancel job", "cancel background job", "stop job", "stop background job"}:
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if bool(words & {"abort", "cancel", "stop", "terminate"}) and bool(words & {"background", "job", "run", "worker"}):
        return True
    return _has_any(text, ("取消后台", "停止后台", "中止后台", "取消任务", "停止任务", "中止任务"))


def _is_gate_changing_run_request(text: str) -> bool:
    words = _words(text)
    if words & {"approve", "approved", "confirm", "continue", "resume"}:
        return True
    if "apply" in words:
        return True
    if _has_any(text, ("继续", "推进", "下一步", "接着", "恢复")):
        return True
    if _has_any(text, ("确认", "批准", "同意")) and _has_any(text, ("计划", "方案", "plan")):
        return True
    if _has_any(text, ("应用补丁", "应用变更", "应用改动", "应用修改", "套用补丁", "套用变更", "套用改动", "合并补丁")):
        return True
    return False


def _is_doctor_intent(text: str) -> bool:
    if text in {"doctor", "readiness", "diagnose", "diagnostic", "diagnostics", "诊断", "自检", "环境检查", "检查环境"}:
        return True
    if _has_any(text, ("就绪", "安装检查", "配置检查", "环境检查", "检查环境", "环境自检", "项目自检")):
        return True
    words = _words(text)
    if _has_task_intent(text, words):
        return False
    if _explicit_setup_host_from_message(text) and (
        _has_any(text, ("检查", "自检", "环境", "就绪"))
        or bool(words & {"check", "checks", "doctor", "diagnose", "diagnostic", "diagnostics", "readiness"})
    ):
        return True
    setup_words = {
        "check",
        "checks",
        "config",
        "configuration",
        "install",
        "installation",
        "mcp",
        "patchbay",
        "readiness",
        "setup",
        "skill",
    }
    if "readiness" in words:
        return True
    if words & {"diagnose", "diagnostic", "diagnostics"}:
        return bool(words & setup_words)
    return "doctor" in words and bool(words & (setup_words | {"run", "show"}))


def _safe_economy_target(root: Path) -> dict[str, Any]:
    try:
        return economy_target(load_config(root))
    except Exception:
        return {"provider": service.ECONOMY_PROVIDER, "model": service.ECONOMY_MODEL, "label": "Reasonix/DeepSeek"}


def _help_response(root: Path, *, run_id: str | None = None, include: dict[str, Any] | None = None) -> dict[str, Any]:
    target = _safe_economy_target(root)
    target_label = str(target.get("label") or _route_label(target))
    capabilities = [
        {
            "name": "setup",
            "summary": "Send `patchbay setup` for Codex or `patchbay setup for Claude Desktop` / `install patchbay for Gemini CLI` to initialize project files, local config, Skill installation, host MCP guidance, a doctor summary, top-level recommendations, safe actions[], and action_groups[]. Send `patchbay setup without MCP` for local-only setup, standalone `please don't use MCP` / `no MCP` / `use Chrome Skill` / `use Chrome Skill instead of MCP` / `用你自带的浏览器功能` / `少用这个MCP` / `不要用这个MCP` / `不走 MCP` / `走本地模式` / `只用本地工具` for local_mode guidance, `install Codex Skill` for Skill-only setup, or `register MCP for Claude Desktop` for MCP-only registration.",
        },
        {
            "name": "agent-skill-contract",
            "summary": "MCP hosts, desktop UIs, and Skill-only clients should render structured Agent fields instead of parsing prose. The bundled Codex Skill uses a compact SKILL.md entrypoint and loads install / Agent-response references only when needed.",
            "contract": skill_contract_summary(),
        },
        {
            "name": "start",
            "summary": "Send a task to create a plan; implementation still waits for explicit plan approval.",
        },
        {
            "name": "readiness",
            "summary": "Send `readiness`, `readiness for Claude Desktop`, or `检查 Gemini 命令行环境` to inspect host-aware setup without creating a run.",
        },
        {
            "name": "economy-profile",
            "summary": f"Send `show economy profile` or ask `what model will write/fix use` for a read-only routing check; send `apply economy profile` to route high-volume write/fix work to {target_label} without starting a run.",
        },
        {
            "name": "custom-economy-provider",
            "summary": "Send `configure DeepSeek provider` to get the safe one-command template for registering a low-cost CLI writer, `configure DeepSeek provider to <command>` to register it immediately, or prompts like `简单 writer/fix 用 DeepSeek 省钱` / `降本，让简单 writer/fix 走低价模型` to apply economy routing for simple writer/fix work without starting a run. Send `configure economy provider command to <path>` to repair the active custom provider command without starting a run. If the custom provider command later fails readiness or metrics checks, clients should render the returned `configure_economy_provider_command` command action before falling back to inspection.",
        },
        {
            "name": "reasonix-command",
            "summary": "Send `configure reasonix command` or `configure reasonix command to <path>` to set the Reasonix executable used by the economy write/fix route.",
        },
        {
            "name": "status",
            "summary": "Send `status` without a run_id to list recent runs, or with a run_id to inspect one run.",
        },
        {
            "name": "metrics",
            "summary": "Send `metrics`, `cost`, or `tokens` to inspect the latest run, or include a run_id to inspect a specific run's efficiency evidence.",
        },
        {
            "name": "unattended-approval",
            "summary": "When a concrete run_id is selected, phrases such as `don't ask me`, `full access`, `无需向我确认`, or `完全访问权限` can approve the plan and start write/test/review autopilot; without a run_id they return missing_run guidance, and final apply still needs apply_approved confirmation.",
        },
        {
            "name": "continue",
            "summary": "Send `continue` with a run_id to advance the next safe phase.",
        },
        {
            "name": "apply",
            "summary": "Send `apply` only after tests and review pass; it still requires apply_approved confirmation.",
        },
    ]
    if target.get("provider") != "reasonix_cli":
        capabilities = [item for item in capabilities if item["name"] != "reasonix-command"]
    actions = _help_actions(target)
    next_actions = _help_next_actions(target)
    reply = "Patchbay Agent can run setup, start a gated run, report readiness, apply economy routing, list recent runs, continue a run, show artifacts/diff, and apply only after explicit approval."
    if run_id:
        current = service.status(root, run_id)
        diagnosis = _gate_diagnosis(current)
        run_actions = _next_step_actions(run_id, current, include_open_run=False)
        return _agent_response(
            root,
            run_id,
            action="help",
            reply=reply + f" Current run {run_id} is {current.get('status') or 'unknown'}; see gate_diagnosis.next_action for the selected-run next step.",
            include=include,
            status_data=current,
            extra={
                "capabilities": capabilities,
                "gate_diagnosis": diagnosis,
                "next_action": _next_step_primary_action(current),
                "next_actions": _dedupe_strings([*_next_actions_for_status(current), *next_actions]),
                "actions": _dedupe_actions([*run_actions, *actions]),
            },
        )
    return _stateless_response(
        action="help",
        reply=reply,
        next_actions=next_actions,
        extra={"capabilities": capabilities, "actions": actions},
    )


def _help_next_actions(target: dict[str, Any]) -> list[str]:
    actions = [
        "setup",
        "setup without MCP",
        "local mode",
        "install Codex Skill",
        "skill doctor",
        "print Skill contract",
        "register MCP for Claude Desktop",
        "start",
        "readiness",
        "configure DeepSeek provider",
        "apply economy profile",
        "runs",
    ]
    if target.get("provider") == "reasonix_cli":
        actions.insert(5, "configure reasonix command")
    return actions


def _help_actions(target: dict[str, Any]) -> list[dict[str, Any]]:
    target_label = str(target.get("label") or _route_label(target))
    actions = [
        {
            "id": "run_setup",
            "label": "Run setup",
            "kind": "local_agent",
            "message": "patchbay setup",
            "host": "codex",
            "safe": True,
            "reason": "Initialize local config, Skill installation, MCP guidance, and readiness checks.",
        },
        {
            "id": "run_local_setup",
            "label": "Run local setup",
            "kind": "local_agent",
            "message": "patchbay setup without MCP",
            "host": "codex",
            "safe": True,
            "reason": "Initialize local config and Codex Skill installation without attempting MCP host registration.",
        },
        {
            "id": "use_local_mode",
            "label": "Use local mode",
            "kind": "local_agent",
            "message": "走本地模式，不走 MCP",
            "host": "codex",
            "safe": True,
            "reason": "Switch the conversational flow to local CLI/Skill actions and hide MCP probe/register follow-ups.",
        },
        {
            "id": "install_skill_only",
            "label": "Install Codex Skill",
            "kind": "local_agent",
            "message": "install Codex Skill",
            "host": "codex",
            "safe": True,
            "reason": "Install the Codex Skill without attempting MCP host registration.",
        },
        {
            "id": "check_skill_contract",
            "label": "Check Skill contract",
            "kind": "command",
            "command": "patchbay skill doctor codex --json",
            "safe": True,
            "reason": "Validate that the installed Codex Skill and progressive references match the bundled source.",
        },
        {
            "id": "print_skill_contract",
            "label": "Print Skill contract",
            "kind": "command",
            "command": "patchbay skill print codex",
            "safe": True,
            "reason": "Inspect the compact SKILL.md plus references/install.md and references/agent-contract.md without using MCP.",
        },
        {
            "id": "setup_claude_code",
            "label": "Setup Claude Code",
            "kind": "local_agent",
            "message": "patchbay setup for claude-code",
            "host": "claude-code",
            "safe": True,
            "reason": "Initialize Patchbay and return Claude Code MCP registration guidance.",
        },
        {
            "id": "setup_claude_desktop",
            "label": "Setup Claude Desktop",
            "kind": "local_agent",
            "message": "patchbay setup for claude-desktop",
            "host": "claude-desktop",
            "safe": True,
            "reason": "Initialize Patchbay and return Claude Desktop MCP registration guidance.",
        },
        {
            "id": "register_mcp_claude_desktop",
            "label": "Register Claude Desktop MCP",
            "kind": "local_agent",
            "message": "register MCP for Claude Desktop",
            "host": "claude-desktop",
            "safe": True,
            "reason": "Register the Claude Desktop MCP server without reinstalling the Codex Skill.",
        },
        {
            "id": "setup_gemini",
            "label": "Setup Gemini CLI",
            "kind": "local_agent",
            "message": "install patchbay for gemini",
            "host": "gemini",
            "safe": True,
            "reason": "Initialize Patchbay and return Gemini CLI MCP registration guidance.",
        },
        {
            "id": "start_new_task",
            "label": "Start new task",
            "kind": "focus_composer",
            "safe": True,
            "reason": "Focus the composer so a new Patchbay plan can be started.",
        },
        {
            "id": "open_readiness",
            "label": "Open readiness",
            "kind": "local_agent",
            "message": "readiness",
            "host": "codex",
            "safe": True,
            "reason": "Run read-only setup diagnostics before starting or resuming work.",
        },
        {
            "id": "readiness_claude_code",
            "label": "Check Claude Code readiness",
            "kind": "local_agent",
            "message": "readiness for claude-code",
            "host": "claude-code",
            "safe": True,
            "reason": "Run read-only Patchbay readiness checks for Claude Code MCP registration.",
        },
        {
            "id": "readiness_claude_desktop",
            "label": "Check Claude Desktop readiness",
            "kind": "local_agent",
            "message": "readiness for claude-desktop",
            "host": "claude-desktop",
            "safe": True,
            "reason": "Run read-only Patchbay readiness checks for Claude Desktop MCP registration.",
        },
        {
            "id": "readiness_gemini",
            "label": "Check Gemini CLI readiness",
            "kind": "local_agent",
            "message": "readiness for gemini",
            "host": "gemini",
            "safe": True,
            "reason": "Run read-only Patchbay readiness checks for Gemini CLI MCP registration.",
        },
        {
            "id": "apply_economy_profile",
            "label": "Apply economy profile",
            "kind": "local_agent",
            "message": "apply economy profile",
            "safe": True,
            "reason": f"Route high-volume write/fix work to the {target_label} economy profile.",
        },
        {
            "id": "configure_deepseek_provider",
            "label": "Configure DeepSeek provider",
            "kind": "local_agent",
            "message": "configure DeepSeek provider",
            "safe": True,
            "reason": "Open the conversational custom-provider setup path and return a safe copyable command template.",
        },
        _custom_provider_setup_action(),
        {
            "id": "show_runs",
            "label": "Show runs",
            "kind": "local_agent",
            "message": "status",
            "safe": True,
            "reason": "List recent Patchbay runs without advancing any run gate.",
        },
    ]
    if target.get("provider") == "reasonix_cli":
        actions.insert(
            4,
            {
                "id": "configure_reasonix_command",
                "label": "Configure Reasonix",
                "kind": "local_agent",
                "message": "configure reasonix command",
                "command": "patchbay config --set-key commands.reasonix --set-value reasonix",
                "safe": True,
                "reason": "Set the Reasonix executable used by the economy write/fix route.",
            },
        )
    return actions


def _custom_provider_setup_action() -> dict[str, Any]:
    return {
        "id": "configure_custom_economy_provider",
        "label": "Configure cheap writer provider",
        "kind": "command",
        "command": _custom_provider_setup_command(),
        "safe": True,
        "reason": "Register a low-cost CLI writer and immediately route write/fix work through it.",
    }


def _custom_provider_setup_command() -> str:
    return (
        "patchbay config provider add-cli cheap_writer --roles write fix "
        "--command <deepseek-writer-command> --output-contract writer_diff "
        "--activate-economy --economy-model deepseek-chat --economy-label \"DeepSeek cheap writer\""
    )


def _custom_provider_command_from_message(message: str) -> str:
    text = (message or "").strip()
    patterns = (
        r"--set-value\s+(.+)$",
        r"--command\s+(.+?)(?:\s+--[a-z0-9-]+|$)",
        r"providers\.[a-z0-9_-]+\.command\s*(?:=|to|as)\s*(.+)$",
        r"\bdeepseek\s+provider\s+(?:command|cmd|executable|wrapper)\s+(.+)$",
        r"\b(?:with|using|use)\s+(?:command|cmd|executable|wrapper)\s+(.+)$",
        r"\b(?:command|cmd|executable|wrapper|path)\s+(.+)$",
        r"\b(?:to|as|at)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = _clean_custom_provider_command_value(match.group(1))
        if value:
            return value
    return ""


def _clean_custom_provider_command_value(value: str) -> str:
    cleaned = _clean_reasonix_command_value(value)
    if cleaned.lower() in {
        "cheap writer",
        "deepseek",
        "deepseek provider",
        "provider",
        "writer",
        "<command>",
        "<deepseek-writer-command>",
    }:
        return ""
    return cleaned


def _setup_response(root: Path, message: str) -> dict[str, Any]:
    host = _setup_host_from_message(message)
    result = run_setup(root, host=host, **_setup_options_from_message(message))
    next_actions = list(result.get("next_actions") or [])
    actions = list(result.get("actions") or [])
    recommendations = list(result.get("recommendations") or [])
    reply = "Patchbay setup completed."
    if next_actions:
        reply = "Patchbay setup completed with follow-up steps: " + " ".join(next_actions)
    if recommendations:
        reply += " Recommendations: " + " ".join(recommendations)
    return _stateless_response(
        action="setup",
        reply=reply,
        ok=bool(result.get("ok")),
        error=None if result.get("ok") else reply,
        next_actions=next_actions or ["readiness", "start"],
        extra={
            "setup": result,
            "setup_host": result.get("setup_host") or host,
            "routing": result.get("routing"),
            "recommendations": recommendations,
            "actions": actions,
        },
    )


def _local_mode_response(root: Path, message: str, *, run_id: str | None = None) -> dict[str, Any]:
    runs_dir = root / ".ai" / "runs"
    recent = list(service.runs(root, limit=1).get("runs") or []) if runs_dir.exists() else []
    actions: list[dict[str, Any]] = [
        {
            "id": "open_local_readiness",
            "label": "Open local readiness",
            "kind": "local_agent",
            "message": "readiness without MCP",
            "host": "codex",
            "safe": True,
            "reason": "Run local-only readiness checks without MCP probing or registration follow-ups.",
        },
        {
            "id": "run_local_setup",
            "label": "Run local setup",
            "kind": "local_agent",
            "message": "patchbay setup without MCP",
            "host": "codex",
            "safe": True,
            "reason": "Initialize local config and the Codex Skill without attempting MCP registration.",
        },
        {
            "id": "install_skill_only",
            "label": "Install Codex Skill",
            "kind": "local_agent",
            "message": "install Codex Skill",
            "host": "codex",
            "safe": True,
            "reason": "Install the Codex Skill so Patchbay can be used without MCP tools.",
        },
        {
            "id": "show_runs",
            "label": "Show runs",
            "kind": "local_agent",
            "message": "status",
            "safe": True,
            "reason": "List recent Patchbay runs without advancing any gate.",
        },
    ]
    recent_run: dict[str, Any] | None = None
    if run_id:
        try:
            current_status = service.status(root, run_id)
            recent_run = {
                "run_id": run_id,
                "status": current_status.get("status"),
                "task": current_status.get("task"),
            }
        except Exception:
            recent_run = {"run_id": run_id}
    elif recent:
        recent_run = recent[0]
    if recent_run:
        actions.insert(
            0,
            {
                "id": "open_latest_run",
                "label": "Open latest run",
                "kind": "open_run",
                "run_id": recent_run.get("run_id"),
                "safe": True,
                "reason": "Open the latest Patchbay run before taking any gated action.",
            },
        )
    extra: dict[str, Any] = {
        "local_mode": {
            "skip_mcp": True,
            "requires_run_for_unattended_approval": True,
            "apply_requires_confirmation": True,
        },
        "recent_run": recent_run,
        "actions": actions,
    }
    if run_id:
        extra["run_id"] = run_id
    reply = (
        "Local-only mode selected. Use the local CLI/Skill path and avoid MCP probes or registration follow-ups. "
        "Unattended permission phrases can approve a selected plan run, but a run_id must be selected first and final apply still requires apply confirmation."
    )
    return _stateless_response(
        action="local_mode",
        reply=reply,
        next_actions=["readiness without MCP", "setup without MCP", "install Codex Skill", "runs"],
        extra=extra,
    )


def _runs_response(root: Path) -> dict[str, Any]:
    report = service.runs(root, limit=5)
    recent = list(report.get("runs") or [])
    if recent:
        latest = recent[0]
        reply = f"Latest Patchbay run is {latest.get('run_id')} ({latest.get('status') or 'unknown'}). Open that run before choosing any gated action."
        next_actions = ["open latest run", "readiness"]
        actions = [
            {
                "id": "open_latest_run",
                "label": "Open latest run",
                "kind": "open_run",
                "run_id": latest.get("run_id"),
                "safe": True,
                "reason": "Open the latest Patchbay run without advancing any gate.",
            },
            {
                "id": "open_readiness",
                "label": "Open readiness",
                "kind": "local_agent",
                "message": "readiness",
                "safe": True,
                "reason": "Run read-only setup diagnostics before starting or resuming work.",
            },
        ]
    else:
        reply = "No Patchbay runs found. Send a task to start with a plan, or send readiness to check setup."
        next_actions = ["start", "readiness"]
        actions = [
            {
                "id": "start_new_task",
                "label": "Start new task",
                "kind": "focus_composer",
                "safe": True,
                "reason": "Focus the composer so a new Patchbay plan can be started.",
            },
            {
                "id": "open_readiness",
                "label": "Open readiness",
                "kind": "local_agent",
                "message": "readiness",
                "safe": True,
                "reason": "Run read-only setup diagnostics before starting work.",
            },
        ]
    return _stateless_response(
        action="runs",
        reply=reply,
        next_actions=next_actions,
        extra={"runs": report, "recent_run": recent[0] if recent else None, "actions": actions},
    )


def _next_step_response(root: Path, *, run_id: str | None, include: dict[str, Any] | None = None) -> dict[str, Any]:
    if run_id:
        current = service.status(root, run_id)
        return _agent_response(
            root,
            run_id,
            action="next_step",
            reply=_next_step_reply(run_id, current),
            include=include,
            extra={
                "next_action": _next_step_primary_action(current),
                "actions": _next_step_actions(run_id, current, include_open_run=False),
            },
        )

    report = service.runs(root, limit=5)
    recent = list(report.get("runs") or [])
    if not recent:
        return _stateless_response(
            action="next_step",
            reply="No Patchbay runs found. Send a task to start with a plan, or send readiness to check setup.",
            next_actions=["start", "readiness"],
            extra={
                "runs": report,
                "recent_run": None,
                "actions": [
                    {
                        "id": "start_new_task",
                        "label": "Start new task",
                        "kind": "focus_composer",
                        "safe": True,
                        "reason": "Focus the composer so a new Patchbay plan can be started.",
                    },
                    {
                        "id": "open_readiness",
                        "label": "Open readiness",
                        "kind": "local_agent",
                        "message": "readiness",
                        "safe": True,
                        "reason": "Run read-only setup diagnostics before starting work.",
                    },
                ],
            },
        )

    latest = recent[0]
    latest_run_id = str(latest.get("run_id") or "")
    current = service.status(root, latest_run_id) if latest_run_id else dict(latest)
    next_actions = _dedupe_strings(["open latest run", *_next_actions_for_status(current), "readiness"])
    run_reference = {
        "run_id": latest.get("run_id"),
        "status": latest.get("status") or current.get("status"),
        "task": latest.get("task"),
        "updated_at": latest.get("updated_at"),
        "suggested_message": "open latest run",
        "safe_actions": ["open_run", "status", "events"],
        "next_actions": _next_actions_for_status(current),
        "next_action": _next_step_primary_action(current),
    }
    return _stateless_response(
        action="next_step",
        reply=_next_step_reply(latest_run_id, current)
        + " Open that run before taking any gated action from a stateless client.",
        next_actions=next_actions,
        extra={
            "runs": report,
            "recent_run": latest,
            "run_reference": run_reference,
            "latest_status": current,
            "next_action": {
                "id": "open_latest_run",
                "label": "Open latest run",
                "kind": "open_run",
                "run_id": latest_run_id,
                "safe": True,
                "reason": "Open the latest Patchbay run before choosing the gated next action.",
            },
            "actions": _next_step_actions(latest_run_id, current, include_open_run=True),
        },
    )


def _gate_status_response(root: Path, *, run_id: str | None, include: dict[str, Any] | None = None) -> dict[str, Any]:
    if run_id:
        current = service.status(root, run_id)
        diagnosis = _gate_diagnosis(current)
        return _agent_response(
            root,
            run_id,
            action="gate_status",
            reply=_gate_status_reply(run_id, diagnosis),
            include=include,
            extra={"gate_diagnosis": diagnosis, "actions": _gate_status_actions(run_id, current, include_open_run=False)},
        )

    report = service.runs(root, limit=5)
    recent = list(report.get("runs") or [])
    if not recent:
        return _stateless_response(
            action="gate_status",
            reply="No Patchbay runs found. Send a task to start with a plan, or send readiness to check setup.",
            next_actions=["start", "readiness"],
            extra={
                "runs": report,
                "recent_run": None,
                "actions": [
                    {
                        "id": "start_new_task",
                        "label": "Start new task",
                        "kind": "focus_composer",
                        "safe": True,
                        "reason": "Focus the composer so a new Patchbay plan can be started.",
                    },
                    {
                        "id": "open_readiness",
                        "label": "Open readiness",
                        "kind": "local_agent",
                        "message": "readiness",
                        "safe": True,
                        "reason": "Run read-only setup diagnostics before starting work.",
                    },
                ],
            },
        )

    latest = recent[0]
    latest_run_id = str(latest.get("run_id") or "")
    current = service.status(root, latest_run_id) if latest_run_id else dict(latest)
    diagnosis = _gate_diagnosis(current)
    run_reference = {
        "run_id": latest.get("run_id"),
        "status": latest.get("status") or current.get("status"),
        "task": latest.get("task"),
        "updated_at": latest.get("updated_at"),
        "suggested_message": "open latest run",
        "safe_actions": ["open_run", "status", "events"],
        "gate_diagnosis": diagnosis,
    }
    return _stateless_response(
        action="gate_status",
        reply=_gate_status_reply(latest_run_id, diagnosis)
        + " Open that run before taking any gated action from a stateless client.",
        next_actions=["open latest run", "status", "events", "readiness"],
        extra={
            "runs": report,
            "recent_run": latest,
            "run_reference": run_reference,
            "latest_status": current,
            "gate_diagnosis": diagnosis,
            "actions": _gate_status_actions(latest_run_id, current, include_open_run=True),
        },
    )


def _metrics_response(root: Path, run_id: str) -> dict[str, Any]:
    result = service.metrics(root, run_id)
    run_metrics = result.get("run_metrics") or {}
    attempts = sum(int(value or 0) for value in (run_metrics.get("phase_attempts") or {}).values())
    providers = [item for item in (run_metrics.get("provider_usage") or []) if item.get("provider") or item.get("model")]
    cost = run_metrics.get("cost") or {}
    token_usage = run_metrics.get("token_usage") or {}
    tier_usage = run_metrics.get("tier_usage") or {}
    routing = result.get("routing_evidence") or run_metrics.get("routing_evidence") or {}
    efficiency = result.get("efficiency_summary") or run_metrics.get("efficiency_summary") or {}
    signals = [
        f"{attempts} phase attempt{'s' if attempts != 1 else ''}",
        f"{len(providers)} provider trace entr{'ies' if len(providers) != 1 else 'y'}",
        "cost known" if cost.get("known") else "cost not reported",
        "tokens known" if token_usage.get("known") else "tokens not reported",
    ]
    if isinstance(efficiency, dict) and efficiency.get("status"):
        signals.append(f"efficiency {efficiency['status']}")
        if efficiency.get("summary"):
            signals.append(str(efficiency["summary"]))
    economy_tier = tier_usage.get("economy") if isinstance(tier_usage, dict) else {}
    economy_tokens = economy_tier.get("token_usage") if isinstance(economy_tier, dict) else {}
    if isinstance(economy_tokens, dict) and economy_tokens.get("known"):
        token_percent = economy_tokens.get("token_percent")
        percent_label = f"{token_percent}% tokens" if token_percent is not None else f"{economy_tokens.get('total_tokens')} tokens"
        signals.append(f"economy tier {percent_label}")
    if isinstance(routing, dict) and routing.get("summary"):
        health = routing.get("economy_health") if isinstance(routing.get("economy_health"), dict) else {}
        if health.get("status"):
            signals.append(f"economy health {health['status']}")
        signals.append(str(routing["summary"]))
    metrics_payload = dict(result)
    if routing:
        metrics_payload["routing_evidence"] = routing
    if efficiency:
        metrics_payload["efficiency_summary"] = efficiency
    actions = list(result.get("actions") or (routing.get("actions") if isinstance(routing, dict) else []) or [])
    return _with_action_groups({
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "action": "metrics",
        "reply": f"Run {run_id} metrics: " + "; ".join(signals) + ".",
        "run_id": run_id,
        "status": metrics_payload,
        "context": None,
        "events": None,
        "artifacts": {},
        "diff": None,
        "requires_confirmation": None,
        "next_actions": ["status", "continue", "readiness"],
        "actions": actions,
        "error": None,
        "metrics": metrics_payload,
    })


def _latest_metrics_response(root: Path, text: str) -> dict[str, Any]:
    report = service.runs(root, limit=5)
    recent = list(report.get("runs") or [])
    if not recent:
        return _missing_run_response(root, text)
    latest = recent[0]
    latest_run_id = str(latest.get("run_id") or "")
    response = _metrics_response(root, latest_run_id)
    requested_view = {"tab": "Overview", "reason": "The prompt asked for latest run efficiency metrics."}
    open_action = {
        "id": "open_latest_run",
        "label": "Open latest run",
        "kind": "open_run",
        "run_id": latest_run_id,
        "tab": "Overview",
        "safe": True,
        "reason": "Open the latest Patchbay run that supplied these read-only metrics.",
    }
    actions = [open_action, *list(response.get("actions") or [])]
    response.update(
        {
            "reply": response["reply"].replace(f"Run {latest_run_id} metrics:", f"Latest run {latest_run_id} metrics:", 1),
            "next_actions": ["open latest run", "status", "continue", "readiness"],
            "actions": actions,
            "recent_run": latest,
            "run_reference": {
                "run_id": latest_run_id,
                "status": latest.get("status"),
                "task": latest.get("task"),
                "updated_at": latest.get("updated_at"),
                "suggested_message": "open latest run",
                "safe_actions": ["open_run", "status", "events"],
                "requested_view": requested_view,
            },
            "requested_view": requested_view,
            "runs": report,
        }
    )
    return _with_action_groups(response)


def _latest_view_response(root: Path, text: str) -> dict[str, Any]:
    report = service.runs(root, limit=5)
    recent = list(report.get("runs") or [])
    if not recent:
        return _missing_run_response(root, text)
    latest = recent[0]
    latest_run_id = str(latest.get("run_id") or "")
    requested_view = _missing_run_requested_view(text) or {"tab": "Overview", "reason": "The prompt asked for the latest run."}
    tab = str(requested_view.get("tab") or "Overview")
    include = _include_for_requested_view(root, latest_run_id, tab)
    response = _agent_response(
        root,
        latest_run_id,
        action=_action_for_requested_view(tab),
        reply=f"Latest run {latest_run_id} {tab.lower()} view.",
        include=include,
        extra=_run_view_response_extra(text, default_tab=tab),
    )
    response.update(
        {
            "recent_run": latest,
            "run_reference": {
                "run_id": latest_run_id,
                "status": latest.get("status"),
                "task": latest.get("task"),
                "updated_at": latest.get("updated_at"),
                "suggested_message": "open latest run",
                "safe_actions": ["open_run", "status", "events"],
                "requested_view": requested_view,
            },
            "requested_view": requested_view,
            "runs": report,
        }
    )
    response["actions"] = [
        {
            "id": "open_latest_run",
            "label": "Open latest run",
            "kind": "open_run",
            "run_id": latest_run_id,
            "tab": tab,
            "safe": True,
            "reason": "Open the latest Patchbay run that supplied this read-only view.",
        },
        *list(response.get("actions") or []),
    ]
    return _with_action_groups(response)


def _include_for_requested_view(root: Path, run_id: str, tab: str) -> dict[str, Any]:
    if tab == "Diff":
        return {"diff": True}
    if tab == "Trace":
        return {"events_since": 0, "include_trace": True}
    if tab == "Log":
        artifact = _log_artifact_for_run(root, run_id)
        include: dict[str, Any] = {"events_since": 0, "include_trace": True}
        if artifact:
            include.update({"artifact": artifact, "artifact_tail": 200})
        return include
    if tab == "Artifacts":
        return {"plan": True, "review": True}
    return {"events_since": 0}


def _action_for_requested_view(tab: str) -> str:
    if tab == "Overview":
        return "context"
    if tab == "Diff":
        return "diff"
    if tab == "Trace":
        return "events"
    if tab in {"Artifacts", "Log"}:
        return "artifact"
    return "status"


def _log_artifact_for_run(root: Path, run_id: str) -> str | None:
    try:
        run_path, _ = service._load_run(root, run_id)
        status = service.status(root, run_id)
    except Exception:
        return None
    recovery = status.get("failure_recovery") if isinstance(status.get("failure_recovery"), dict) else {}
    for artifact in recovery.get("artifacts") or []:
        name = str(artifact or "")
        if name.endswith(".log") and (run_path / name).is_file():
            return name
    phase = str(status.get("current_phase") or "")
    phase_logs = {
        "plan": "claude-planner.log",
        "write": "writer.log",
        "fix": "writer.log",
        "review": "codex-reviewer.log",
        "test": "TEST.log",
    }
    candidate = phase_logs.get(phase)
    return candidate if candidate and (run_path / candidate).is_file() else None


def _missing_run_response(root: Path, text: str) -> dict[str, Any]:
    report = service.runs(root, limit=5)
    recent = list(report.get("runs") or [])
    run_reference = None
    requested_view = _missing_run_requested_view(text)
    if recent:
        latest = recent[0]
        run_reference = {
            "run_id": latest.get("run_id"),
            "status": latest.get("status"),
            "task": latest.get("task"),
            "updated_at": latest.get("updated_at"),
            "suggested_message": "open latest run",
            "safe_actions": ["open_run", "status", "events"],
            "requested_view": requested_view,
        }
        actions = [
            {
                "id": "open_latest_run",
                "label": "Open latest run",
                "kind": "open_run",
                "run_id": latest.get("run_id"),
                "tab": (requested_view or {}).get("tab"),
                "safe": True,
                "reason": "Open the latest Patchbay run before choosing any gated action.",
            },
            {
                "id": "show_runs",
                "label": "Show runs",
                "kind": "local_agent",
                "message": "status",
                "safe": True,
                "reason": "List recent Patchbay runs without advancing any run gate.",
            },
            {
                "id": "open_readiness",
                "label": "Open readiness",
                "kind": "local_agent",
                "message": "readiness",
                "safe": True,
                "reason": "Run read-only setup diagnostics before starting or resuming work.",
            },
        ]
        reply = (
            f"`{text}` needs an existing run_id. Latest run is {latest.get('run_id')} "
            f"({latest.get('status') or 'unknown'}). Open that run first, then choose the next gated action."
        )
        next_actions = ["open latest run", "runs", "readiness"]
    else:
        reply = f"`{text}` needs an existing run_id, but no Patchbay runs were found. Send a task to start with a plan."
        next_actions = ["start", "readiness"]
        actions = [
            {
                "id": "start_new_task",
                "label": "Start new task",
                "kind": "focus_composer",
                "safe": True,
                "reason": "Focus the composer so a new Patchbay plan can be started.",
            },
            {
                "id": "open_readiness",
                "label": "Open readiness",
                "kind": "local_agent",
                "message": "readiness",
                "safe": True,
                "reason": "Run read-only setup diagnostics before starting work.",
            },
        ]
    return _stateless_response(
        action="missing_run",
        reply=reply,
        ok=False,
        error=reply,
        next_actions=next_actions,
        extra={
            "runs": report,
            "recent_run": recent[0] if recent else None,
            "run_reference": run_reference,
            "requested_view": requested_view,
            "actions": actions,
        },
    )


def _missing_run_requested_view(text: str) -> dict[str, Any] | None:
    normalized = text.strip().lower()
    words = _words(normalized)
    if normalized in {"context", "handoff", "poll context", "run context"} or _has_any(normalized, ("handoff context", "run handoff")):
        return {"tab": "Overview", "reason": "The prompt asked for the run handoff context."}
    if words & {"diff", "patch"} or _has_any(normalized, ("补丁", "变更", "差异", "改动")):
        return {"tab": "Diff", "reason": "The prompt asked for the run diff or patch."}
    if words & {"events", "trace"} or _has_any(normalized, ("事件", "跟踪", "轨迹", "trace")):
        return {"tab": "Trace", "reason": "The prompt asked for run events or trace."}
    if words & {"error", "errors", "fail", "failed", "failure", "log", "logs"} or _has_any(normalized, ("失败", "错误", "报错", "原因", "为什么", "日志", "log")):
        return {"tab": "Log", "reason": "The prompt asked for run logs."}
    if words & {"artifact", "artifacts", "plan", "review"} or _has_any(normalized, ("产物", "计划", "审查", "评审")):
        return {"tab": "Artifacts", "reason": "The prompt asked for run artifacts."}
    return None


def _run_view_response_extra(text: str, *, default_tab: str | None = None) -> dict[str, Any]:
    requested_view = _missing_run_requested_view(text)
    if requested_view is None and default_tab:
        requested_view = {"tab": default_tab, "reason": f"The prompt asked for the run {default_tab.lower()} view."}
    if not requested_view:
        return {}
    tab = str(requested_view.get("tab") or "")
    if not tab:
        return {"requested_view": requested_view}
    return {
        "requested_view": requested_view,
        "actions": [
            {
                "id": f"open_{tab.lower()}",
                "label": f"Open {tab}",
                "kind": "diagnostic_tab",
                "tab": tab,
                "safe": True,
                "reason": str(requested_view.get("reason") or "Open the requested run diagnostic view."),
            }
        ],
    }


def _doctor_response(root: Path, message: str = "") -> dict[str, Any]:
    host = _setup_host_from_message(message)
    avoid_mcp = _is_mcp_avoidance_intent(message.lower())
    report = run_doctor(root, include_mcp=False, suppress_mcp_actions=avoid_mcp, host=host)
    next_actions = list(report.get("next_actions") or [])
    recommendations = list(report.get("recommendations") or [])
    actions = list(report.get("actions") or [])
    if avoid_mcp:
        next_actions = _without_mcp_followup_text(next_actions)
        actions = _without_mcp_followup_actions(actions)
        report = {**report, "next_actions": next_actions, "actions": actions}
    suggested_actions = _doctor_suggested_actions(next_actions, recommendations)
    if not suggested_actions:
        suggested_actions = _next_actions_from_structured_actions(actions)
    if report.get("ok"):
        reply = "Patchbay readiness checks passed."
    elif next_actions:
        reply = "Patchbay readiness checks found setup work: " + " ".join(next_actions)
    else:
        reply = "Patchbay readiness checks need attention."
    if recommendations:
        reply += " Recommendations: " + " ".join(recommendations)
    return _stateless_response(
        action="doctor",
        reply=reply,
        ok=bool(report.get("ok")),
        error=None if report.get("ok") else reply,
        next_actions=suggested_actions,
        extra={
            "doctor": report,
            "setup_host": report.get("host") or host,
            "recommendations": recommendations,
            "routing": report.get("routing"),
            "actions": actions,
        },
    )


def _doctor_suggested_actions(next_actions: list[str], recommendations: list[str]) -> list[str]:
    actions = list(next_actions)
    if any("config profile apply economy" in item for item in recommendations):
        actions.append("apply economy profile")
    if any("commands.reasonix" in item for item in recommendations):
        actions.append("configure reasonix command")
    if any("providers." in item and ".command" in item for item in recommendations):
        actions.append("configure economy provider command")
    return _dedupe_strings(actions)


def _next_actions_from_structured_actions(actions: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for action in actions:
        message = str(action.get("message") or "").strip()
        if message:
            values.append(message)
            continue
        if str(action.get("id") or "") == "start_new_task" or str(action.get("kind") or "") == "focus_composer":
            values.append("start")
            continue
        command = str(action.get("command") or "").strip()
        if command:
            values.append(command)
    return _dedupe_strings(values)


def _economy_command_not_ready_sentence(routing: dict[str, Any]) -> str:
    phases = routing.get("command_not_ready_phases") or ["write", "fix"]
    phase_text = "/".join(str(phase) for phase in phases)
    phase_data = routing.get("phases") if isinstance(routing.get("phases"), dict) else {}
    statuses: list[dict[str, Any]] = []
    for phase in phases:
        item = phase_data.get(phase) if isinstance(phase_data.get(phase), dict) else {}
        status = item.get("command_status") if isinstance(item.get("command_status"), dict) else None
        if status:
            statuses.append(status)
    sources = _dedupe_strings([str(item.get("source") or "").strip() for item in statuses if str(item.get("source") or "").strip()])
    recommendations = _dedupe_strings(
        [str(item.get("recommendation") or "").strip() for item in statuses if str(item.get("recommendation") or "").strip()]
    )
    target = routing.get("target", {}) if isinstance(routing.get("target"), dict) else {}
    target_label = str(target.get("label") or _route_label(target) or "the configured economy target")
    source_text = " and ".join(f"`{source}`" for source in sources) if sources else "the configured provider command"
    if str(target.get("provider") or "") == service.ECONOMY_PROVIDER and "commands.reasonix" in sources:
        sentence = (
            f"The economy route is configured, but {phase_text} cannot execute until "
            "`commands.reasonix` points to a runnable Reasonix CLI."
        )
    else:
        sentence = (
            f"The economy route is configured, but {phase_text} cannot execute until "
            f"{source_text} points to a runnable {target_label} command."
        )
    if recommendations:
        sentence += " " + recommendations[0]
    return sentence


def _profile_apply_response(root: Path) -> dict[str, Any]:
    result = run_config_wizard(root, profile="economy")
    status = result.get("status") or {}
    write = ((status.get("economy") or {}).get("write") or {})
    fix = ((status.get("economy") or {}).get("fix") or {})
    routing = _profile_routing_digest(result)
    target = routing.get("target", {}) if isinstance(routing.get("target"), dict) else {}
    target_label = str(target.get("label") or _route_label(target) or "the configured economy target")
    reply = (
        "Economy routing profile applied. High-volume write/fix work now routes to "
        f"{target_label}."
    )
    if fix:
        reply += f" Fix uses {fix.get('provider') or '-'} / {fix.get('model') or '-'}."
    reply += f" {routing['summary']}"
    if routing.get("economy_command_ready") is False:
        reply += " " + _economy_command_not_ready_sentence(routing)
    reply = _with_workload_policy_summary(reply, routing)
    return _stateless_response(
        action="profile_apply",
        reply=reply,
        next_actions=list(result.get("next_actions") or ["readiness", "start"]),
        extra={
            "profile": result,
            "routing": routing,
            "actions": list(result.get("actions") or []),
        },
    )


def _custom_provider_setup_response(root: Path, message: str) -> dict[str, Any]:
    command = _custom_provider_command_from_message(message)
    if command:
        result = run_config_wizard(
            root,
            provider_id="cheap_writer",
            provider_roles=["write", "fix"],
            provider_command=command,
            prompt_mode="stdin",
            output_contract="writer_diff",
            activate_economy=True,
            economy_model="deepseek-chat",
            economy_label="DeepSeek cheap writer",
        )
        routing = _profile_routing_digest(result)
        reply = (
            f"Custom economy provider `cheap_writer` configured with `{command}`. "
            "High-volume write/fix work now routes to DeepSeek cheap writer. "
            f"{routing['summary']}"
        )
        if routing.get("economy_command_ready") is False:
            reply += " " + _economy_command_not_ready_sentence(routing)
        reply = _with_workload_policy_summary(reply, routing)
        return _stateless_response(
            action="custom_provider_configure",
            reply=reply,
            next_actions=list(result.get("next_actions") or ["readiness", "start"]),
            extra={
                "config_update": result,
                "profile": result,
                "routing": routing,
                "actions": list(result.get("actions") or []),
                "custom_provider": {
                    "provider_id": "cheap_writer",
                    "roles": ["write", "fix"],
                    "command": command,
                    "output_contract": "writer_diff",
                    "activate_economy": True,
                },
            },
        )

    profile = run_config_wizard(root, show_profile=True)
    routing = _profile_routing_digest(profile)
    action = _custom_provider_setup_action()
    return _stateless_response(
        action="custom_provider_setup",
        reply=(
            "Use the command action to register a low-cost CLI writer such as DeepSeek and activate it for write/fix. "
            "Replace `<deepseek-writer-command>` with your local wrapper or executable; Patchbay will validate the provider before writing config."
        ),
        next_actions=["copy custom provider command", "readiness", "show economy profile"],
        extra={
            "profile": profile,
            "routing": routing,
            "actions": [
                action,
                {
                    "id": "open_readiness",
                    "label": "Open readiness",
                    "kind": "local_agent",
                    "message": "readiness",
                    "safe": True,
                    "reason": "Inspect setup and economy route command readiness after registering the provider.",
                },
            ],
            "custom_provider": {
                "provider_id": "cheap_writer",
                "roles": ["write", "fix"],
                "output_contract": "writer_diff",
                "activate_economy": True,
            },
        },
    )


def _custom_provider_command_configure_response(root: Path, message: str) -> dict[str, Any]:
    cfg = load_config(root)
    target = economy_target(cfg)
    provider_id = _custom_provider_id_from_message(message, cfg, target)
    command = _custom_provider_command_from_message(message)
    if provider_id == service.ECONOMY_PROVIDER:
        return _reasonix_command_configure_response(root, message)

    if not provider_id:
        action = _custom_provider_setup_action()
        return _stateless_response(
            action="custom_provider_command_configure",
            reply=(
                "No custom economy provider is active yet. Register one first, or use the command action template "
                "to create `cheap_writer` for high-volume write/fix work."
            ),
            next_actions=["copy custom provider command", "readiness", "show economy profile"],
            ok=False,
            error="custom economy provider not configured",
            extra={"actions": [action], "target": target},
        )

    providers = cfg.get("providers", {}) if isinstance(cfg.get("providers"), dict) else {}
    if provider_id not in providers:
        if provider_id == "cheap_writer" and command:
            return _custom_provider_setup_response(root, f"configure DeepSeek provider to {command}")
        action = _custom_provider_setup_action()
        return _stateless_response(
            action="custom_provider_command_configure",
            reply=(
                f"`providers.{provider_id}` is not configured yet. Register the provider before setting "
                f"`providers.{provider_id}.command`, or use the `cheap_writer` setup template."
            ),
            next_actions=["copy custom provider command", "readiness", "show economy profile"],
            ok=False,
            error=f"providers.{provider_id} is not configured",
            extra={
                "actions": [action],
                "custom_provider": {"provider_id": provider_id, "source": f"providers.{provider_id}.command"},
                "target": target,
            },
        )

    source = f"providers.{provider_id}.command"
    target_label = str(target.get("label") or _route_label(target)) if str(target.get("provider") or "") == provider_id else provider_id
    if not command:
        action = _provider_command_copy_action(source, target_label)
        return _stateless_response(
            action="custom_provider_command_configure",
            reply=f"Provide the executable or wrapper command to set `{source}` for the {target_label} economy route.",
            next_actions=["copy provider command", "readiness", "show economy profile"],
            ok=False,
            error="provider command value missing",
            extra={
                "actions": [action],
                "custom_provider": {"provider_id": provider_id, "source": source},
                "target": target,
            },
        )

    result = run_config_wizard(root, set_key=source, set_value=command)
    profile = run_config_wizard(root, show_profile=True)
    routing = _profile_routing_digest(profile)
    reply = (
        f"Custom economy provider `{provider_id}` command configured as `{command}`. "
        f"Patchbay will use it for the {target_label} write/fix economy route when that profile is active. "
        f"{routing['summary']}"
    )
    if routing.get("economy_command_ready") is False:
        reply += " " + _economy_command_not_ready_sentence(routing)
    return _stateless_response(
        action="custom_provider_command_configure",
        reply=reply,
        next_actions=list(profile.get("next_actions") or ["readiness", "start"]),
        extra={
            "config_update": result,
            "profile": profile,
            "routing": routing,
            "actions": list(profile.get("actions") or []),
            "custom_provider": {"provider_id": provider_id, "command": command, "source": source},
        },
    )


def _custom_provider_id_from_message(message: str, cfg: dict[str, Any], target: dict[str, Any]) -> str:
    text = (message or "").strip().lower()
    match = re.search(r"providers\.([a-z0-9_-]+)\.command", text)
    if match:
        return match.group(1)
    providers = cfg.get("providers", {}) if isinstance(cfg.get("providers"), dict) else {}
    for provider_id in sorted((str(key) for key in providers.keys()), key=len, reverse=True):
        candidate = provider_id.lower()
        if re.search(rf"\b{re.escape(candidate)}\b", text) or candidate.replace("_", " ") in text:
            return provider_id
    target_provider = str(target.get("provider") or "").strip()
    if target_provider and target_provider != service.ECONOMY_PROVIDER:
        return target_provider
    words = _words(text)
    if "cheap_writer" in words or "cheap writer" in text or ("deepseek" in words and "provider" in words):
        return "cheap_writer"
    return service.ECONOMY_PROVIDER if target_provider == service.ECONOMY_PROVIDER else ""


def _provider_command_copy_action(source: str, target_label: str) -> dict[str, Any]:
    return {
        "id": "configure_economy_provider_command",
        "label": "Copy provider command",
        "kind": "command",
        "command": f"patchbay config --set-key {source} --set-value <command>",
        "safe": True,
        "reason": f"Copy the command for the {target_label} economy provider into .ai/patchbay.toml.",
    }


def _reasonix_command_configure_response(root: Path, message: str = "") -> dict[str, Any]:
    command = _reasonix_command_from_message(message)
    source = "message" if command != "reasonix" else "default"
    result = run_config_wizard(root, set_key="commands.reasonix", set_value=command)
    profile = run_config_wizard(root, show_profile=True)
    routing = _profile_routing_digest(profile)
    actions = list(profile.get("actions") or [])
    target = routing.get("target", {}) if isinstance(routing.get("target"), dict) else {}
    target_label = str(target.get("label") or _route_label(target) or "the active economy target")
    reply = (
        f"Reasonix command configured as `{command}`. "
        f"Patchbay will use it for the {target_label} economy write/fix route when that profile is active."
    )
    if routing.get("economy_command_ready") is False:
        reply += " The command is saved, but it is not currently resolvable on PATH; install Reasonix or set the full executable path."
    return _stateless_response(
        action="reasonix_command_configure",
        reply=reply,
        next_actions=list(profile.get("next_actions") or ["readiness", "start"]),
        extra={
            "config_update": result,
            "profile": profile,
            "routing": routing,
            "actions": actions,
            "reasonix_command": {"command": command, "source": source},
        },
    )


def _reasonix_command_from_message(message: str) -> str:
    text = (message or "").strip()
    patterns = (
        r"--set-value\s+(.+)$",
        r"commands\.reasonix\s*(?:=|为|设为|设置为|配置为)\s*(.+)$",
        r"(?:把|将)?\s*reasonix\s*(?:命令|路径|可执行文件|可执行程序)?\s*(?:设为|设置为|配置为|指定为|改为|换成|用|使用|=|为|是)\s*(.+)$",
        r"(?:设为|设置为|配置为|指定为|路径是|命令是|使用)\s+(.+)$",
        r"reasonix\s*(?:命令|路径|可执行文件|可执行程序)\s*(?:到|为|是|=)\s*(.+)$",
        r"\b(?:to|as|at|path|executable)\s+(.+)$",
        r"\breasonix\s+command\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = _clean_reasonix_command_value(match.group(1))
        if value:
            return value
    return "reasonix"


def _clean_reasonix_command_value(value: str) -> str:
    cleaned = value.strip().rstrip(".,;。；，、")
    cleaned = re.sub(r"^(?:to|as|=|为|是|到|成|设为|设置为|配置为|指定为|用|使用)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    had_wrapping_quotes = len(cleaned) >= 2 and (
        (cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"', "`"})
        or (cleaned[0], cleaned[-1]) in {("“", "”"), ("‘", "’")}
    )
    while len(cleaned) >= 2 and (
        (cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"', "`"})
        or (cleaned[0], cleaned[-1]) in {("“", "”"), ("‘", "’")}
    ):
        cleaned = cleaned[1:-1].strip()
    if cleaned.lower() in {
        "command",
        "commands.reasonix",
        "reasonix command",
        "reasonix 命令",
        "reasonix 路径",
        "命令",
        "路径",
        "可执行",
        "可执行文件",
        "可执行程序",
    }:
        return ""
    if re.search(r"\s", cleaned) and (had_wrapping_quotes or _looks_like_command_path(cleaned)):
        return f'"{cleaned}"'
    return cleaned


def _looks_like_command_path(value: str) -> bool:
    return "\\" in value or "/" in value or ":" in value


def _profile_show_response(root: Path, run_id: str | None = None) -> dict[str, Any]:
    preview = _routing_preview(root)
    result = preview["profile"]
    profile = str(result.get("profile") or "custom")
    routing = preview["routing"]
    reply = preview["reply_suffix"]
    extra: dict[str, Any] = {"profile": result, "routing": routing, "actions": list(preview["actions"])}
    if run_id:
        try:
            metrics = service.metrics(root, run_id)
        except Exception as exc:
            extra["run_evidence_error"] = str(exc)
            reply += f" Run evidence for `{run_id}` could not be loaded: {exc}"
        else:
            efficiency = metrics.get("efficiency_summary") if isinstance(metrics.get("efficiency_summary"), dict) else {}
            run_routing = metrics.get("routing_evidence") if isinstance(metrics.get("routing_evidence"), dict) else {}
            extra.update(
                {
                    "run_id": run_id,
                    "metrics": metrics,
                    "routing_evidence": run_routing,
                    "efficiency_summary": efficiency,
                }
            )
            if efficiency.get("summary"):
                reply += " Run evidence: " + str(efficiency["summary"])
            elif run_routing.get("summary"):
                reply += " Run evidence: " + str(run_routing["summary"])
    return _stateless_response(
        action="profile_show",
        reply=reply,
        next_actions=list(result.get("next_actions") or (["readiness", "start"] if profile == "economy" else ["apply economy profile", "readiness"])),
        extra=extra,
    )


def _routing_preview(root: Path) -> dict[str, Any]:
    preview = service.routing_preview(root)
    result = preview["profile"]
    routing = preview["routing"]
    reply = str(routing["summary"])
    if not routing.get("economy_configured"):
        reply += " " + str(result.get("recommendation") or "Run `patchbay config profile apply economy`.")
    elif routing.get("economy_command_ready") is False:
        reply += " " + _economy_command_not_ready_sentence(routing)
    reply = _with_workload_policy_summary(reply, routing)
    return {
        "profile": result,
        "routing": routing,
        "actions": list(preview.get("actions") or []),
        "reply_suffix": reply,
    }


def _with_workload_policy_summary(reply: str, routing: dict[str, Any]) -> str:
    workload_policy = routing.get("workload_policy") if isinstance(routing.get("workload_policy"), dict) else {}
    workload_summary = str(workload_policy.get("summary") or "").strip()
    if workload_summary and workload_summary not in reply:
        reply += " " + workload_summary
    return reply


def _stateless_response(
    *,
    action: str,
    reply: str,
    next_actions: list[str],
    ok: bool = True,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "action": action,
        "reply": reply,
        "run_id": None,
        "status": None,
        "context": None,
        "events": None,
        "artifacts": {},
        "diff": None,
        "requires_confirmation": None,
        "next_actions": next_actions,
        "error": error,
    }
    if extra:
        response.update(extra)
    return _with_action_groups(response)


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for action in actions:
        key = str(action.get("id") or action.get("message") or action.get("command") or action.get("label") or "").strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(action)
    return result


def _is_unattended_plan_approval(text: str) -> bool:
    if not text:
        return False
    compact = re.sub(r"[\s\-_`'\".,;:!?()\[\]{}]+", "", text)
    compact_needles = tuple(re.sub(r"[\s\-_`'\".,;:!?()\[\]{}]+", "", item) for item in UNATTENDED_PLAN_APPROVAL_PHRASES)
    return _has_any(text, UNATTENDED_PLAN_APPROVAL_PHRASES) or _has_any(compact, compact_needles)


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
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = service.status(root, run_id)
    result = {
        "run_id": run_id,
        "ok": ok,
        "reply": reply,
        "status": current,
        "requires_confirmation": requires_confirmation,
        "next_actions": _next_actions_for_status(current),
        "error": error,
    }
    if current.get("failure_recovery"):
        result["recovery"] = current["failure_recovery"]
    if extra:
        result.update(extra)
    return result


def _agent_response(
    root: Path,
    run_id: str,
    *,
    action: str,
    reply: str,
    requires_confirmation: dict[str, Any] | None = None,
    include: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    status_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = status_data if status_data is not None else service.status(root, run_id)
    effective_include = _merge_include(include, _auto_include_for_status(current))
    since = int(effective_include.get("events_since", 0) or 0)
    include_trace = bool(effective_include.get("include_trace", False))
    response: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "action": action,
        "reply": reply,
        "run_id": run_id,
        "status": current,
        "context": service.context(root, run_id, since_event=since, include_trace=include_trace, status_data=current),
        "events": service.events(root, run_id, since=since, phase=effective_include.get("event_phase") or None),
        "artifacts": _included_artifacts(root, run_id, effective_include),
        "diff": service.diff(root, run_id) if effective_include.get("diff") else None,
        "requires_confirmation": requires_confirmation or _required_confirmation_for_status(current),
        "next_actions": _next_actions_for_status(current),
        "error": None,
    }
    if current.get("failure_recovery"):
        response["recovery"] = current["failure_recovery"]
    if extra:
        response.update(extra)
    return _with_action_groups(response)


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
        "context": None,
        "events": None,
        "artifacts": {},
        "diff": None,
        "requires_confirmation": None,
        "next_actions": [],
        "error": message,
    }


def _background_pending_response(
    *,
    action: str,
    run_id: str,
    reply: str,
    job: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    followup_actions = service.background_followup_actions(run_id)
    response = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "action": action,
        "reply": reply,
        "run_id": run_id,
        "status": None,
        "context": None,
        "events": None,
        "artifacts": {},
        "diff": None,
        "requires_confirmation": None,
        "next_actions": _background_next_actions(),
        "error": None,
        "background": True,
        "job": job,
        "background_job": service.summarize_background_job(job),
        "actions": followup_actions,
    }
    if extra:
        response.update(extra)
        routing_actions = list(extra.get("routing_actions") or [])
        if routing_actions:
            response["actions"] = followup_actions + routing_actions
    return _with_action_groups(response)


def _with_action_groups(response: dict[str, Any]) -> dict[str, Any]:
    actions = response.get("actions")
    if isinstance(actions, list):
        actions = _dedupe_actions([action for action in actions if isinstance(action, dict)])
        response["actions"] = actions
        groups = group_actions(actions)
        if groups:
            response["action_groups"] = groups
    return response


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
    if _apply_ready(status_data):
        return _confirmation("apply_approval", "apply", APPLY_CONFIRMATION)
    return None


def _apply_ready(status_data: dict[str, Any]) -> bool:
    return (
        status_data.get("status") == REVIEWED_PASS
        and status_data.get("review_result") == "PASS"
        and bool(status_data.get("tests_passed"))
        and bool(status_data.get("gate_state", {}).get("ready_to_apply"))
    )


def _confirmation(kind: str, required_action: str, confirmation: str) -> dict[str, Any]:
    return {
        "type": kind,
        "required_action": required_action,
        "confirmation": confirmation,
    }


def _next_actions_for_status(status_data: dict[str, Any]) -> list[str]:
    blocker = status_data.get("blocked_next_action") if isinstance(status_data.get("blocked_next_action"), dict) else None
    if blocker:
        action = blocker.get("action") if isinstance(blocker.get("action"), dict) else {}
        suggested = str(action.get("message") or "configure reasonix command")
        return [suggested, "readiness", "status", "events"]
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


def _next_step_reply(run_id: str, status_data: dict[str, Any]) -> str:
    status_value = str(status_data.get("status") or "unknown")
    blocker = status_data.get("blocked_next_action") if isinstance(status_data.get("blocked_next_action"), dict) else None
    if blocker:
        return f"Run {run_id} cannot continue yet. {blocker.get('message') or blocker.get('suggested_next_action')}"
    if status_value == PLANNED:
        return f"Run {run_id} is waiting for explicit plan approval. Review the plan, then approve before implementation starts."
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        return f"Run {run_id} passed tests and review. Apply is available, but still requires explicit apply confirmation."
    if status_value in {APPROVED, IMPLEMENTED, TESTED, REVIEWED_CHANGES_REQUESTED}:
        return f"Run {run_id} is {status_value}. `continue` can run the next safe phase for the selected run."
    if status_value in {IMPLEMENTING, TESTING, REVIEWING, FIXING}:
        return f"Run {run_id} is currently running {status_data.get('current_phase') or status_value}. Poll status, context, or events."
    if status_value == FAILED:
        recovery = status_data.get("failure_recovery") or _failure_recovery_summary(status_data)
        return f"Run {run_id} failed. {recovery.get('suggested_next_action') or 'Inspect artifacts and events before retrying.'}"
    if status_value == APPLIED:
        return f"Run {run_id} has already been applied. Inspect status/events or clean up the isolated worktree."
    return f"Run {run_id} is {status_value}. Inspect status/events before choosing another action."


def _next_step_actions(run_id: str, status_data: dict[str, Any], *, include_open_run: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if include_open_run:
        actions.append(
            {
                "id": "open_latest_run",
                "label": "Open latest run",
                "kind": "open_run",
                "run_id": run_id,
                "safe": True,
                "reason": "Open the latest Patchbay run before choosing any gated action.",
            }
        )
    actions.append(
        {
            "id": "open_trace",
            "label": "Open activity",
            "kind": "diagnostic_tab",
            "tab": "Trace",
            "safe": True,
            "reason": "Inspect the run timeline and provider activity before taking the next step.",
        }
    )
    status_value = str(status_data.get("status") or "")
    if status_value == PLANNED:
        actions.append(
            {
                "id": "open_plan",
                "label": "Open plan",
                "kind": "diagnostic_tab",
                "tab": "Artifacts",
                "safe": True,
                "reason": "Review PLAN.md before giving explicit approval.",
            }
        )
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        actions.append(
            {
                "id": "open_diff",
                "label": "Open diff",
                "kind": "diagnostic_tab",
                "tab": "Diff",
                "safe": True,
                "reason": "Inspect the final patch before explicit apply confirmation.",
            }
        )
    if status_value == FAILED:
        actions.extend(list((status_data.get("failure_recovery") or {}).get("actions") or []))
    actions.append(
        {
            "id": "open_readiness",
            "label": "Open readiness",
            "kind": "local_agent",
            "message": "readiness",
            "safe": True,
            "reason": "Run read-only setup diagnostics if the next step is blocked by local setup.",
        }
    )
    return actions


def _next_step_primary_action(status_data: dict[str, Any]) -> dict[str, Any]:
    diagnosis = _gate_diagnosis(status_data)
    action = dict(diagnosis.get("next_action") or {})
    if action:
        action.setdefault("safe", True)
        action.setdefault("reason", "Next safe Patchbay step for the selected run.")
        return action
    return {
        "id": "inspect_status",
        "label": "Inspect status",
        "kind": "local_agent",
        "message": "status",
        "safe": True,
        "reason": "Inspect status and events before choosing another action.",
    }


def _gate_diagnosis(status_data: dict[str, Any]) -> dict[str, Any]:
    gate = status_data.get("gate_state", {}) or {}
    status_value = str(status_data.get("status") or "unknown")
    tests_status = str(gate.get("tests_status") or status_data.get("tests_status") or "NOT_RUN")
    review_result = gate.get("review_result") or status_data.get("review_result")
    checks = [
        {
            "key": "approval",
            "label": "Plan approval",
            "ok": bool(gate.get("approved")) or status_value not in {PLANNED},
            "status": "done" if gate.get("approved") else "pending",
            "detail": "Plan approval is recorded." if gate.get("approved") else "Plan has not been explicitly approved.",
        },
        {
            "key": "tests",
            "label": "Tests",
            "ok": bool(gate.get("tests_passed")),
            "status": tests_status,
            "detail": "Tests passed." if gate.get("tests_passed") else f"Tests are not passing yet (tests_status={tests_status}).",
        },
        {
            "key": "review",
            "label": "Review",
            "ok": review_result == "PASS",
            "status": review_result or "pending",
            "detail": "Review passed." if review_result == "PASS" else f"Review has not returned PASS (review_result={review_result or 'pending'}).",
        },
        {
            "key": "apply",
            "label": "Apply gate",
            "ok": bool(gate.get("ready_to_apply")),
            "status": "ready" if gate.get("ready_to_apply") else "blocked",
            "detail": "Apply can proceed with explicit confirmation."
            if gate.get("ready_to_apply")
            else "Apply is blocked until tests pass and review returns PASS.",
        },
    ]
    blockers = [item for item in checks if not item["ok"]]
    diagnosis = {
        "status": status_value,
        "ready_to_apply": bool(gate.get("ready_to_apply")),
        "tests_status": tests_status,
        "review_result": review_result,
        "blockers": blockers,
        "checks": checks,
    }
    diagnosis["next_action"] = _gate_next_action(status_data, diagnosis)
    return diagnosis


def _gate_next_action(status_data: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    blocker = status_data.get("blocked_next_action") if isinstance(status_data.get("blocked_next_action"), dict) else None
    if blocker:
        action = dict(blocker.get("action") or {}) if isinstance(blocker.get("action"), dict) else {}
        action.setdefault("id", "unblock_provider_command")
        action.setdefault("label", "Fix provider command")
        action.setdefault("kind", "local_agent")
        action.setdefault("safe", True)
        action.setdefault("reason", blocker.get("message") or blocker.get("suggested_next_action") or "Repair the blocked provider command.")
        return action

    status_value = str(status_data.get("status") or "unknown")
    if diagnosis.get("ready_to_apply"):
        return {
            "id": "apply",
            "label": "Apply reviewed diff",
            "kind": "local_agent",
            "message": "apply",
            "safe": False,
            "requires_confirmation": _confirmation("apply_approval", "apply", APPLY_CONFIRMATION),
            "reason": "Tests and review passed; apply still requires explicit confirmation.",
        }
    if status_value == PLANNED:
        return {
            "id": "approve_and_run",
            "label": "Approve plan",
            "kind": "local_agent",
            "message": "approve",
            "safe": False,
            "requires_confirmation": _confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
            "reason": "Plan approval is required before write/test/review phases can run.",
        }
    if status_value == REVIEWED_PASS and not status_data.get("tests_passed"):
        tests_status = str(diagnosis.get("tests_status") or "unknown")
        return {
            "id": "open_readiness",
            "label": "Configure tests",
            "kind": "local_agent",
            "message": "readiness",
            "safe": True,
            "reason": f"Tests are not passing yet (tests_status={tests_status}); configure tests or adjust the apply-without-tests policy.",
        }
    if status_value in {APPROVED, IMPLEMENTED, TESTED, REVIEWED_CHANGES_REQUESTED}:
        labels = {
            APPROVED: "Continue to write",
            IMPLEMENTED: "Continue to test",
            TESTED: "Continue to review",
            REVIEWED_CHANGES_REQUESTED: "Continue to fix",
        }
        reasons = {
            APPROVED: "Run the writer phase in the isolated Patchbay worktree.",
            IMPLEMENTED: "Run configured tests to create apply-gate evidence.",
            TESTED: "Run review so the apply gate can verify PASS.",
            REVIEWED_CHANGES_REQUESTED: "Run a fix/test/review loop before apply is allowed.",
        }
        return {
            "id": "continue",
            "label": labels.get(status_value, "Continue run"),
            "kind": "local_agent",
            "message": "continue",
            "safe": False,
            "reason": reasons.get(status_value, "Run the next Patchbay phase for the selected run."),
        }
    if status_value == FAILED:
        return {
            "id": "inspect_failure",
            "label": "Inspect failure",
            "kind": "diagnostic_tab",
            "tab": "Trace",
            "safe": True,
            "reason": "Inspect events and artifacts before retrying or starting a replacement task.",
        }
    if status_value == APPLIED:
        return {
            "id": "inspect_status",
            "label": "Inspect applied run",
            "kind": "local_agent",
            "message": "status",
            "safe": True,
            "reason": "Run has already been applied; inspect status/events or clean up the isolated worktree.",
        }
    if status_value in {IMPLEMENTING, TESTING, REVIEWING, FIXING}:
        return {
            "id": "poll_status",
            "label": "Poll status",
            "kind": "local_agent",
            "message": "status",
            "safe": True,
            "reason": "A phase is running; poll status, context, or events.",
        }
    return {
        "id": "inspect_status",
        "label": "Inspect status",
        "kind": "local_agent",
        "message": "status",
        "safe": True,
        "reason": "Inspect status and events before choosing another action.",
    }


def _gate_status_reply(run_id: str, diagnosis: dict[str, Any]) -> str:
    if diagnosis.get("ready_to_apply"):
        return f"Run {run_id} is through the technical gates; apply still requires explicit confirmation."
    blockers = diagnosis.get("blockers") or []
    if not blockers:
        return f"Run {run_id} has no detected gate blockers, but apply is not marked ready. Inspect status and events."
    details = "; ".join(f"{item.get('label')}: {item.get('detail')}" for item in blockers[:3])
    return f"Run {run_id} is blocked by {len(blockers)} gate check{'s' if len(blockers) != 1 else ''}: {details}"


def _gate_status_actions(run_id: str, status_data: dict[str, Any], *, include_open_run: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if include_open_run:
        actions.append(
            {
                "id": "open_latest_run",
                "label": "Open latest run",
                "kind": "open_run",
                "run_id": run_id,
                "safe": True,
                "reason": "Open the latest Patchbay run before choosing any gated action.",
            }
        )
    actions.append(
        {
            "id": "open_trace",
            "label": "Open activity",
            "kind": "diagnostic_tab",
            "tab": "Trace",
            "safe": True,
            "reason": "Inspect event and provider activity for gate evidence.",
        }
    )
    status_value = str(status_data.get("status") or "")
    if status_value == PLANNED:
        actions.append(
            {
                "id": "open_plan",
                "label": "Open plan",
                "kind": "diagnostic_tab",
                "tab": "Artifacts",
                "safe": True,
                "reason": "Review PLAN.md before explicit plan approval.",
            }
        )
    if status_value in {IMPLEMENTED, TESTED, REVIEWED_PASS, REVIEWED_CHANGES_REQUESTED}:
        actions.append(
            {
                "id": "open_diff",
                "label": "Open diff",
                "kind": "diagnostic_tab",
                "tab": "Diff",
                "safe": True,
                "reason": "Inspect the patch and evidence related to the apply gate.",
            }
        )
    actions.append(
        {
            "id": "open_readiness",
            "label": "Open readiness",
            "kind": "local_agent",
            "message": "readiness",
            "safe": True,
            "reason": "Run read-only setup diagnostics if a gate is blocked by local configuration.",
        }
    )
    return actions


def _reply_for_status(status_data: dict[str, Any]) -> str:
    if status_data.get("status") == PLANNED:
        return "Plan generated and waiting for approval."
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        return "Tests and review passed; waiting for explicit apply approval."
    if status_data.get("status") == FAILED:
        recovery = status_data.get("failure_recovery") or _failure_recovery_summary(status_data)
        return f"{recovery.get('summary')} Suggested next action: {recovery.get('suggested_next_action')}".strip()
    return f"Run status: {status_data.get('status')}."


def _failure_recovery_summary(status_data: dict[str, Any]) -> dict[str, Any]:
    stage = str(status_data.get("stage") or status_data.get("current_phase") or "unknown")
    suggested = str(status_data.get("suggested_next_action") or "Inspect artifacts and events before continuing.")
    actions = [
        {
            "id": "inspect_events",
            "label": "Inspect events",
            "kind": "diagnostic_tab",
            "tab": "Trace",
            "safe": True,
            "reason": "Open the event and trace timeline for the failed run.",
        },
        {
            "id": "inspect_artifacts",
            "label": "Inspect artifacts",
            "kind": "diagnostic_tab",
            "tab": "Artifacts",
            "safe": True,
            "reason": "Open available run artifacts before retrying.",
        },
        {
            "id": "start_new_task",
            "label": "Start replacement task",
            "kind": "focus_composer",
            "safe": True,
            "reason": "Start a narrower replacement task instead of retrying the failed run blindly.",
        },
    ]
    return {
        "stage": stage,
        "error": str(status_data.get("error") or "Run failed."),
        "suggested_next_action": suggested,
        "safe_actions": ["status", "events", "artifact", "diff", "new_run"],
        "actions": actions,
        "action_groups": group_actions(actions),
        "artifacts": list(status_data.get("artifacts") or []),
        "summary": f"Run failed in {stage}.",
    }


def _append_agent_event(root: Path, run_id: str, **kwargs: Any) -> None:
    run_path, _ = service._load_run(root, run_id)
    append_event(run_path, phase="agent", run_id=run_id, **kwargs)


def _append_agent_event_by_path(run_path: Path, *, run_id: str, **kwargs: Any) -> None:
    append_event(run_path, phase="agent", run_id=run_id, **kwargs)


def _agent_lock_path(run_path: Path) -> Path:
    return run_path / AGENT_LOCK_FILE


def _acquire_agent_lock(run_path: Path, *, token: str | None = None) -> None:
    path = _agent_lock_path(run_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get(INHERITED_AGENT_LOCK_ENV) == "agent" and path.exists():
        return
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        raise StateError(
            f"Agent is already running: {read_text(path, default='').strip()}",
            stage="agent",
            suggested_next_action="Poll agent status and events until the active run finishes.",
        )
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"pid={os.getpid()}\n")
        if token:
            handle.write(f"{token}\n")
        handle.write(f"started_at={time.time()}\n")


def _release_agent_lock(run_path: Path, *, token: str | None = None) -> None:
    path = _agent_lock_path(run_path)
    if not path.exists():
        return
    if token:
        lines = read_text(path, default="").splitlines()
        if token not in lines:
            return
    if path.exists():
        path.unlink()
