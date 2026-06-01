from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import service
from .agent import agent_message
from .config_wizard import run_config_wizard
from .doctor import run_doctor
from .errors import AiFlowError
from .mcp_install import run_mcp_install, run_mcp_doctor
from .setup_flow import run_setup
from .skill_install import run_skill_doctor, run_skill_install, run_skill_print
from .web_server import serve as serve_web


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
    skill_install.add_argument("host", nargs="?", default="codex", help="Skill host: codex.")
    skill_install.add_argument("--path", default="", help="Destination skills root; defaults to $CODEX_HOME/skills or ~/.codex/skills.")
    skill_install.add_argument("--dry-run", action="store_true", help="Show destination without copying files.")
    _add_json(skill_install)
    skill_print = skill_sub.add_parser("print", help="Print the Patchbay Skill files for inspection.")
    skill_print.add_argument("host", nargs="?", default="codex", help="Skill host: codex.")
    _add_json(skill_print)
    skill_doctor = skill_sub.add_parser("doctor", help="Validate bundled and installed Patchbay Skill state.")
    skill_doctor.add_argument("host", nargs="?", default="codex", help="Skill host: codex.")
    skill_doctor.add_argument("--path", default="", help="Destination skills root; defaults to $CODEX_HOME/skills or ~/.codex/skills.")
    _add_json(skill_doctor)

    diff = sub.add_parser("diff", help="Print run final diff.")
    diff.add_argument("run_id")

    apply = sub.add_parser("apply", help="Apply reviewed diff to current workspace.")
    apply.add_argument("run_id")
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
        "plan": lambda a, c: service.start_background_phase(c, "plan", task=a.task, mock=a.mock, run_id=a.run_id or None) if a.background else service.plan(c, task=a.task, mock=a.mock, run_id=a.run_id or None),
        "approve": lambda a, c: service.approve(c, a.run_id),
        "write": lambda a, c: service.start_background_phase(c, "write", run_id=a.run_id, mock=a.mock) if a.background else service.write(c, a.run_id, mock=a.mock),
        "test": lambda a, c: service.start_background_phase(c, "test", run_id=a.run_id) if a.background else service.test(c, a.run_id),
        "review": lambda a, c: service.start_background_phase(c, "review", run_id=a.run_id, mock=a.mock) if a.background else service.review(c, a.run_id, mock=a.mock),
        "fix": lambda a, c: service.start_background_phase(c, "fix", run_id=a.run_id, mock=a.mock) if a.background else service.fix(c, a.run_id, mock=a.mock),
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
        "apply": lambda a, c: service.apply(c, a.run_id),
        "cleanup": lambda a, c: service.cleanup(c, a.run_id),
    }
    return handlers[command](args, cwd)
