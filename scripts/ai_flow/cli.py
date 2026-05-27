from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import service
from .config_wizard import run_config_wizard
from .errors import AiFlowError
from .mcp_install import run_mcp_install, run_mcp_doctor


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
            provider_command=args.command,
            provider_args=args.args,
            prompt_mode=args.prompt_mode,
            output_contract=args.output_contract,
        )
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


def agent_dispatch(cwd: Path, args: argparse.Namespace) -> Any:
    agent_cmd = getattr(args, "agent_command", "")
    if agent_cmd == "serve":
        from .agent_server import run_agent_server

        return run_agent_server(
            cwd,
            host=args.host,
            port=args.port,
            open_browser=bool(getattr(args, "open_browser", False)),
        )
    raise AiFlowError("Missing agent subcommand. Try: patchbay agent serve", stage="agent")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchbay",
        description="MCP-friendly patch orchestration across interchangeable coding agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create config, ignored artifact dirs, and docs skeleton.")
    _add_json(init)

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

    events = sub.add_parser("events", help="Show run event log (JSONL stream).")
    events.add_argument("run_id")
    events.add_argument("--since", type=int, default=0, help="Return events after index N.")
    events.add_argument("--phase", type=str, default=None, help="Filter by phase.")
    events.add_argument("--follow", action="store_true", help="Poll until new events stop arriving.")
    _add_json(events)

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
    provider_add.add_argument("--command", required=True)
    provider_add.add_argument("--args", nargs="*", default=[])
    provider_add.add_argument("--prompt-mode", choices=["stdin", "arg", "file"], default="stdin")
    provider_add.add_argument("--output-contract", choices=["plan_json", "review_verdict", "worktree_diff", "writer_diff"], required=True)
    _add_json(provider_add)
    _add_json(config)

    mcp = sub.add_parser("mcp", help="MCP host registration helpers.")
    mcp_sub = mcp.add_subparsers(dest="mcp_command")

    mcp_install = mcp_sub.add_parser("install", help="Register Patchbay MCP server for a host.")
    mcp_install.add_argument("host", help="Host name: codex, claude, claude-desktop, gemini.")
    mcp_install.add_argument("--root", default="", help="Repository root to register.")
    mcp_install.add_argument("--dry-run", action="store_true", help="Print the command without running it.")
    _add_json(mcp_install)

    mcp_doctor = mcp_sub.add_parser("doctor", help="Validate MCP server reachability.")
    mcp_doctor.add_argument("--root", default="", help="Repository root to inspect.")
    _add_json(mcp_doctor)

    agent = sub.add_parser("agent", help="Run the local conversational Patchbay Agent UI.")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)

    agent_serve = agent_sub.add_parser("serve", help="Serve the local Patchbay Agent web UI.")
    agent_serve.add_argument("--host", default="127.0.0.1", help="Host address to bind.")
    agent_serve.add_argument("--port", type=int, default=8765, help="Port to bind.")
    agent_serve.add_argument("--open", action="store_true", dest="open_browser", help="Open the UI in the default browser.")

    diff = sub.add_parser("diff", help="Print run final diff.")
    diff.add_argument("run_id")

    apply = sub.add_parser("apply", help="Apply reviewed diff to current workspace.")
    apply.add_argument("run_id")
    _add_json(apply)

    cleanup = sub.add_parser("cleanup", help="Remove the run worktree.")
    cleanup.add_argument("run_id")
    _add_json(cleanup)

    return parser


def _run_events_follow(cwd: Path, args: argparse.Namespace) -> dict[str, Any]:
    initial_since = int(getattr(args, "since", 0) or 0)
    seen = initial_since
    last: dict[str, Any] | None = None
    collected: list[dict[str, Any]] = []
    idle_rounds = 0
    while True:
        last = service.events(cwd, args.run_id, since=seen, phase=getattr(args, "phase", None))
        events = last.get("events", [])
        if events:
            collected.extend(events)
            idle_rounds = 0
        else:
            idle_rounds += 1
            if idle_rounds >= 5:
                break
        seen = int(last.get("total") or seen)
        if not getattr(args, "follow", False):
            break
        if events and not bool(getattr(args, "json", False)):
            for event in events:
                print(json.dumps(event, ensure_ascii=False, sort_keys=True))
        time.sleep(0.4)
    total = int((last or {}).get("total") or seen)
    return {
        "run_id": args.run_id,
        "since": initial_since,
        "total": total,
        "returned": len(collected),
        "events": collected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = Path.cwd()
    try:
        if args.command == "events" and getattr(args, "follow", False):
            result = _run_events_follow(cwd, args)
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
    elif args.command == "events" and getattr(args, "follow", False):
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_result(result, as_json=as_json)
    return 0


def dispatch(args: argparse.Namespace, cwd: Path) -> Any:
    command = args.command.replace("-", "_")
    handlers: dict[str, Callable[[argparse.Namespace, Path], Any]] = {
        "init": lambda a, c: service.init_project(c),
        "plan": lambda a, c: service.start_background_phase(c, "plan", task=a.task, mock=a.mock, run_id=a.run_id or None) if a.background else service.plan(c, task=a.task, mock=a.mock, run_id=a.run_id or None),
        "approve": lambda a, c: service.approve(c, a.run_id),
        "write": lambda a, c: service.start_background_phase(c, "write", run_id=a.run_id, mock=a.mock) if a.background else service.write(c, a.run_id, mock=a.mock),
        "test": lambda a, c: service.start_background_phase(c, "test", run_id=a.run_id) if a.background else service.test(c, a.run_id),
        "review": lambda a, c: service.start_background_phase(c, "review", run_id=a.run_id, mock=a.mock) if a.background else service.review(c, a.run_id, mock=a.mock),
        "fix": lambda a, c: service.start_background_phase(c, "fix", run_id=a.run_id, mock=a.mock) if a.background else service.fix(c, a.run_id, mock=a.mock),
        "status": lambda a, c: service.status(c, a.run_id),
        "events": lambda a, c: service.events(c, a.run_id, since=getattr(a, "since", 0), phase=getattr(a, "phase", None)),
        "runs": lambda a, c: service.runs(c, limit=a.limit),
        "artifact": lambda a, c: service.artifact(c, a.run_id, a.artifact, tail=a.tail),
        "config": lambda a, c: config_wizard_run(c, a),
        "mcp": lambda a, c: mcp_dispatch(c, a),
        "agent": lambda a, c: agent_dispatch(c, a),
        "diff": lambda a, c: service.diff(c, a.run_id),
        "apply": lambda a, c: service.apply(c, a.run_id),
        "cleanup": lambda a, c: service.cleanup(c, a.run_id),
    }
    return handlers[command](args, cwd)
