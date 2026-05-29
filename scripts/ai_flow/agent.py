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
from .artifacts import now_iso, read_text
from .config import load_config
from .config_wizard import run_config_wizard
from .doctor import run_doctor
from .errors import StateError
from .events import append_event
from .mcp_install import HOST_ALIASES, normalize_mcp_host
from .setup_flow import run_setup
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
        return _doctor_response(root)
    if intent == "help":
        return _help_response()
    if intent == "runs":
        return _runs_response(root)
    if intent == "profile_apply":
        return _profile_apply_response(root)
    if intent == "profile_show":
        return _profile_show_response(root)
    if intent == "missing_run":
        return _missing_run_response(root, text)
    if intent == "setup":
        return _setup_response(root, text)
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
    profile_intent = _config_profile_intent(text)
    if profile_intent:
        return profile_intent
    if _is_doctor_intent(text):
        return "doctor"
    if _is_help_intent(text):
        return "help"
    if _is_setup_intent(text):
        return "setup"
    if _is_metrics_intent(text):
        return "metrics" if has_run else "missing_run"
    if not has_run:
        if _is_runs_intent(text):
            return "runs"
        if _is_run_bound_intent(text):
            return "missing_run"
        return "start"
    if _has_any(text, ("apply", "应用", "套用")):
        return "apply"
    if _has_any(text, ("approve", "approved", "confirm", "确认", "批准", "同意")):
        return "approve_and_run"
    if _has_any(text, ("continue", "go on", "resume", "next", "继续", "推进", "下一步")):
        return "continue"
    if _has_any(text, ("diff", "patch", "补丁", "变更")):
        return "diff"
    if _is_metrics_intent(text):
        return "metrics"
    if _has_any(text, ("artifact", "plan", "review", "log", "产物", "计划", "日志")):
        return "artifact"
    return "status"


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text))


def _is_help_intent(text: str) -> bool:
    if text in {"?", "help", "usage", "commands", "帮助", "怎么用"}:
        return True
    words = _words(text)
    if words & TASK_INTENT_WORDS:
        return False
    return bool(words & {"help", "usage", "commands"}) and bool(words & {"patchbay", "agent", "command", "commands"})


def _is_runs_intent(text: str) -> bool:
    if text in {"status", "runs", "recent", "recent runs", "list runs", "show runs", "状态", "运行", "最近运行"}:
        return True
    words = _words(text)
    if words & TASK_INTENT_WORDS:
        return False
    if "runs" in words:
        return True
    if "status" in words:
        return bool(words & {"agent", "latest", "list", "patchbay", "recent", "run", "runs", "show", "current"})
    return "recent" in words and bool(words & {"run", "runs"})


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
    words = _words(text)
    routing_scope = {"cost", "deepseek", "economy", "profile", "reasonix", "route", "routing"}
    if "profile" in words and bool(words & {"show", "status", "read", "inspect"}):
        return "profile_show" if bool(words & routing_scope) else None
    if bool(words & {"deepseek", "economy", "reasonix"}) and bool(words & {"show", "status", "read", "inspect"}):
        return "profile_show"
    apply_words = {"apply", "enable", "route", "switch", "use"}
    write_fix_words = {"fix", "implementation", "repair", "write", "writer"}
    if bool(words & {"deepseek", "economy", "reasonix"}) and bool(words & apply_words):
        return "profile_apply"
    if bool(words & {"cheap", "cost", "lower", "low", "economy"}) and bool(words & {"model", "models", "routing", "route", "profile"}):
        return "profile_apply" if bool(words & (apply_words | write_fix_words | {"optimize"})) else "profile_show"
    return None


def _is_setup_intent(text: str) -> bool:
    if text in {"setup", "patchbay setup", "setup patchbay", "install patchbay", "patchbay install"}:
        return True
    if _has_any(text, ("初始化 patchbay", "安装 patchbay")):
        return True
    words = _words(text)
    if "patchbay" not in words:
        return False
    return bool(words & {"install", "installation", "setup"}) and not bool(words & TASK_INTENT_WORDS)


def _setup_host_from_message(text: str) -> str:
    normalized = re.sub(r"[\s_]+", " ", text.strip().lower().replace("-", " ").replace("=", " "))
    if not normalized:
        return "codex"
    host_phrases = sorted({_normalize_host_phrase(phrase) for phrase in HOST_ALIASES}, key=len, reverse=True)
    for phrase in host_phrases:
        if re.search(rf"(?:--host\s+|host\s+|for\s+|to\s+)?{re.escape(phrase)}\b", normalized):
            if phrase == "codex" and not re.search(r"(?:--host\s+|host\s+|for\s+|to\s+)codex\b", normalized):
                continue
            return normalize_mcp_host(phrase)
    return "codex"


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
    if words & TASK_INTENT_WORDS:
        return False
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
        "confirm",
        "continue",
        "cost",
        "diff",
        "events",
        "metrics",
        "log",
        "logs",
        "next",
        "patch",
        "review",
        "resume",
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
    if words & TASK_INTENT_WORDS:
        return False
    if words & {"approve", "approved", "confirm"}:
        return bool(words & {"approval", "current", "latest", "patchbay", "plan", "run", "this"})
    if words & {"continue", "resume"}:
        return bool(words & {"current", "last", "latest", "phase", "run", "step", "this", "worktree"})
    if "apply" in words:
        return bool(words & {"changes", "diff", "final", "patch", "reviewed"})
    if "next" in words:
        return bool(words & {"phase", "run", "step"})
    if words & {"artifact", "diff", "events", "log", "logs", "patch", "trace"}:
        return bool(words & {"current", "get", "last", "latest", "open", "run", "show", "this", "view"})
    if "review" in words:
        return bool(words & {"current", "get", "last", "latest", "open", "run", "show", "this", "view"})
    return False


def _is_doctor_intent(text: str) -> bool:
    if text in {"doctor", "readiness", "diagnose", "diagnostic", "diagnostics", "诊断"}:
        return True
    if _has_any(text, ("就绪", "安装检查", "配置检查")):
        return True
    words = _words(text)
    if words & TASK_INTENT_WORDS:
        return False
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


def _help_response() -> dict[str, Any]:
    capabilities = [
        {
            "name": "setup",
            "summary": "Send `patchbay setup` for Codex or `patchbay setup for Claude Desktop` / `install patchbay for Gemini CLI` to initialize project files, local config, Skill installation, host MCP guidance, and a doctor summary.",
        },
        {
            "name": "start",
            "summary": "Send a task to create a plan; implementation still waits for explicit plan approval.",
        },
        {
            "name": "readiness",
            "summary": "Send `readiness` or `patchbay doctor` to inspect setup without creating a run.",
        },
        {
            "name": "economy-profile",
            "summary": "Send `apply economy profile` to route high-volume write/fix work to Reasonix/DeepSeek without starting a run.",
        },
        {
            "name": "status",
            "summary": "Send `status` without a run_id to list recent runs, or with a run_id to inspect one run.",
        },
        {
            "name": "metrics",
            "summary": "Send `metrics`, `cost`, or `tokens` with a run_id to inspect run efficiency evidence.",
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
    return _stateless_response(
        action="help",
        reply="Patchbay Agent can run setup, start a gated run, report readiness, apply economy routing, list recent runs, continue a run, show artifacts/diff, and apply only after explicit approval.",
        next_actions=["setup", "start", "readiness", "apply economy profile", "runs"],
        extra={"capabilities": capabilities},
    )


def _setup_response(root: Path, message: str) -> dict[str, Any]:
    host = _setup_host_from_message(message)
    result = run_setup(root, host=host)
    next_actions = list(result.get("next_actions") or [])
    actions = list(result.get("actions") or [])
    reply = "Patchbay setup completed."
    if next_actions:
        reply = "Patchbay setup completed with follow-up steps: " + " ".join(next_actions)
    return _stateless_response(
        action="setup",
        reply=reply,
        ok=bool(result.get("ok")),
        error=None if result.get("ok") else reply,
        next_actions=next_actions or ["readiness", "start"],
        extra={"setup": result, "setup_host": result.get("setup_host") or host, "actions": actions},
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


def _metrics_response(root: Path, run_id: str) -> dict[str, Any]:
    result = service.metrics(root, run_id)
    run_metrics = result.get("run_metrics") or {}
    attempts = sum(int(value or 0) for value in (run_metrics.get("phase_attempts") or {}).values())
    providers = [item for item in (run_metrics.get("provider_usage") or []) if item.get("provider") or item.get("model")]
    cost = run_metrics.get("cost") or {}
    token_usage = run_metrics.get("token_usage") or {}
    routing = result.get("routing_evidence") or run_metrics.get("routing_evidence") or {}
    signals = [
        f"{attempts} phase attempt{'s' if attempts != 1 else ''}",
        f"{len(providers)} provider trace entr{'ies' if len(providers) != 1 else 'y'}",
        "cost known" if cost.get("known") else "cost not reported",
        "tokens known" if token_usage.get("known") else "tokens not reported",
    ]
    if isinstance(routing, dict) and routing.get("summary"):
        health = routing.get("economy_health") if isinstance(routing.get("economy_health"), dict) else {}
        if health.get("status"):
            signals.append(f"economy health {health['status']}")
        signals.append(str(routing["summary"]))
    metrics_payload = dict(result)
    if routing:
        metrics_payload["routing_evidence"] = routing
    actions = list(result.get("actions") or (routing.get("actions") if isinstance(routing, dict) else []) or [])
    return {
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
    }


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
    if words & {"diff", "patch"} or _has_any(normalized, ("琛ヤ竵", "鍙樻洿")):
        return {"tab": "Diff", "reason": "The prompt asked for the run diff or patch."}
    if words & {"events", "trace"} or _has_any(normalized, ("浜嬩欢", "璺熻釜")):
        return {"tab": "Trace", "reason": "The prompt asked for run events or trace."}
    if words & {"log", "logs"} or _has_any(normalized, ("鏃ュ織",)):
        return {"tab": "Log", "reason": "The prompt asked for run logs."}
    if words & {"artifact", "artifacts", "plan", "review"} or _has_any(normalized, ("浜х墿", "璁″垝")):
        return {"tab": "Artifacts", "reason": "The prompt asked for run artifacts."}
    return None


def _doctor_response(root: Path) -> dict[str, Any]:
    report = run_doctor(root, include_mcp=False)
    next_actions = list(report.get("next_actions") or [])
    recommendations = list(report.get("recommendations") or [])
    actions = list(report.get("actions") or [])
    suggested_actions = _doctor_suggested_actions(next_actions, recommendations)
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
        extra={"doctor": report, "recommendations": recommendations, "actions": actions},
    )


def _doctor_suggested_actions(next_actions: list[str], recommendations: list[str]) -> list[str]:
    actions = list(next_actions)
    if any("config profile apply economy" in item or "Reasonix/DeepSeek" in item for item in recommendations):
        actions.append("apply economy profile")
    return _dedupe_strings(actions)


def _profile_routing_digest(profile_result: dict[str, Any]) -> dict[str, Any]:
    status = profile_result.get("status") if isinstance(profile_result.get("status"), dict) else profile_result
    economy = status.get("economy") if isinstance(status.get("economy"), dict) else {}
    write = _phase_route_snapshot(economy.get("write") if isinstance(economy.get("write"), dict) else {})
    fix = _phase_route_snapshot(economy.get("fix") if isinstance(economy.get("fix"), dict) else {})
    economy_active = bool(economy.get("matches"))
    recommendation = str(status.get("recommendation") or profile_result.get("recommendation") or "")
    return {
        "profile": status.get("profile") or profile_result.get("profile") or ("economy" if economy_active else "custom"),
        "target": {"provider": service.ECONOMY_PROVIDER, "model": service.ECONOMY_MODEL},
        "economy_configured": economy_active,
        "phase_strategy": status.get("phase_strategy") or {},
        "phases": {
            "write": {"configured": write, "configured_economy": _phase_is_economy(write)},
            "fix": {"configured": fix, "configured_economy": _phase_is_economy(fix)},
        },
        "summary": _profile_routing_summary(economy_active=economy_active, write=write, fix=fix),
        "recommendation": recommendation,
    }


def _phase_route_snapshot(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": str(route.get("provider") or ""),
        "model": str(route.get("model") or ""),
        "command_key": str(route.get("command_key") or ""),
    }


def _phase_is_economy(route: dict[str, Any]) -> bool:
    return route.get("provider") == service.ECONOMY_PROVIDER and route.get("model") == service.ECONOMY_MODEL


def _route_label(route: dict[str, Any]) -> str:
    provider = str(route.get("provider") or "-")
    model = str(route.get("model") or "")
    return f"{provider} / {model}" if model else provider


def _profile_routing_summary(*, economy_active: bool, write: dict[str, Any], fix: dict[str, Any]) -> str:
    prefix = "Economy routing profile is active" if economy_active else "Economy routing profile is not active"
    return f"{prefix}: write {_route_label(write)}, fix {_route_label(fix)}."


def _profile_apply_response(root: Path) -> dict[str, Any]:
    result = run_config_wizard(root, profile="economy")
    status = result.get("status") or {}
    write = ((status.get("economy") or {}).get("write") or {})
    fix = ((status.get("economy") or {}).get("fix") or {})
    routing = _profile_routing_digest(result)
    reply = (
        "Economy routing profile applied. High-volume write/fix work now routes to "
        f"{write.get('provider') or 'reasonix_cli'} / {write.get('model') or 'deepseek-v4-pro'}."
    )
    if fix:
        reply += f" Fix uses {fix.get('provider') or '-'} / {fix.get('model') or '-'}."
    reply += f" {routing['summary']}"
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


def _profile_show_response(root: Path) -> dict[str, Any]:
    result = run_config_wizard(root, show_profile=True)
    profile = str(result.get("profile") or "custom")
    routing = _profile_routing_digest(result)
    reply = str(routing["summary"])
    if not routing.get("economy_configured"):
        reply += " " + str(result.get("recommendation") or "Run `patchbay config profile apply economy`.")
    return _stateless_response(
        action="profile_show",
        reply=reply,
        next_actions=list(result.get("next_actions") or (["readiness", "start"] if profile == "economy" else ["apply economy profile", "readiness"])),
        extra={"profile": result, "routing": routing, "actions": list(result.get("actions") or [])},
    )


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
    return response


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


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
    if current.get("failure_recovery"):
        response["recovery"] = current["failure_recovery"]
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
        recovery = status_data.get("failure_recovery") or _failure_recovery_summary(status_data)
        return f"{recovery.get('summary')} Suggested next action: {recovery.get('suggested_next_action')}".strip()
    return f"Run status: {status_data.get('status')}."


def _failure_recovery_summary(status_data: dict[str, Any]) -> dict[str, Any]:
    stage = str(status_data.get("stage") or status_data.get("current_phase") or "unknown")
    suggested = str(status_data.get("suggested_next_action") or "Inspect artifacts and events before continuing.")
    return {
        "stage": stage,
        "error": str(status_data.get("error") or "Run failed."),
        "suggested_next_action": suggested,
        "safe_actions": ["status", "events", "artifact", "diff", "new_run"],
        "actions": [
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
        ],
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
