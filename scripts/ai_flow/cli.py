from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from . import service
from .errors import AiFlowError


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
    _add_json(plan)

    approve = sub.add_parser("approve", help="Approve a planned run.")
    approve.add_argument("run_id")
    _add_json(approve)

    write = sub.add_parser("write", help="Create worktree and run writer.")
    write.add_argument("run_id")
    write.add_argument("--mock", action="store_true", help="Use mock writer.")
    _add_json(write)

    test = sub.add_parser("test", help="Run selected allowlisted test commands in worktree.")
    test.add_argument("run_id")
    _add_json(test)

    review = sub.add_parser("review", help="Run read-only Codex reviewer.")
    review.add_argument("run_id")
    review.add_argument("--mock", action="store_true", help="Use mock reviewer.")
    _add_json(review)

    fix = sub.add_parser("fix", help="Run bounded fix loop for review/test failures.")
    fix.add_argument("run_id")
    fix.add_argument("--mock", action="store_true", help="Use mock repair writer.")
    _add_json(fix)

    status = sub.add_parser("status", help="Show run status.")
    status.add_argument("run_id")
    _add_json(status)

    diff = sub.add_parser("diff", help="Print run final diff.")
    diff.add_argument("run_id")

    apply = sub.add_parser("apply", help="Apply reviewed diff to current workspace.")
    apply.add_argument("run_id")
    _add_json(apply)

    cleanup = sub.add_parser("cleanup", help="Remove the run worktree.")
    cleanup.add_argument("run_id")
    _add_json(cleanup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = Path.cwd()
    try:
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
    else:
        _print_result(result, as_json=as_json)
    return 0


def dispatch(args: argparse.Namespace, cwd: Path) -> Any:
    command = args.command.replace("-", "_")
    handlers: dict[str, Callable[[argparse.Namespace, Path], Any]] = {
        "init": lambda a, c: service.init_project(c),
        "plan": lambda a, c: service.plan(c, task=a.task, mock=a.mock),
        "approve": lambda a, c: service.approve(c, a.run_id),
        "write": lambda a, c: service.write(c, a.run_id, mock=a.mock),
        "test": lambda a, c: service.test(c, a.run_id),
        "review": lambda a, c: service.review(c, a.run_id, mock=a.mock),
        "fix": lambda a, c: service.fix(c, a.run_id, mock=a.mock),
        "status": lambda a, c: service.status(c, a.run_id),
        "diff": lambda a, c: service.diff(c, a.run_id),
        "apply": lambda a, c: service.apply(c, a.run_id),
        "cleanup": lambda a, c: service.cleanup(c, a.run_id),
    }
    return handlers[command](args, cwd)
