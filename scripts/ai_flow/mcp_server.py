from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ai_flow import service
    from ai_flow.config_wizard import run_config_wizard
else:
    from . import service
    from .config_wizard import run_config_wizard


ROOT = Path(os.environ.get("PATCHBAY_ROOT") or Path.cwd())
SERVER_NAME = "patchbay"
SERVER_VERSION = "0.1.0"


def patchbay_plan(task: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "plan", task=task)
    return service.plan(ROOT, task=task)


def patchbay_approve(run_id: str) -> dict[str, Any]:
    return service.approve(ROOT, run_id)


def patchbay_write(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "write", run_id=run_id)
    return service.write(ROOT, run_id)


def patchbay_test(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "test", run_id=run_id)
    return service.test(ROOT, run_id)


def patchbay_review(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "review", run_id=run_id)
    return service.review(ROOT, run_id)


def patchbay_fix(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "fix", run_id=run_id)
    return service.fix(ROOT, run_id)


def patchbay_status(run_id: str) -> dict[str, Any]:
    return service.status(ROOT, run_id)


def patchbay_events(run_id: str, since: int = 0, phase: str = "") -> dict[str, Any]:
    return service.events(ROOT, run_id, since=since, phase=phase or None)


def patchbay_runs(limit: int = 20) -> dict[str, Any]:
    return service.runs(ROOT, limit=limit)


def patchbay_artifact(run_id: str, artifact: str, tail: int | None = None) -> dict[str, Any]:
    return service.artifact(ROOT, run_id, artifact, tail=tail)


def patchbay_config_show() -> dict[str, Any]:
    return run_config_wizard(ROOT, show=True)


def patchbay_config_phase_set(
    phase: str,
    provider: str,
    model: str = "",
    command_key: str = "",
) -> dict[str, Any]:
    return run_config_wizard(ROOT, phase=phase, provider=provider, model=model, command_key=command_key)


def patchbay_config_command_set(key: str, command: str) -> dict[str, Any]:
    return run_config_wizard(ROOT, command_key_name=key, command_value=command)


def patchbay_config_test_add(command: str) -> dict[str, Any]:
    return run_config_wizard(ROOT, test_command=command)


def patchbay_config_provider_add_cli(
    provider_id: str,
    roles: list[str],
    command: str,
    args: list[str] | None = None,
    prompt_mode: str = "stdin",
    output_contract: str = "writer_diff",
) -> dict[str, Any]:
    return run_config_wizard(
        ROOT,
        provider_id=provider_id,
        provider_roles=roles,
        provider_command=command,
        provider_args=args or [],
        prompt_mode=prompt_mode,
        output_contract=output_contract,
    )


def patchbay_diff(run_id: str) -> dict[str, str]:
    return {"diff": service.diff(ROOT, run_id)}


def patchbay_apply(run_id: str) -> dict[str, Any]:
    return service.apply(ROOT, run_id)


CANONICAL_TOOLS: dict[str, Callable[..., Any]] = {
    "patchbay_plan": patchbay_plan,
    "patchbay_approve": patchbay_approve,
    "patchbay_write": patchbay_write,
    "patchbay_test": patchbay_test,
    "patchbay_review": patchbay_review,
    "patchbay_fix": patchbay_fix,
    "patchbay_status": patchbay_status,
    "patchbay_events": patchbay_events,
    "patchbay_runs": patchbay_runs,
    "patchbay_artifact": patchbay_artifact,
    "patchbay_config_show": patchbay_config_show,
    "patchbay_config_phase_set": patchbay_config_phase_set,
    "patchbay_config_command_set": patchbay_config_command_set,
    "patchbay_config_test_add": patchbay_config_test_add,
    "patchbay_config_provider_add_cli": patchbay_config_provider_add_cli,
    "patchbay_diff": patchbay_diff,
    "patchbay_apply": patchbay_apply,
}

LEGACY_TOOLS: dict[str, Callable[..., Any]] = {
    "ai_flow_plan": patchbay_plan,
    "ai_flow_approve": patchbay_approve,
    "ai_flow_write": patchbay_write,
    "ai_flow_test": patchbay_test,
    "ai_flow_review": patchbay_review,
    "ai_flow_fix": patchbay_fix,
    "ai_flow_status": patchbay_status,
    "ai_flow_events": patchbay_events,
    "ai_flow_runs": patchbay_runs,
    "ai_flow_artifact": patchbay_artifact,
    "ai_flow_config_show": patchbay_config_show,
    "ai_flow_config_phase_set": patchbay_config_phase_set,
    "ai_flow_config_command_set": patchbay_config_command_set,
    "ai_flow_config_test_add": patchbay_config_test_add,
    "ai_flow_config_provider_add_cli": patchbay_config_provider_add_cli,
    "ai_flow_diff": patchbay_diff,
    "ai_flow_apply": patchbay_apply,
}

TOOLS: dict[str, Callable[..., Any]] = {**CANONICAL_TOOLS, **LEGACY_TOOLS}


def _tool_schema(name: str) -> dict[str, Any]:
    if name.endswith("_plan"):
        properties: dict[str, Any] = {"task": {"type": "string"}}
        properties["background"] = {"type": "boolean", "description": "Start phase in the background and poll events."}
        required = ["task"]
    elif name.endswith("_runs"):
        properties = {"limit": {"type": "integer"}}
        required = []
    elif name.endswith("_artifact"):
        properties = {
            "run_id": {"type": "string"},
            "artifact": {"type": "string"},
            "tail": {"type": "integer"},
        }
        required = ["run_id", "artifact"]
    elif name.endswith("_events"):
        properties = {
            "run_id": {"type": "string"},
            "since": {"type": "integer", "description": "Return events after index N (default 0)."},
            "phase": {"type": "string", "description": "Optional filter by phase name."},
        }
        required = ["run_id"]
    elif name.endswith("_config_show"):
        properties = {}
        required = []
    elif name.endswith("_config_phase_set"):
        properties = {
            "phase": {"type": "string"},
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "command_key": {"type": "string"},
        }
        required = ["phase", "provider"]
    elif name.endswith("_config_command_set"):
        properties = {"key": {"type": "string"}, "command": {"type": "string"}}
        required = ["key", "command"]
    elif name.endswith("_config_test_add"):
        properties = {"command": {"type": "string"}}
        required = ["command"]
    elif name.endswith("_config_provider_add_cli"):
        properties = {
            "provider_id": {"type": "string"},
            "roles": {"type": "array", "items": {"type": "string"}},
            "command": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "prompt_mode": {"type": "string"},
            "output_contract": {"type": "string"},
        }
        required = ["provider_id", "roles", "command", "output_contract"]
    else:
        properties = {"run_id": {"type": "string"}}
        if any(name.endswith(suffix) for suffix in ("_write", "_test", "_review", "_fix")):
            properties["background"] = {"type": "boolean", "description": "Start phase in the background and poll events."}
        required = ["run_id"]

    descriptions: dict[str, str] = {
        "patchbay_plan": "Run the planning phase (host-agnostic — provider configurable via [phases.plan] in .ai/patchbay.toml).",
        "patchbay_approve": "Approve the plan so the writer phase can proceed.",
        "patchbay_write": "Run the implementation phase (provider configurable via [phases.write] / [writer].provider).",
        "patchbay_test": "Run test commands from the plan or allowlist inside the isolated worktree.",
        "patchbay_review": "Run the review phase (provider configurable via [phases.review]).",
        "patchbay_fix": "Run the fix phase after a CHANGES_REQUESTED review (provider defaults to write).",
        "patchbay_status": "Return current run status and artifacts, including latest cross-phase event.",
        "patchbay_events": "Return the append-only event log (JSONL stream) for a run so any host can see what every phase/agent did.",
        "patchbay_runs": "List recent Patchbay runs.",
        "patchbay_artifact": "Read a run artifact such as PLAN.md, TEST.log, REVIEW.md, or FINAL.diff.",
        "patchbay_config_show": "Show the effective Patchbay configuration.",
        "patchbay_config_phase_set": "Set a phase provider/model/command key without hand-editing TOML.",
        "patchbay_config_command_set": "Set a command alias in .ai/patchbay.toml.",
        "patchbay_config_test_add": "Add a test command to both allowlist and phase config.",
        "patchbay_config_provider_add_cli": "Add a custom CLI provider block under [providers.<id>].",
        "patchbay_diff": "Return the current FINAL.diff for the run.",
        "patchbay_apply": "Apply the reviewed patch to the original repository (no LLM executor).",
    }
    description = descriptions.get(name, name.replace("_", " "))
    if name in LEGACY_TOOLS:
        description += " (legacy ai-flow alias — use patchbay_* names for new integrations)"
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _response(request_id, {"tools": [_tool_schema(name) for name in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOLS:
            return _error(request_id, -32601, f"Unknown tool: {name}")
        try:
            result = TOOLS[name](**arguments)
        except Exception as exc:
            return _response(
                request_id,
                {
                    "content": [{"type": "text", "text": f"ERROR: {exc}"}],
                    "isError": True,
                },
            )
        return _response(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
                    }
                ]
            },
        )
    return _error(request_id, -32601, f"Unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle(message)
        except Exception as exc:
            response = _error(None, -32700, str(exc))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
