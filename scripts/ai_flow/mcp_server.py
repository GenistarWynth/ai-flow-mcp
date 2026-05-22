from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ai_flow import service
else:
    from . import service


ROOT = Path.cwd()


def ai_flow_plan(task: str) -> dict[str, Any]:
    return service.plan(ROOT, task=task)


def ai_flow_approve(run_id: str) -> dict[str, Any]:
    return service.approve(ROOT, run_id)


def ai_flow_write(run_id: str) -> dict[str, Any]:
    return service.write(ROOT, run_id)


def ai_flow_test(run_id: str) -> dict[str, Any]:
    return service.test(ROOT, run_id)


def ai_flow_review(run_id: str) -> dict[str, Any]:
    return service.review(ROOT, run_id)


def ai_flow_fix(run_id: str) -> dict[str, Any]:
    return service.fix(ROOT, run_id)


def ai_flow_status(run_id: str) -> dict[str, Any]:
    return service.status(ROOT, run_id)


def ai_flow_diff(run_id: str) -> dict[str, str]:
    return {"diff": service.diff(ROOT, run_id)}


def ai_flow_apply(run_id: str) -> dict[str, Any]:
    return service.apply(ROOT, run_id)


TOOLS: dict[str, Callable[..., Any]] = {
    "ai_flow_plan": ai_flow_plan,
    "ai_flow_approve": ai_flow_approve,
    "ai_flow_write": ai_flow_write,
    "ai_flow_test": ai_flow_test,
    "ai_flow_review": ai_flow_review,
    "ai_flow_fix": ai_flow_fix,
    "ai_flow_status": ai_flow_status,
    "ai_flow_diff": ai_flow_diff,
    "ai_flow_apply": ai_flow_apply,
}


def _tool_schema(name: str) -> dict[str, Any]:
    if name == "ai_flow_plan":
        properties = {"task": {"type": "string"}}
        required = ["task"]
    else:
        properties = {"run_id": {"type": "string"}}
        required = ["run_id"]
    return {
        "name": name,
        "description": name.replace("_", " "),
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
                "serverInfo": {"name": "ai-flow", "version": "0.1.0"},
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
