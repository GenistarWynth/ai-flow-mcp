from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from . import service
from .artifacts import now_iso, read_text
from .config import load_config
from .errors import StateError
from .events import append_event
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
        return _agent_response(
            root,
            run_id,
            action="start",
            reply="Plan generated. Review PLAN.md, then approve before implementation.",
            requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
            include=_merge_include(include, {"plan": True, "events_since": 0}),
        )

    if not run_id:
        return _error_response("Continuing a Patchbay run requires run_id.", action=intent)

    if intent == "approve_and_run":
        if confirmation != PLAN_CONFIRMATION:
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
            extra={"autopilot": autopilot},
        )
        return _with_autopilot_error(response, autopilot)

    if intent == "apply":
        current = service.status(root, run_id)
        if not _apply_ready(current):
            message = "Apply is blocked until tests pass and review returns PASS."
            return _agent_response(
                root,
                run_id,
                action="apply",
                reply=message,
                include=include,
                extra={"ok": False, "error": message},
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

    if intent == "diff":
        return _agent_response(root, run_id, action="diff", reply="Current final diff.", include=_merge_include(include, {"diff": True}))

    if intent == "artifact":
        return _agent_response(
            root,
            run_id,
            action="artifact",
            reply="Requested run artifacts.",
            include=_merge_include(include, {"plan": True, "review": True}),
        )

    return agent_status(root, run_id, since=int((include or {}).get("events_since", 0) or 0), include=include)


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
        return _background_pending_response(
            action="start",
            run_id=str(job["run_id"]),
            reply="Planning started in the background. Poll status, context, or events for progress.",
            job=job,
        )

    if not run_id:
        return _error_response("Continuing a Patchbay run requires run_id.", action=intent)

    if intent in {"diff", "artifact", "status"}:
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

    if intent == "approve_and_run" and confirmation != PLAN_CONFIRMATION:
        return _agent_response(
            root,
            run_id,
            action="approve_and_run",
            reply="Implementation requires explicit plan approval.",
            requires_confirmation=_confirmation("plan_approval", "approve_and_run", PLAN_CONFIRMATION),
            include=_merge_include(include, {"plan": True}),
        )

    current = service.status(root, run_id)
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
    service._record_job(run_path, job)
    response = _agent_response(
        root,
        run_id,
        action=intent,
        reply="Background agent turn started. Poll status, context, or events for progress.",
        include=include,
        extra={"background": True, "job": job},
    )
    response["requires_confirmation"] = None
    response["next_actions"] = ["status", "events"]
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
import os
import sys
from pathlib import Path

root = Path(os.environ["PATCHBAY_BACKGROUND_ROOT"])
source_scripts = Path(os.environ.get("PATCHBAY_BACKGROUND_SOURCE_SCRIPTS", ""))
for candidate in (root / "scripts", source_scripts):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from ai_flow.cli import main
    raise SystemExit(main(sys.argv[1:]))
finally:
    run_dir = os.environ.get("PATCHBAY_BACKGROUND_RUN_DIR")
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
                _append_agent_event(
                    root,
                    run_id,
                    action="stopped",
                    status="FAILED",
                    detail=str(current.get("error") or "Run failed."),
                    next_action="inspect",
                )
                return _autopilot_result(root, run_id, "Run failed. Inspect artifacts and events before continuing.", ok=False, error=str(current.get("error") or "Run failed."))
            if status_value == APPLIED:
                return _autopilot_result(root, run_id, "Reviewed diff is already applied.")
            return _autopilot_result(root, run_id, f"Current status is {status_value}; no automatic action is available.")
        return _autopilot_result(root, run_id, "Agent stopped after reaching the internal step limit.", ok=False, error="step limit reached")
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
    if not has_run:
        return "start"
    if _has_any(text, ("apply", "应用", "套用")):
        return "apply"
    if _has_any(text, ("approve", "approved", "confirm", "确认", "批准", "同意")):
        return "approve_and_run"
    if _has_any(text, ("continue", "go on", "resume", "next", "继续", "推进", "下一步")):
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
    include_trace = bool(effective_include.get("include_trace", False))
    response: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "action": action,
        "reply": reply,
        "run_id": run_id,
        "status": current,
        "context": service.context(root, run_id, since_event=since, include_trace=include_trace),
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
        "context": None,
        "events": None,
        "artifacts": {},
        "diff": None,
        "requires_confirmation": None,
        "next_actions": [],
        "error": message,
    }


def _background_pending_response(*, action: str, run_id: str, reply: str, job: dict[str, Any]) -> dict[str, Any]:
    return {
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
        "next_actions": ["status", "events"],
        "error": None,
        "background": True,
        "job": job,
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
        return "Plan generated and waiting for approval."
    if status_data.get("gate_state", {}).get("ready_to_apply"):
        return "Tests and review passed; waiting for explicit apply approval."
    if status_data.get("status") == FAILED:
        return f"Run failed in {status_data.get('stage') or 'unknown'}: {status_data.get('error') or ''}".strip()
    return f"Run status: {status_data.get('status')}."


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
