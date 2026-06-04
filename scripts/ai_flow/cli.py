from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import service
from .agent import APPLY_CONFIRMATION, agent_message
from .config_wizard import run_config_wizard
from .doctor import run_doctor
from .errors import AiFlowError, StateError
from .mcp_install import run_mcp_install, run_mcp_doctor
from .setup_flow import run_setup
from .skill_install import run_skill_doctor, run_skill_install, run_skill_print
from .web_server import serve as serve_web


SKILL_HOST_HELP = "Skill host or Codex alias: codex, Codex CLI, Codex Desktop, Codex 桌面."


def config_wizard_run(cwd: Path, args: argparse.Namespace) -> Any:
    config_command = getattr(args, "config_command", "")
    if config_command == "show":
        return run_config_wizard(cwd, show=True)
    if config_command == "phase":
        return run_config_wizard(
            cwd,
            phase=args.phase,
            provider=args.provider,
            model=args.model,
            command_key=args.command_key,
        )
    if config_command == "command":
        return run_config_wizard(cwd, command_key_name=args.key, command_value=args.value)
    if config_command == "test":
        return run_config_wizard(cwd, test_command=args.test_command)
    if config_command == "provider":
        return run_config_wizard(
            cwd,
            provider_id=args.provider_id,
            provider_roles=args.roles,
            provider_command=args.provider_command,
            provider_args=args.args,
            prompt_mode=args.prompt_mode,
            output_contract=args.output_contract,
            activate_economy=args.activate_economy,
            economy_model=args.economy_model,
            economy_label=args.economy_label,
        )
    if config_command == "profile":
        if args.profile_command == "apply":
            return run_config_wizard(cwd, profile=args.profile)
        if args.profile_command == "show":
            return run_config_wizard(cwd, show_profile=True)
    return run_config_wizard(
        cwd,
        set_key=args.set_key,
        set_value=args.set_value,
        doctor=args.doctor,
    )


def mcp_dispatch(cwd: Path, args: argparse.Namespace) -> Any:
    mcp_cmd = getattr(args, "mcp_command", "")
    if mcp_cmd == "install":
        return run_mcp_install(
            cwd,
            args.host,
            root=getattr(args, "root", "") or None,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
    if mcp_cmd == "doctor":
        return run_mcp_doctor(cwd, root=getattr(args, "root", "") or None)
    raise AiFlowError(
        "Missing MCP subcommand. Try: patchbay mcp install codex  or  patchbay mcp doctor",
        stage="config",
    )


def skill_dispatch(cwd: Path, args: argparse.Namespace) -> Any:
    skill_cmd = getattr(args, "skill_command", "")
    if skill_cmd == "install":
        return run_skill_install(cwd, host=args.host, path=getattr(args, "path", "") or None, dry_run=bool(getattr(args, "dry_run", False)))
    if skill_cmd == "print":
        return run_skill_print(cwd, host=args.host)
    if skill_cmd == "doctor":
        return run_skill_doctor(cwd, host=args.host, path=getattr(args, "path", "") or None)
    raise AiFlowError(
        "Missing skill subcommand. Try: patchbay skill install codex  or  patchbay skill doctor codex",
        stage="skill",
    )


def _print_result(data: Any, *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            else:
                print(f"{key}: {value}")
    else:
        print(data)


def _action_guard(action: dict[str, Any] | None) -> str:
    if not isinstance(action, dict) or not action:
        return "-"
    confirmation = action.get("requires_confirmation")
    if isinstance(confirmation, dict):
        token = confirmation.get("confirmation") or confirmation.get("type") or "required"
        return f"confirmation:{token}"
    if action.get("safe") is False:
        return "manual"
    return "safe"


def _action_label(action: dict[str, Any] | None) -> str:
    if not isinstance(action, dict):
        return "-"
    return str(action.get("label") or action.get("id") or action.get("name") or action.get("message") or "-")


def _action_summary(action: dict[str, Any] | None) -> str:
    label = _action_label(action)
    if label == "-":
        return "-"
    return f"{label} ({_action_guard(action)})"


def _action_detail(action: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("run_id", "tab", "message", "command", "host"):
        value = action.get(key)
        if isinstance(value, str) and value:
            parts.append(f"{key}={value}")
    return f" [{', '.join(parts)}]" if parts else ""


def _print_actions(actions: list[Any], *, title: str = "Actions") -> None:
    printable = [action for action in actions if isinstance(action, dict)]
    if not printable:
        return
    print(title + ":")
    for action in printable:
        print(f"- {_action_summary(action)}{_action_detail(action)}")


def _print_grouped_actions(actions: list[Any], groups: list[Any]) -> None:
    printable = [action for action in actions if isinstance(action, dict)]
    if not printable:
        return
    by_id = {
        str(action.get("id") or action.get("name")): action
        for action in printable
        if action.get("id") or action.get("name")
    }
    printed: set[int] = set()
    if groups:
        print("Actions:")
        for group in groups:
            if not isinstance(group, dict):
                continue
            action_ids = group.get("action_ids") if isinstance(group.get("action_ids"), list) else []
            group_actions = [by_id[str(action_id)] for action_id in action_ids if str(action_id) in by_id]
            if not group_actions:
                continue
            print(f"{group.get('label') or group.get('id') or 'Group'}:")
            for action in group_actions:
                if id(action) in printed:
                    continue
                printed.add(id(action))
                print(f"- {_action_summary(action)}{_action_detail(action)}")
    remaining = [action for action in printable if id(action) not in printed]
    if remaining:
        _print_actions(remaining, title="Actions" if not printed else "Other actions")


def _check_status(check: Any) -> str:
    if not isinstance(check, dict):
        return str(check)
    if check.get("skipped"):
        return "skipped"
    status = check.get("status")
    if isinstance(status, str) and status:
        return status
    if "ready" in check:
        return "ready" if check.get("ready") else "not ready"
    if "ok" in check:
        return "ok" if check.get("ok") else "needs attention"
    return "unknown"


def _print_readiness_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")

    doctor = data.get("doctor") if isinstance(data.get("doctor"), dict) else data
    ok = bool(doctor.get("ok"))
    print(f"Patchbay readiness: {'ready' if ok else 'needs attention'}")
    root = doctor.get("root")
    host = doctor.get("host")
    if root:
        print(f"root: {root}")
    if host:
        print(f"host: {host}")

    checks = doctor.get("checks") if isinstance(doctor.get("checks"), dict) else {}
    if checks:
        print("Checks:")
        for name, check in checks.items():
            print(f"- {name}: {_check_status(check)}")

    routing = data.get("routing") if isinstance(data.get("routing"), dict) else doctor.get("routing")
    if isinstance(routing, dict):
        summary = routing.get("summary")
        workload_policy = routing.get("workload_policy") if isinstance(routing.get("workload_policy"), dict) else {}
        if not summary:
            summary = workload_policy.get("summary")
        if summary:
            print(f"Routing: {summary}")

    recommendations = data.get("recommendations") or doctor.get("recommendations") or []
    if isinstance(recommendations, list) and recommendations:
        print("Recommendations:")
        for item in recommendations:
            print(f"- {item}")

    actions = data.get("actions") if isinstance(data.get("actions"), list) else doctor.get("actions")
    groups = data.get("action_groups") if isinstance(data.get("action_groups"), list) else doctor.get("action_groups")
    if isinstance(actions, list):
        if actions:
            print("")
        _print_grouped_actions(actions, groups if isinstance(groups, list) else [])


def _setup_step_status(step: Any) -> str:
    if not isinstance(step, dict):
        return "-"
    if step.get("skipped"):
        reason = step.get("reason")
        return f"skipped ({reason})" if reason else "skipped"
    if step.get("dry_run"):
        return "dry run"
    if step.get("created"):
        return "created"
    if step.get("installed"):
        return "installed"
    if step.get("executed"):
        return "executed"
    if step.get("exists"):
        return "exists"
    if step.get("ok"):
        return "ok"
    return "ready"


def _print_setup_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")

    setup = data.get("setup") if isinstance(data.get("setup"), dict) else data
    mode = "dry run" if setup.get("dry_run") else "applied" if setup.get("applied") else "not applied"
    print(f"Patchbay setup: {mode}")
    root = setup.get("root")
    host = setup.get("setup_host")
    if root:
        print(f"root: {root}")
    if host:
        print(f"host: {host}")

    init = setup.get("init") if isinstance(setup.get("init"), dict) else {}
    if init:
        would_create = init.get("would_create") if isinstance(init.get("would_create"), list) else []
        suffix = f"; would create {len(would_create)} paths" if would_create else ""
        print(f"init: {_setup_step_status(init)}{suffix}")

    config = setup.get("config") if isinstance(setup.get("config"), dict) else {}
    if config:
        path = config.get("path")
        print(f"config: {_setup_step_status(config)}" + (f" [{path}]" if path else ""))

    skill = setup.get("skill") if isinstance(setup.get("skill"), dict) else {}
    if skill:
        destination = skill.get("destination")
        print(f"skill: {_setup_step_status(skill)}" + (f" [{destination}]" if destination else ""))

    mcp = setup.get("mcp") if isinstance(setup.get("mcp"), dict) else {}
    if mcp:
        command = mcp.get("command")
        print(f"mcp: {_setup_step_status(mcp)}" + (f" [{command}]" if command else ""))

    doctor = setup.get("doctor") if isinstance(setup.get("doctor"), dict) else None
    if doctor:
        print("")
        _print_readiness_result(
            {
                "doctor": doctor,
                "routing": setup.get("routing") or data.get("routing"),
                "recommendations": setup.get("recommendations") or data.get("recommendations"),
                "actions": setup.get("actions") or data.get("actions"),
                "action_groups": setup.get("action_groups") or data.get("action_groups"),
            }
        )


def _phase_summary(name: str, phase: Any) -> str:
    if not isinstance(phase, dict):
        return f"{name}: -"
    if phase.get("error"):
        return f"{name}: error ({phase.get('error')})"
    tier = str(phase.get("tier") or "-")
    provider = str(phase.get("provider") or "-")
    model = str(phase.get("model") or "-")
    route = "economy route" if phase.get("economy_route") else "supervision route"
    command = phase.get("command_status") if isinstance(phase.get("command_status"), dict) else {}
    command_suffix = ""
    if command.get("required"):
        command_suffix = f"; command {_check_status(command)}"
    return f"{name}: {tier} | {provider} / {model} | {route}{command_suffix}"


def _print_profile_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")

    payload = data.get("profile") if isinstance(data.get("profile"), dict) else data
    status = payload.get("status") if isinstance(payload.get("status"), dict) else payload
    routing = data.get("routing") if isinstance(data.get("routing"), dict) else {}
    if not routing and isinstance(payload.get("routing"), dict):
        routing = payload["routing"]

    profile_name = status.get("profile") or payload.get("profile") or data.get("profile") or "-"
    print(f"Patchbay profile: {profile_name}")
    config = payload.get("config") or data.get("config")
    if config:
        print(f"config: {config}")

    summary = payload.get("summary") or routing.get("summary")
    workload = routing.get("workload_policy") if isinstance(routing.get("workload_policy"), dict) else {}
    if not summary:
        summary = workload.get("summary")
    economy = status.get("economy") if isinstance(status.get("economy"), dict) else {}
    if not summary:
        summary = economy.get("intent")
    if summary:
        print(f"summary: {summary}")

    target = economy.get("target") if isinstance(economy.get("target"), dict) else {}
    if target:
        target_label = target.get("label") or target.get("provider") or "-"
        print(f"target: {target_label} ({target.get('provider') or '-'} / {target.get('model') or '-'})")
    if "command_ready" in economy:
        print(f"economy command: {'ready' if economy.get('command_ready') else 'needs attention'}")

    phases = status.get("phase_strategy") if isinstance(status.get("phase_strategy"), dict) else routing.get("phase_strategy")
    if isinstance(phases, dict) and phases:
        print("Phase routing:")
        for phase in ("plan", "write", "fix", "review"):
            if phase in phases:
                print(f"- {_phase_summary(phase, phases[phase])}")

    recommendation = status.get("recommendation") or payload.get("recommendation") or routing.get("recommendation")
    if recommendation:
        print(f"recommendation: {recommendation}")

    next_actions = payload.get("next_actions") or data.get("next_actions") or []
    if isinstance(next_actions, list) and next_actions:
        print("Next actions:")
        for item in next_actions:
            print(f"- {item}")

    actions = data.get("actions") if isinstance(data.get("actions"), list) else payload.get("actions")
    groups = data.get("action_groups") if isinstance(data.get("action_groups"), list) else payload.get("action_groups")
    if isinstance(actions, list):
        if actions:
            print("")
        _print_grouped_actions(actions, groups if isinstance(groups, list) else [])


def _duration_label(value: Any) -> str:
    if value is None:
        return "-"
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return str(value)
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms}ms"


def _percent_suffix(value: Any) -> str:
    return f" ({value}%)" if value is not None else ""


def _tier_summary(name: str, bucket: Any) -> str:
    if not isinstance(bucket, dict):
        return f"{name}: -"
    label = str(bucket.get("label") or name)
    phases = bucket.get("phases") if isinstance(bucket.get("phases"), list) else []
    phase_text = "/".join(str(phase) for phase in phases) if phases else "-"
    parts: list[str] = []
    if bucket.get("duration_known"):
        parts.append(f"{_duration_label(bucket.get('duration_ms'))}{_percent_suffix(bucket.get('duration_percent'))}")
    tokens = bucket.get("token_usage") if isinstance(bucket.get("token_usage"), dict) else {}
    if tokens.get("known"):
        parts.append(f"{tokens.get('total_tokens')} tokens{_percent_suffix(tokens.get('token_percent'))}")
    cost = bucket.get("cost") if isinstance(bucket.get("cost"), dict) else {}
    if cost.get("known"):
        parts.append(f"{cost.get('currency') or 'USD'} {cost.get('estimated_total')}{_percent_suffix(cost.get('cost_percent'))}")
    usage = ", ".join(parts) if parts else "usage not reported"
    return f"{label}: {phase_text}; {usage}"


def _provider_summary(item: Any) -> str:
    if not isinstance(item, dict):
        return "-"
    phase = item.get("phase") or "-"
    provider = item.get("provider") or "-"
    model = item.get("model") or "-"
    parts = [f"{phase}: {provider} / {model}"]
    command_key = item.get("command_key")
    if command_key:
        parts.append(f"command={command_key}")
    if item.get("duration_ms"):
        parts.append(f"duration={_duration_label(item.get('duration_ms'))}")
    token_usage = item.get("token_usage") if isinstance(item.get("token_usage"), dict) else {}
    if token_usage.get("known"):
        parts.append(f"tokens={token_usage.get('total_tokens')}")
    cost = item.get("cost") if isinstance(item.get("cost"), dict) else {}
    if cost.get("known"):
        parts.append(f"cost={cost.get('currency') or 'USD'} {cost.get('estimated_total')}")
    return " | ".join(parts)


def _print_metrics_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")

    payload = data.get("metrics") if isinstance(data.get("metrics"), dict) else data
    run_id = payload.get("run_id") or data.get("run_id") or "-"
    print(f"Patchbay metrics: {run_id}")
    status = payload.get("status")
    phase = payload.get("current_phase")
    if status or phase:
        print(f"status: {status or '-'} | phase: {phase or '-'}")

    efficiency = payload.get("efficiency_summary") if isinstance(payload.get("efficiency_summary"), dict) else {}
    summary = efficiency.get("summary")
    if summary:
        print(f"Efficiency: {summary}")
    recommendation = efficiency.get("recommendation")
    if recommendation:
        print(f"recommendation: {recommendation}")

    routing = payload.get("routing_evidence") if isinstance(payload.get("routing_evidence"), dict) else {}
    health = routing.get("economy_health") if isinstance(routing.get("economy_health"), dict) else {}
    if routing.get("summary"):
        print(f"Routing: {routing.get('summary')}")
    if health:
        print(f"economy health: {health.get('status') or '-'} ({health.get('severity') or '-'})")

    run_metrics = payload.get("run_metrics") if isinstance(payload.get("run_metrics"), dict) else {}
    tiers = run_metrics.get("tier_usage") if isinstance(run_metrics.get("tier_usage"), dict) else {}
    if tiers:
        print("Tier usage:")
        for tier in ("economy", "supervision", "execution"):
            if tier in tiers:
                print(f"- {_tier_summary(tier, tiers[tier])}")

    providers = run_metrics.get("provider_usage") if isinstance(run_metrics.get("provider_usage"), list) else []
    if providers:
        print("Provider usage:")
        for item in providers[:8]:
            print(f"- {_provider_summary(item)}")
        if len(providers) > 8:
            print(f"- ... {len(providers) - 8} more")

    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else data.get("actions")
    groups = payload.get("action_groups") if isinstance(payload.get("action_groups"), list) else data.get("action_groups")
    if isinstance(actions, list):
        if actions:
            print("")
        _print_grouped_actions(actions, groups if isinstance(groups, list) else [])


def _short_text(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _print_next_actions(data: dict[str, Any]) -> None:
    next_actions = data.get("next_actions")
    if not isinstance(next_actions, list) or not next_actions:
        return
    print("Next actions:")
    for item in next_actions:
        if isinstance(item, dict):
            print(f"- {_action_summary(item)}{_action_detail(item)}")
        else:
            print(f"- {item}")


def _run_reference_line(run: dict[str, Any]) -> str:
    run_id = run.get("run_id") or "-"
    status = run.get("status") or "-"
    task = _short_text(run.get("task") or run.get("title") or "-", limit=90)
    return f"{run_id} | {status} | {task}"


def _print_run_reference(title: str, value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    print(f"{title}: {_run_reference_line(value)}")
    action = value.get("next_action")
    if not isinstance(action, dict):
        inbox = value.get("inbox") if isinstance(value.get("inbox"), dict) else {}
        action = inbox.get("next_action") if isinstance(inbox.get("next_action"), dict) else {}
    if action:
        print(f"{title.lower()} next_action: {_action_summary(action)}")


def _print_capabilities(capabilities: Any) -> None:
    if not isinstance(capabilities, list) or not capabilities:
        return
    print("Capabilities:")
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        name = capability.get("name") or "-"
        summary = _short_text(capability.get("summary"), limit=220)
        print(f"- {name}: {summary}")


def _print_gate_diagnosis(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    print("Gate diagnosis:")
    for key in ("status", "summary", "reason", "blocker", "message"):
        item = value.get(key)
        if item:
            print(f"- {key}: {_short_text(item)}")
    blockers = value.get("blockers") if isinstance(value.get("blockers"), list) else []
    for blocker in blockers:
        print(f"- blocker: {_short_text(blocker)}")
    action = value.get("next_action") if isinstance(value.get("next_action"), dict) else {}
    if action:
        print(f"- next_action: {_action_summary(action)}")


def _print_agent_guidance_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")

    action = str(data.get("action") or "agent")
    labels = {
        "help": "help",
        "local_mode": "local mode",
        "next_step": "next step",
        "gate_status": "gate status",
    }
    print(f"Patchbay {labels.get(action, action.replace('_', ' '))}:")

    local_mode = data.get("local_mode") if isinstance(data.get("local_mode"), dict) else {}
    if local_mode:
        print(f"- skip_mcp: {bool(local_mode.get('skip_mcp'))}")
        print(f"- requires_run_for_unattended_approval: {bool(local_mode.get('requires_run_for_unattended_approval'))}")
        print(f"- apply_requires_confirmation: {bool(local_mode.get('apply_requires_confirmation'))}")

    _print_capabilities(data.get("capabilities"))
    _print_run_reference("Run reference", data.get("run_reference"))
    _print_run_reference("Recent run", data.get("recent_run"))

    runs = data.get("runs") if isinstance(data.get("runs"), dict) else {}
    if runs:
        print("")
        _print_runs_result(runs, inbox_only=True)

    latest_status = data.get("latest_status") if isinstance(data.get("latest_status"), dict) else {}
    failure = latest_status.get("failure_recovery") if isinstance(latest_status.get("failure_recovery"), dict) else {}
    if failure.get("summary"):
        print(f"Failure recovery: {_short_text(failure.get('summary'), limit=220)}")

    _print_gate_diagnosis(data.get("gate_diagnosis"))
    _print_background_job(data.get("background_job"), include_actions=False)

    next_action = data.get("next_action") if isinstance(data.get("next_action"), dict) else {}
    if next_action:
        print(f"next_action: {_action_summary(next_action)}{_action_detail(next_action)}")
    _print_next_actions(data)

    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    groups = data.get("action_groups") if isinstance(data.get("action_groups"), list) else []
    if actions:
        print("")
        _print_grouped_actions(actions, groups)


def _print_gate_state(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    print(
        "Gate state: "
        f"approved={bool(value.get('approved'))}, "
        f"tests={value.get('tests_status') or '-'}, "
        f"review={value.get('review_result') or '-'}, "
        f"ready_to_apply={bool(value.get('ready_to_apply'))}"
    )


def _print_failure_recovery(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    print("Failure recovery:")
    for key in ("stage", "error", "suggested_next_action", "summary"):
        item = value.get(key)
        if item:
            print(f"- {key}: {_short_text(item, limit=220)}")
    artifacts = value.get("artifacts") if isinstance(value.get("artifacts"), list) else []
    if artifacts:
        print(f"- artifacts: {', '.join(str(item) for item in artifacts[:8])}")
    actions = value.get("actions") if isinstance(value.get("actions"), list) else []
    groups = value.get("action_groups") if isinstance(value.get("action_groups"), list) else []
    if actions:
        _print_grouped_actions(actions, groups)


def _print_routing_evidence(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    summary = value.get("summary")
    if summary:
        print(f"Routing: {summary}")
    health = value.get("economy_health") if isinstance(value.get("economy_health"), dict) else {}
    if health:
        print(f"economy health: {health.get('status') or '-'} ({health.get('severity') or '-'})")
        if health.get("recommendation"):
            print(f"routing recommendation: {_short_text(health.get('recommendation'))}")
    actions = value.get("actions") if isinstance(value.get("actions"), list) else []
    if actions:
        _print_actions(actions, title="Routing actions")


def _print_efficiency(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    summary = value.get("summary")
    if summary:
        print(f"Efficiency: {summary}")
    recommendation = value.get("recommendation")
    if recommendation:
        print(f"efficiency recommendation: {_short_text(recommendation)}")


def _print_run_metrics_brief(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    total_duration = value.get("total_duration_ms")
    event_count = value.get("event_count")
    trace_count = value.get("trace_count")
    print(
        "Run metrics: "
        f"events={event_count if event_count is not None else '-'}, "
        f"trace={trace_count if trace_count is not None else '-'}, "
        f"duration={_duration_label(total_duration) if total_duration is not None else '-'}"
    )
    tiers = value.get("tier_usage") if isinstance(value.get("tier_usage"), dict) else {}
    if tiers:
        print("Tier usage:")
        for tier in ("economy", "supervision", "execution"):
            if tier in tiers:
                print(f"- {_tier_summary(tier, tiers[tier])}")
    providers = value.get("provider_usage") if isinstance(value.get("provider_usage"), list) else []
    if providers:
        print("Provider usage:")
        for item in providers[:5]:
            print(f"- {_provider_summary(item)}")


def _print_provider_trail(value: Any) -> None:
    if not isinstance(value, list) or not value:
        return
    print("Provider trail:")
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        phase = item.get("phase") or "-"
        provider = item.get("provider") or "-"
        model = item.get("model") or "-"
        status = item.get("status") or "-"
        print(f"- {phase}: {provider} / {model} | {status}")


def _print_artifacts_brief(value: Any) -> None:
    if not isinstance(value, list) or not value:
        return
    names: list[str] = []
    for item in value[:10]:
        if isinstance(item, dict):
            names.append(str(item.get("name") or item.get("path") or "-"))
        else:
            names.append(str(item))
    print(f"Artifacts: {', '.join(names)}")


def _print_agent_activity(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    headline = value.get("headline")
    if headline:
        print(f"Agent activity: {_short_text(headline)}")
    current = value.get("current_step") if isinstance(value.get("current_step"), dict) else {}
    if current:
        print(
            "Current step: "
            f"{current.get('phase') or '-'} | {current.get('status') or '-'} | "
            f"{_short_text(current.get('summary'), limit=140)}"
        )
    conversation = value.get("conversation_state") if isinstance(value.get("conversation_state"), dict) else {}
    if conversation.get("next_step"):
        print(f"Conversation next step: {_short_text(conversation.get('next_step'), limit=220)}")
    action = value.get("next_action") if isinstance(value.get("next_action"), dict) else {}
    if action:
        print(f"agent next_action: {_action_summary(action)}{_action_detail(action)}")
    health_cards = value.get("health_cards") if isinstance(value.get("health_cards"), list) else []
    if health_cards:
        print("Health cards:")
        for card in health_cards[:6]:
            if not isinstance(card, dict):
                continue
            print(
                f"- {card.get('label') or card.get('key') or '-'}: "
                f"{card.get('status') or '-'} | {_short_text(card.get('detail'), limit=180)}"
            )


def _cancel_result_details(value: Any) -> list[str]:
    if not isinstance(value, dict) or not value:
        return []
    details = []
    for key in ("attempted", "terminated", "already_exited", "reason", "error"):
        item = value.get(key)
        if item not in (None, ""):
            details.append(f"{key}={item}")
    return details


def _print_background_job(value: Any, *, include_actions: bool = True) -> None:
    if not isinstance(value, dict) or not value:
        return
    status = value.get("status") or ("running" if value.get("active") else "-")
    phase = value.get("phase") or value.get("action") or "-"
    active = bool(value.get("active"))
    print("Background job:")
    print(f"- status: {status} | phase: {phase} | active={active}")
    for key in ("kind", "pid", "exit_code"):
        item = value.get(key)
        if item not in (None, ""):
            print(f"- {key}: {item}")
    duration = value.get("duration_ms")
    if duration is not None:
        print(f"- duration: {_duration_label(duration)}")
    for key in ("error", "cancel_requested_at", "canceled_at"):
        item = value.get(key)
        if item:
            print(f"- {key}: {_short_text(item, limit=220)}")
    details = _cancel_result_details(value.get("cancel_result"))
    if details:
        print(f"- cancel_result: {', '.join(details)}")
    actions = value.get("actions") if isinstance(value.get("actions"), list) else []
    groups = value.get("action_groups") if isinstance(value.get("action_groups"), list) else []
    if include_actions and actions:
        _print_grouped_actions(actions, groups)


def _print_agent_background_cancel_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")
    print(f"Patchbay background cancel: {data.get('run_id') or '-'}")
    print(f"ok: {bool(data.get('ok'))}")
    print(f"canceled: {bool(data.get('canceled'))}")
    if data.get("error"):
        print(f"error: {_short_text(data.get('error'), limit=220)}")
    _print_background_job(data.get("background_job"), include_actions=True)
    details = _cancel_result_details(data.get("cancel_result"))
    if details:
        print(f"cancel_result: {', '.join(details)}")
    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    groups = data.get("action_groups") if isinstance(data.get("action_groups"), list) else []
    if actions:
        print("")
        _print_grouped_actions(actions, groups)


def _print_status_result(data: dict[str, Any]) -> None:
    print(f"Patchbay status: {data.get('run_id') or '-'}")
    task = data.get("task")
    if task:
        print(f"task: {_short_text(task)}")
    print(f"status: {data.get('status') or '-'} | phase: {data.get('current_phase') or data.get('stage') or '-'}")
    if data.get("error"):
        print(f"error: {_short_text(data.get('error'), limit=220)}")
    if data.get("suggested_next_action"):
        print(f"suggested_next_action: {_short_text(data.get('suggested_next_action'), limit=220)}")
    _print_gate_state(data.get("gate_state"))
    _print_background_job(data.get("background_job"), include_actions=True)
    _print_failure_recovery(data.get("failure_recovery"))
    _print_routing_evidence(data.get("routing_evidence"))
    _print_efficiency(data.get("efficiency_summary"))
    _print_run_metrics_brief(data.get("run_metrics"))
    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    if artifacts:
        _print_artifacts_brief(artifacts)


def _print_context_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")
    payload = data.get("context") if isinstance(data.get("context"), dict) else data
    print(f"Patchbay context: {payload.get('run_id') or data.get('run_id') or '-'}")
    summary = payload.get("handoff_summary")
    if summary:
        print(f"summary: {_short_text(summary, limit=260)}")
    print(f"status: {payload.get('status') or '-'} | phase: {payload.get('current_phase') or '-'}")
    _print_gate_state(payload.get("gate_state"))
    _print_background_job(payload.get("background_job"), include_actions=False)
    _print_agent_activity(payload.get("agent_activity"))
    _print_failure_recovery(payload.get("failure_recovery"))
    _print_routing_evidence(payload.get("routing_evidence"))
    _print_efficiency(payload.get("efficiency_summary"))
    _print_run_metrics_brief(payload.get("run_metrics"))
    _print_provider_trail(payload.get("provider_trail"))
    _print_artifacts_brief(payload.get("artifacts"))
    _print_next_actions(payload)
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    if not actions:
        actions = payload.get("next_actions") if isinstance(payload.get("next_actions"), list) else []
    groups = payload.get("action_groups") if isinstance(payload.get("action_groups"), list) else []
    if actions:
        print("")
        _print_grouped_actions(actions, groups)


def _event_summary(index: int, event: Any) -> str:
    if not isinstance(event, dict):
        return f"{index}: {event}"
    timestamp = event.get("timestamp") or "-"
    phase = event.get("phase") or "-"
    action = event.get("action") or "-"
    status = event.get("status") or "-"
    provider = event.get("provider") or "-"
    model = event.get("model") or "-"
    parts = [f"{index}: {timestamp}", f"{phase}.{action}", str(status)]
    if provider != "-" or model != "-":
        parts.append(f"{provider} / {model}")
    if event.get("duration_ms") is not None:
        parts.append(f"duration={_duration_label(event.get('duration_ms'))}")
    if event.get("next_action"):
        parts.append(f"next={event.get('next_action')}")
    detail = event.get("detail")
    if detail:
        parts.append(_short_text(detail, limit=140))
    return " | ".join(parts)


def _print_event_log_result(data: dict[str, Any], *, kind: str) -> None:
    title = "events" if kind == "events" else "trace"
    entries = data.get(kind) if isinstance(data.get(kind), list) else []
    print(f"Patchbay {title}: {data.get('run_id') or '-'}")
    print(f"since: {data.get('since', 0)} | returned: {data.get('returned', len(entries))} | total: {data.get('total', len(entries))}")
    if not entries:
        print(f"No {title} entries returned.")
        return
    print("Timeline:")
    try:
        start = int(data.get("since") or 0)
    except (TypeError, ValueError):
        start = 0
    for offset, event in enumerate(entries, start=start):
        print(f"- {_event_summary(offset, event)}")


def _print_artifact_result(data: dict[str, Any]) -> None:
    print(f"Patchbay artifact: {data.get('artifact') or '-'}")
    print(f"run_id: {data.get('run_id') or '-'}")
    path = data.get("path")
    if path:
        print(f"path: {path}")
    if data.get("lines_returned") is not None:
        print(f"lines_returned: {data.get('lines_returned')}")
    text = data.get("text")
    if isinstance(text, str):
        print("")
        print(text, end="" if text.endswith("\n") else "\n")


def _print_agent_artifacts(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    print("Artifacts:")
    for name, artifact in value.items():
        if isinstance(artifact, dict) and artifact.get("error"):
            print(f"- {name}: error ({artifact.get('error')})")
        elif isinstance(artifact, dict):
            text = artifact.get("text")
            detail = f"{len(str(text).splitlines())} lines" if isinstance(text, str) else "available"
            print(f"- {name}: {detail}")
        else:
            print(f"- {name}: {type(artifact).__name__}")


def _print_agent_view_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")
    action = str(data.get("action") or "view")
    print(f"Patchbay {action.replace('_', ' ')} view: {data.get('run_id') or '-'}")
    requested = data.get("requested_view") if isinstance(data.get("requested_view"), dict) else {}
    if requested:
        print(f"requested_view: {requested.get('tab') or '-'} | {_short_text(requested.get('reason'), limit=180)}")
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    if status:
        print(f"status: {status.get('status') or '-'} | phase: {status.get('current_phase') or status.get('stage') or '-'}")
        if status.get("suggested_next_action"):
            print(f"suggested_next_action: {_short_text(status.get('suggested_next_action'))}")
    events = data.get("events") if isinstance(data.get("events"), dict) else {}
    if events:
        _print_event_log_result(events, kind="events")
    trace = data.get("trace") if isinstance(data.get("trace"), dict) else {}
    if trace:
        _print_event_log_result(trace, kind="trace")
    _print_agent_artifacts(data.get("artifacts"))
    diff = data.get("diff")
    if isinstance(diff, str) and diff:
        print("Diff:")
        print(diff, end="" if diff.endswith("\n") else "\n")
    recovery = data.get("recovery") if isinstance(data.get("recovery"), dict) else {}
    _print_failure_recovery(recovery)
    _print_next_actions(data)
    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    groups = data.get("action_groups") if isinstance(data.get("action_groups"), list) else []
    if actions:
        print("")
        _print_grouped_actions(actions, groups)


def _run_title(run: dict[str, Any]) -> str:
    task = str(run.get("task") or "").strip()
    run_id = str(run.get("run_id") or "").strip()
    return task or run_id or "-"


def _print_run_detail(run: dict[str, Any]) -> None:
    inbox = run.get("inbox") if isinstance(run.get("inbox"), dict) else {}
    action = inbox.get("next_action") if isinstance(inbox.get("next_action"), dict) else {}
    print(f"run_id: {run.get('run_id')}")
    print(f"title: {_run_title(run)}")
    print(f"status: {run.get('status') or '-'}")
    print(f"phase: {run.get('current_phase') or '-'}")
    print(f"inbox: {inbox.get('label') or inbox.get('key') or '-'}")
    print(f"next_action: {_action_summary(action)}")
    commands = run.get("next_commands") if isinstance(run.get("next_commands"), list) else []
    if commands:
        print(f"next_commands: {', '.join(str(item) for item in commands)}")
    run_dir = run.get("run_dir")
    if run_dir:
        print(f"run_dir: {run_dir}")


def _print_runs_result(data: dict[str, Any], *, inbox_only: bool = False, focus_only: bool = False) -> None:
    inbox = data.get("inbox") if isinstance(data.get("inbox"), dict) else {}
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    summary = inbox.get("summary") or f"{len(runs)} runs."
    print(f"Agent inbox: {summary}")

    groups = inbox.get("groups") if isinstance(inbox.get("groups"), list) else []
    if groups:
        print("Groups:")
        for group in groups:
            if not isinstance(group, dict):
                continue
            run_ids = group.get("run_ids") if isinstance(group.get("run_ids"), list) else []
            suffix = f" [{', '.join(str(item) for item in run_ids[:3])}]" if run_ids else ""
            if len(run_ids) > 3:
                suffix += " ..."
            print(f"- {group.get('label') or group.get('key')}: {group.get('count', 0)}{suffix}")

    focus = inbox.get("focus") if isinstance(inbox.get("focus"), dict) else None
    if focus:
        focus_inbox = focus.get("inbox") if isinstance(focus.get("inbox"), dict) else {}
        focus_action = focus_inbox.get("next_action") if isinstance(focus_inbox.get("next_action"), dict) else {}
        print(
            "Focus: "
            f"{focus.get('run_id')} | {_run_title(focus)} | "
            f"{focus_inbox.get('label') or focus_inbox.get('key') or focus.get('status') or '-'} | "
            f"{_action_summary(focus_action)}"
        )

    if focus_only:
        if focus:
            print("")
            _print_run_detail(focus)
        return
    if inbox_only:
        return

    if not runs:
        print("No Patchbay runs yet.")
        return

    print("Runs:")
    for run in runs:
        if not isinstance(run, dict):
            continue
        inbox_state = run.get("inbox") if isinstance(run.get("inbox"), dict) else {}
        action = inbox_state.get("next_action") if isinstance(inbox_state.get("next_action"), dict) else {}
        print(
            "- "
            f"{run.get('run_id')} | {_run_title(run)} | {run.get('status') or '-'} | "
            f"{inbox_state.get('label') or inbox_state.get('key') or '-'} | "
            f"{_action_summary(action)}"
        )


def _print_agent_runs_result(data: dict[str, Any]) -> None:
    reply = str(data.get("reply") or "").strip()
    if reply:
        print(reply)
        print("")

    runs = data.get("runs") if isinstance(data.get("runs"), dict) else {}
    _print_runs_result(runs)

    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    if actions:
        print("")
        _print_actions(actions)


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")


def _add_setup_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default="", help="Repository root to set up.")
    parser.add_argument(
        "--host",
        default="codex",
        help="MCP host or alias: codex, claude, claude-code, claude-desktop, gemini (for example Claude Desktop or Gemini CLI).",
    )
    parser.add_argument("--skill-path", default="", help="Destination skills root; defaults to $CODEX_HOME/skills or ~/.codex/skills.")
    parser.add_argument("--dry-run", action="store_true", help="Preview setup without writing files.")
    parser.add_argument("--skip-skill", action="store_true", help="Skip Codex Skill installation.")
    parser.add_argument(
        "--skip-mcp",
        "--no-mcp",
        "--local-only",
        dest="skip_mcp",
        action="store_true",
        help="Skip MCP host registration helper and suppress MCP follow-up actions.",
    )
    parser.add_argument("--mcp-dry-run", action="store_true", help="Preview MCP registration without writing host config.")
    parser.add_argument("--probe-mcp", action="store_true", help="Run stdio MCP doctor after setup.")
    parser.add_argument("--no-config", action="store_true", help="Do not create .ai/patchbay.toml from the example.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchbay",
        description="MCP-friendly patch orchestration across interchangeable coding agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create config, ignored artifact dirs, and docs skeleton.")
    _add_json(init)

    web = sub.add_parser("web", help="Start the local Patchbay web workbench.")
    web.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    web.add_argument("--port", type=int, default=0, help="Port to bind; 0 selects a free port.")
    _add_json(web)

    doctor = sub.add_parser("doctor", help="Run unified CLI/config/Skill readiness checks without stdio MCP probing by default.")
    doctor.add_argument("--root", default="", help="Repository root to inspect.")
    doctor.add_argument("--host", default="codex", help="MCP host for structured registration actions.")
    doctor.add_argument(
        "--skip-mcp",
        "--no-mcp",
        "--local-only",
        dest="skip_mcp",
        action="store_true",
        help="Do not probe MCP and suppress MCP registration/probe follow-up actions.",
    )
    doctor.add_argument("--probe-mcp", action="store_true", help="Run stdio MCP server probing and verify registered tools.")
    doctor.add_argument("--skill-path", default="", help="Codex skills root to inspect.")
    _add_json(doctor)

    setup = sub.add_parser("setup", help="Initialize Patchbay, install the Skill, and print/register MCP host setup.")
    _add_setup_args(setup)
    _add_json(setup)

    install = sub.add_parser("install", help="Alias for setup.")
    _add_setup_args(install)
    _add_json(install)

    agent = sub.add_parser("agent", help="Conversational Patchbay Agent entry point.")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_message_parser = agent_sub.add_parser("message", help="Send a natural-language message to Patchbay Agent.")
    agent_message_parser.add_argument("message", nargs="?", default="", help="Task or instruction.")
    agent_message_parser.add_argument("--run-id", default="", help="Existing run id to continue.")
    agent_message_parser.add_argument(
        "--confirmation",
        default="none",
        choices=["none", "plan_approved", "apply_approved"],
        help="Explicit confirmation token for plan/apply gates.",
    )
    agent_message_parser.add_argument("--max-fix-rounds", type=int, default=None, help="Optional cap for this agent turn.")
    agent_message_parser.add_argument("--include-plan", action="store_true", help="Include PLAN.md in the response.")
    agent_message_parser.add_argument("--include-review", action="store_true", help="Include REVIEW.md in the response.")
    agent_message_parser.add_argument("--include-diff", action="store_true", help="Include FINAL.diff in the response.")
    agent_message_parser.add_argument("--background", action="store_true", help="Run this agent turn in the background when it can safely advance phases.")
    _add_json(agent_message_parser)

    plan = sub.add_parser("plan", help="Run read-only Claude planner.")
    plan.add_argument("--task", required=True, help="Task to plan.")
    plan.add_argument("--mock", action="store_true", help="Use mock planner.")
    plan.add_argument("--background", action="store_true", help="Run this phase in the background.")
    plan.add_argument("--run-id", default="", help="Reuse a specific run id.")
    _add_json(plan)

    approve = sub.add_parser("approve", help="Approve a planned run.")
    approve.add_argument("run_id")
    _add_json(approve)

    write = sub.add_parser("write", help="Create worktree and run writer.")
    write.add_argument("run_id")
    write.add_argument("--mock", action="store_true", help="Use mock writer.")
    write.add_argument("--background", action="store_true", help="Run this phase in the background.")
    _add_json(write)

    test = sub.add_parser("test", help="Run selected allowlisted test commands in worktree.")
    test.add_argument("run_id")
    test.add_argument("--background", action="store_true", help="Run this phase in the background.")
    _add_json(test)

    review = sub.add_parser("review", help="Run read-only Codex reviewer.")
    review.add_argument("run_id")
    review.add_argument("--mock", action="store_true", help="Use mock reviewer.")
    review.add_argument("--background", action="store_true", help="Run this phase in the background.")
    _add_json(review)

    fix = sub.add_parser("fix", help="Run bounded fix loop for review/test failures.")
    fix.add_argument("run_id")
    fix.add_argument("--mock", action="store_true", help="Use mock repair writer.")
    fix.add_argument("--background", action="store_true", help="Run this phase in the background.")
    _add_json(fix)

    cancel = sub.add_parser("cancel", help="Cancel an active background job for a run.")
    cancel.add_argument("run_id")
    _add_json(cancel)

    status = sub.add_parser("status", help="Show run status.")
    status.add_argument("run_id")
    status.add_argument("--watch", action="store_true", help="Poll status until terminal.")
    _add_json(status)

    context = sub.add_parser("context", help="Show unified run handoff context.")
    context.add_argument("run_id")
    context.add_argument("--since-event", type=int, default=0, help="Return events after raw event index N.")
    context.add_argument("--since-trace", type=int, default=0, help="Return trace entries after raw trace index N.")
    context.add_argument("--include-trace", action="store_true", help="Merge trace entries into the context timeline.")
    _add_json(context)

    metrics = sub.add_parser("metrics", help="Show run efficiency metrics.")
    metrics.add_argument("run_id")
    _add_json(metrics)

    events = sub.add_parser("events", help="Show run event log (JSONL stream).")
    events.add_argument("run_id")
    events.add_argument("--since", type=int, default=0, help="Return events after index N.")
    events.add_argument("--phase", type=str, default=None, help="Filter by phase.")
    events.add_argument("--follow", action="store_true", help="Poll until new events stop arriving.")
    _add_json(events)

    trace = sub.add_parser("trace", help="Show run structured trace log (JSONL stream).")
    trace.add_argument("run_id")
    trace.add_argument("--since", type=int, default=0, help="Return trace entries after raw line index N.")
    trace.add_argument("--phase", type=str, default=None, help="Filter by phase.")
    trace.add_argument("--follow", action="store_true", help="Poll until new trace entries stop arriving.")
    _add_json(trace)

    runs = sub.add_parser("runs", help="List recent Patchbay runs.")
    runs.add_argument("--limit", type=int, default=20)
    runs.add_argument("--inbox", action="store_true", help="Show only the Agent inbox summary, groups, and focus.")
    runs.add_argument("--focus", action="store_true", help="Show the highest-priority run details and next action.")
    _add_json(runs)

    artifact = sub.add_parser("artifact", help="Read a run artifact file.")
    artifact.add_argument("run_id")
    artifact.add_argument("artifact")
    artifact.add_argument("--tail", type=int, default=None)
    _add_json(artifact)

    config = sub.add_parser("config", help="Interactive config wizard (no args), set key=value, or doctor.")
    config.add_argument("--set-key", type=str, default="", metavar="KEY", help="Set a config key (dotted form).")
    config.add_argument("--set-value", type=str, default="", metavar="VALUE", help="Value for --set-key.")
    config.add_argument("--doctor", action="store_true", help="Validate resolved phase configuration.")
    config_sub = config.add_subparsers(dest="config_command")

    config_show = config_sub.add_parser("show", help="Show resolved config.")
    _add_json(config_show)

    config_phase = config_sub.add_parser("phase", help="Update phase configuration.")
    phase_sub = config_phase.add_subparsers(dest="phase_command", required=True)
    phase_set = phase_sub.add_parser("set", help="Set a phase provider/model/command key.")
    phase_set.add_argument("phase")
    phase_set.add_argument("--provider", required=True)
    phase_set.add_argument("--model", default="")
    phase_set.add_argument("--command-key", default="")
    _add_json(phase_set)

    config_command = config_sub.add_parser("command", help="Update command aliases.")
    command_sub = config_command.add_subparsers(dest="command_command", required=True)
    command_set = command_sub.add_parser("set", help="Set a command alias.")
    command_set.add_argument("key")
    command_set.add_argument("value")
    _add_json(command_set)

    config_test = config_sub.add_parser("test", help="Update test allowlist.")
    test_sub = config_test.add_subparsers(dest="test_command_name", required=True)
    test_add = test_sub.add_parser("add", help="Add an allowlisted test command.")
    test_add.add_argument("test_command")
    _add_json(test_add)

    config_provider = config_sub.add_parser("provider", help="Update custom providers.")
    provider_sub = config_provider.add_subparsers(dest="provider_command_name", required=True)
    provider_add = provider_sub.add_parser("add-cli", help="Add a custom CLI provider.")
    provider_add.add_argument("provider_id")
    provider_add.add_argument("--roles", nargs="+", required=True)
    provider_add.add_argument("--command", dest="provider_command", required=True)
    provider_add.add_argument("--args", nargs="*", default=[])
    provider_add.add_argument("--prompt-mode", choices=["stdin", "arg", "file"], default="stdin")
    provider_add.add_argument("--output-contract", choices=["plan_json", "review_verdict", "worktree_diff", "writer_diff"], required=True)
    provider_add.add_argument(
        "--activate-economy",
        "--as-economy",
        dest="activate_economy",
        action="store_true",
        help="Also make this provider the economy write/fix route.",
    )
    provider_add.add_argument("--economy-model", default="", help="Model label to record for the economy write/fix route.")
    provider_add.add_argument("--economy-label", default="", help="Human-readable label for this low-cost economy route.")
    _add_json(provider_add)

    config_profile = config_sub.add_parser("profile", help="Apply or inspect recommended phase routing profiles.")
    profile_sub = config_profile.add_subparsers(dest="profile_command", required=True)
    profile_apply = profile_sub.add_parser("apply", help="Apply a routing profile.")
    profile_apply.add_argument("profile", choices=["economy"])
    _add_json(profile_apply)
    profile_show = profile_sub.add_parser("show", help="Show current routing profile status.")
    _add_json(profile_show)
    _add_json(config)

    mcp = sub.add_parser("mcp", help="MCP host registration helpers.")
    mcp_sub = mcp.add_subparsers(dest="mcp_command")

    mcp_install = mcp_sub.add_parser("install", help="Register Patchbay MCP server for a host.")
    mcp_install.add_argument(
        "host",
        help="Host name or alias: codex, claude, claude-code, claude-desktop, gemini (for example Claude Desktop or Gemini CLI).",
    )
    mcp_install.add_argument("--root", default="", help="Repository root to register.")
    mcp_install.add_argument("--dry-run", action="store_true", help="Print the command without running it.")
    _add_json(mcp_install)

    mcp_doctor = mcp_sub.add_parser("doctor", help="Validate MCP server reachability.")
    mcp_doctor.add_argument("--root", default="", help="Repository root to inspect.")
    _add_json(mcp_doctor)

    skill = sub.add_parser("skill", help="Install, inspect, or validate the Patchbay Codex Skill bundle.")
    skill_sub = skill.add_subparsers(dest="skill_command")
    skill_install = skill_sub.add_parser("install", help="Install Patchbay as a Codex Skill.")
    skill_install.add_argument("host", nargs="?", default="codex", help=SKILL_HOST_HELP)
    skill_install.add_argument("--path", default="", help="Destination skills root; defaults to $CODEX_HOME/skills or ~/.codex/skills.")
    skill_install.add_argument("--dry-run", action="store_true", help="Show destination without copying files.")
    _add_json(skill_install)
    skill_print = skill_sub.add_parser("print", help="Print the Patchbay Skill files for inspection.")
    skill_print.add_argument("host", nargs="?", default="codex", help=SKILL_HOST_HELP)
    _add_json(skill_print)
    skill_doctor = skill_sub.add_parser("doctor", help="Validate bundled and installed Patchbay Skill state.")
    skill_doctor.add_argument("host", nargs="?", default="codex", help=SKILL_HOST_HELP)
    skill_doctor.add_argument("--path", default="", help="Destination skills root; defaults to $CODEX_HOME/skills or ~/.codex/skills.")
    _add_json(skill_doctor)

    diff = sub.add_parser("diff", help="Print run final diff.")
    diff.add_argument("run_id")

    apply = sub.add_parser("apply", help="Apply reviewed diff to current workspace.")
    apply.add_argument("run_id")
    apply.add_argument(
        "--confirmation",
        default="none",
        choices=["none", APPLY_CONFIRMATION],
        help="Explicit final-apply confirmation token. Required value: apply_approved.",
    )
    _add_json(apply)

    cleanup = sub.add_parser("cleanup", help="Remove the run worktree.")
    cleanup.add_argument("run_id")
    _add_json(cleanup)

    return parser


def _run_stream_follow(cwd: Path, args: argparse.Namespace, *, kind: str) -> dict[str, Any]:
    initial_since = int(getattr(args, "since", 0) or 0)
    seen = initial_since
    last: dict[str, Any] | None = None
    collected: list[dict[str, Any]] = []
    idle_rounds = 0
    service_func = service.events if kind == "events" else service.trace
    while True:
        last = service_func(cwd, args.run_id, since=seen, phase=getattr(args, "phase", None))
        entries = last.get(kind, [])
        if entries:
            collected.extend(entries)
            idle_rounds = 0
        else:
            idle_rounds += 1
            if idle_rounds >= 5:
                break
        seen = int(last.get("total") or seen)
        if not getattr(args, "follow", False):
            break
        if entries and not bool(getattr(args, "json", False)):
            for entry in entries:
                print(json.dumps(entry, ensure_ascii=False, sort_keys=True))
        time.sleep(0.4)
    total = int((last or {}).get("total") or seen)
    return {
        "run_id": args.run_id,
        "since": initial_since,
        "total": total,
        "returned": len(collected),
        kind: collected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = Path.cwd()
    try:
        if args.command in {"events", "trace"} and getattr(args, "follow", False):
            result = _run_stream_follow(cwd, args, kind=args.command)
        else:
            result = dispatch(args, cwd)
    except AiFlowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if exc.stage:
            print(f"stage: {exc.stage}", file=sys.stderr)
        if exc.suggested_next_action:
            print(f"suggested_next_action: {exc.suggested_next_action}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    as_json = bool(getattr(args, "json", False))
    if args.command == "diff":
        print(result, end="" if str(result).endswith("\n") else "\n")
    elif args.command in {"events", "trace"} and getattr(args, "follow", False):
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command in {"events", "trace"} and not as_json and isinstance(result, dict):
        _print_event_log_result(result, kind=args.command)
    elif args.command == "runs" and not as_json and isinstance(result, dict):
        _print_runs_result(
            result,
            inbox_only=bool(getattr(args, "inbox", False)),
            focus_only=bool(getattr(args, "focus", False)),
        )
    elif args.command == "doctor" and not as_json and isinstance(result, dict):
        _print_readiness_result(result)
    elif args.command in {"setup", "install"} and not as_json and isinstance(result, dict):
        _print_setup_result(result)
    elif args.command == "status" and not as_json and isinstance(result, dict):
        _print_status_result(result)
    elif args.command == "context" and not as_json and isinstance(result, dict):
        _print_context_result(result)
    elif args.command == "metrics" and not as_json and isinstance(result, dict):
        _print_metrics_result(result)
    elif args.command == "artifact" and not as_json and isinstance(result, dict):
        _print_artifact_result(result)
    elif (
        args.command == "config"
        and getattr(args, "config_command", "") == "profile"
        and not as_json
        and isinstance(result, dict)
    ):
        _print_profile_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "runs"
        and isinstance(result.get("runs"), dict)
    ):
        _print_agent_runs_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "doctor"
        and isinstance(result.get("doctor"), dict)
    ):
        _print_readiness_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "setup"
        and isinstance(result.get("setup"), dict)
    ):
        _print_setup_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") in {"profile_show", "profile_apply"}
    ):
        _print_profile_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "metrics"
        and isinstance(result.get("metrics"), dict)
    ):
        _print_metrics_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "background_cancel"
    ):
        _print_agent_background_cancel_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "background_status"
    ):
        _print_agent_guidance_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") in {"help", "local_mode", "next_step", "gate_status", "missing_run"}
    ):
        _print_agent_guidance_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "context"
        and isinstance(result.get("context"), dict)
    ):
        _print_context_result(result)
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and result.get("action") == "status"
        and isinstance(result.get("status"), dict)
    ):
        reply = str(result.get("reply") or "").strip()
        if reply:
            print(reply)
            print("")
        _print_status_result(result["status"])
    elif (
        args.command == "agent"
        and getattr(args, "agent_command", "") == "message"
        and not as_json
        and isinstance(result, dict)
        and (
            result.get("action") in {"events", "artifact", "diff"}
            or isinstance(result.get("requested_view"), dict)
        )
    ):
        _print_agent_view_result(result)
    else:
        _print_result(result, as_json=as_json)
    return 0


def dispatch(args: argparse.Namespace, cwd: Path) -> Any:
    command = args.command.replace("-", "_")
    handlers: dict[str, Callable[[argparse.Namespace, Path], Any]] = {
        "init": lambda a, c: service.init_project(c),
        "web": lambda a, c: serve_web(c, host=a.host, port=a.port, json_output=bool(getattr(a, "json", False))),
        "doctor": lambda a, c: run_doctor(
            c,
            root=getattr(a, "root", "") or None,
            include_mcp=bool(getattr(a, "probe_mcp", False)) and not bool(getattr(a, "skip_mcp", False)),
            suppress_mcp_actions=bool(getattr(a, "skip_mcp", False)),
            skill_path=getattr(a, "skill_path", "") or None,
            host=getattr(a, "host", "codex"),
        ),
        "setup": lambda a, c: run_setup(
            c,
            root=getattr(a, "root", "") or None,
            host=getattr(a, "host", "codex"),
            skill_path=getattr(a, "skill_path", "") or None,
            dry_run=bool(getattr(a, "dry_run", False)),
            skip_skill=bool(getattr(a, "skip_skill", False)),
            skip_mcp=bool(getattr(a, "skip_mcp", False)),
            mcp_dry_run=bool(getattr(a, "mcp_dry_run", False)),
            probe_mcp=bool(getattr(a, "probe_mcp", False)),
            create_config=not bool(getattr(a, "no_config", False)),
        ),
        "install": lambda a, c: run_setup(
            c,
            root=getattr(a, "root", "") or None,
            host=getattr(a, "host", "codex"),
            skill_path=getattr(a, "skill_path", "") or None,
            dry_run=bool(getattr(a, "dry_run", False)),
            skip_skill=bool(getattr(a, "skip_skill", False)),
            skip_mcp=bool(getattr(a, "skip_mcp", False)),
            mcp_dry_run=bool(getattr(a, "mcp_dry_run", False)),
            probe_mcp=bool(getattr(a, "probe_mcp", False)),
            create_config=not bool(getattr(a, "no_config", False)),
        ),
        "agent": lambda a, c: agent_message(
            c,
            a.message,
            run_id=a.run_id or None,
            confirmation=a.confirmation,
            max_fix_rounds=a.max_fix_rounds,
            include={
                "plan": bool(getattr(a, "include_plan", False)),
                "review": bool(getattr(a, "include_review", False)),
                "diff": bool(getattr(a, "include_diff", False)),
            },
            background=bool(getattr(a, "background", False)),
        ),
        "plan": lambda a, c: service.start_background_phase(c, "plan", task=a.task, mock=a.mock, run_id=a.run_id or None) if a.background else service.plan_with_context(c, task=a.task, mock=a.mock, run_id=a.run_id or None),
        "approve": lambda a, c: service.approve(c, a.run_id),
        "write": lambda a, c: service.start_background_phase(c, "write", run_id=a.run_id, mock=a.mock) if a.background else service.write(c, a.run_id, mock=a.mock),
        "test": lambda a, c: service.start_background_phase(c, "test", run_id=a.run_id) if a.background else service.test(c, a.run_id),
        "review": lambda a, c: service.start_background_phase(c, "review", run_id=a.run_id, mock=a.mock) if a.background else service.review(c, a.run_id, mock=a.mock),
        "fix": lambda a, c: service.start_background_phase(c, "fix", run_id=a.run_id, mock=a.mock) if a.background else service.fix(c, a.run_id, mock=a.mock),
        "cancel": lambda a, c: service.cancel_background_job(c, a.run_id),
        "status": lambda a, c: service.status(c, a.run_id),
        "context": lambda a, c: service.context(
            c,
            a.run_id,
            since_event=getattr(a, "since_event", 0),
            since_trace=getattr(a, "since_trace", 0),
            include_trace=bool(getattr(a, "include_trace", False)),
        ),
        "metrics": lambda a, c: service.metrics(c, a.run_id),
        "events": lambda a, c: service.events(c, a.run_id, since=getattr(a, "since", 0), phase=getattr(a, "phase", None)),
        "trace": lambda a, c: service.trace(c, a.run_id, since=getattr(a, "since", 0), phase=getattr(a, "phase", None)),
        "runs": lambda a, c: service.runs(c, limit=a.limit),
        "artifact": lambda a, c: service.artifact(c, a.run_id, a.artifact, tail=a.tail),
        "config": lambda a, c: config_wizard_run(c, a),
        "mcp": lambda a, c: mcp_dispatch(c, a),
        "skill": lambda a, c: skill_dispatch(c, a),
        "diff": lambda a, c: service.diff(c, a.run_id),
        "apply": lambda a, c: apply_dispatch(c, a),
        "cleanup": lambda a, c: service.cleanup(c, a.run_id),
    }
    return handlers[command](args, cwd)


def apply_dispatch(cwd: Path, args: argparse.Namespace) -> Any:
    if getattr(args, "confirmation", "none") != APPLY_CONFIRMATION:
        raise StateError(
            "Applying changes requires explicit approval after reviewing the final diff.",
            stage="apply",
            suggested_next_action=f"Re-run with `--confirmation {APPLY_CONFIRMATION}` after reviewing FINAL.diff.",
        )
    return service.apply(cwd, args.run_id)
