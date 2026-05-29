from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .agent import agent_message
from . import service
from .config import config_path, load_config
from .config_wizard import run_config_wizard
from .doctor import run_doctor
from .errors import AiFlowError, SafetyError, StateError
from .state import REVIEWED_PASS


ACTION_NAMES = {"approve", "write", "test", "review", "fix", "apply", "cleanup"}


def create_server(
    cwd: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    static_dir: Path | None = None,
) -> ThreadingHTTPServer:
    root = service.resolve_root(cwd)
    selected_static_root = _default_static_dir() if static_dir is None else static_dir

    class PatchbayWebHandler(_Handler):
        repo_root = root
        static_root = selected_static_root

    return ThreadingHTTPServer((host, port), PatchbayWebHandler)


def server_info(server: ThreadingHTTPServer) -> dict[str, Any]:
    host, port = server.server_address
    return {"host": host, "port": port, "url": f"http://{host}:{port}"}


def serve(
    cwd: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    json_output: bool = False,
) -> dict[str, Any]:
    server = create_server(cwd, host=host, port=port)
    info = server_info(server)
    if json_output:
        print(json.dumps(info, ensure_ascii=False, sort_keys=True), flush=True)
    else:
        print(f"Patchbay web workbench: {info['url']}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return info


class _Handler(SimpleHTTPRequestHandler):
    repo_root: Path
    static_root: Path
    server_version = "PatchbayWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        self._handle_api_write("POST")

    def do_PUT(self) -> None:
        self._handle_api_write("PUT")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            if path == "/api/health":
                self._json({"status": "ok", "service": "patchbay-web"})
                return
            if path == "/api/runs":
                limit = _int_query(query, "limit", 20)
                self._json(service.runs(self.repo_root, limit=limit))
                return
            if path == "/api/config":
                self._json(run_config_wizard(self.repo_root, show=True))
                return
            if path == "/api/config/profile":
                self._json(run_config_wizard(self.repo_root, show_profile=True))
                return
            if path == "/api/doctor":
                self._json(
                    run_doctor(
                        self.repo_root,
                        include_mcp=_bool_query(query, "include_mcp", False),
                        skill_path=_str_query(query, "skill_path"),
                        host=_str_query(query, "host") or "codex",
                    )
                )
                return
            if path == "/api/providers":
                cfg = load_config(self.repo_root)
                self._json({"config": str(config_path(self.repo_root)), "providers": cfg.get("providers", {})})
                return

            route = _run_route(path)
            if not route:
                self._not_found()
                return
            run_id, remainder = route
            if remainder == "status":
                self._json(service.status(self.repo_root, run_id))
            elif remainder == "context":
                self._json(
                    service.context(
                        self.repo_root,
                        run_id,
                        since_event=_int_query(query, "since_event", 0),
                        since_trace=_int_query(query, "since_trace", 0),
                        include_trace=_bool_query(query, "include_trace", False),
                    )
                )
            elif remainder == "events":
                self._json(
                    service.events(
                        self.repo_root,
                        run_id,
                        since=_int_query(query, "since", 0),
                        phase=_str_query(query, "phase"),
                    )
                )
            elif remainder == "trace":
                self._json(_trace(self.repo_root, run_id, query))
            elif remainder == "diff":
                self._json({"run_id": run_id, "text": service.diff(self.repo_root, run_id)})
            elif remainder.startswith("artifact/"):
                artifact_name = unquote(remainder[len("artifact/") :])
                self._json(service.artifact(self.repo_root, run_id, artifact_name, tail=_optional_int_query(query, "tail")))
            else:
                self._not_found()
        except Exception as exc:
            self._error(exc)

    def _handle_api_write(self, method: str) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json_body()
            if method == "PUT" and parsed.path == "/api/config":
                key = str(payload.get("key", "")).strip()
                if not key:
                    raise SafetyError("PUT /api/config requires a dotted 'key'.", stage="config")
                self._json(run_config_wizard(self.repo_root, set_key=key, set_value=str(payload.get("value", ""))))
                return
            if method == "POST" and parsed.path == "/api/config/profile/apply":
                profile = str(payload.get("profile", "economy") or "economy").strip()
                self._json(run_config_wizard(self.repo_root, profile=profile))
                return
            if method == "POST" and parsed.path == "/api/providers":
                self._json(_add_provider(self.repo_root, payload))
                return
            if method == "POST" and parsed.path == "/api/runs":
                self._json(_create_run(self.repo_root, payload))
                return
            if method == "POST" and parsed.path == "/api/agent/message":
                self._json(
                    agent_message(
                        self.repo_root,
                        str(payload.get("message", "")),
                        run_id=str(payload.get("run_id", "") or "") or None,
                        confirmation=str(payload.get("confirmation", "none") or "none"),
                        include=payload.get("include") if isinstance(payload.get("include"), dict) else {},
                        max_fix_rounds=_optional_payload_int(payload.get("max_fix_rounds")),
                        background=bool(payload.get("background", False)),
                    )
                )
                return
            if method == "POST":
                action = _action_route(parsed.path)
                if action:
                    run_id, action_name = action
                    self._json(_run_action(self.repo_root, run_id, action_name))
                    return
            self._not_found()
        except Exception as exc:
            self._error(exc)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafetyError(f"Invalid JSON body: {exc}", stage="web") from exc
        if not isinstance(payload, dict):
            raise SafetyError("JSON body must be an object.", stage="web")
        return payload

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            candidate = self.static_root / "index.html"
        else:
            relative = unquote(path).lstrip("/")
            candidate = self.static_root / relative
        if not candidate.exists() or not candidate.is_file():
            self._html_placeholder()
            return
        try:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self.static_root.resolve()):
                self._not_found()
                return
        except AttributeError:
            if not str(candidate.resolve()).startswith(str(self.static_root.resolve())):
                self._not_found()
                return
        content = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _html_placeholder(self) -> None:
        body = (
            "<!doctype html><html><head><meta charset='utf-8'><title>Patchbay</title></head>"
            "<body><main><h1>Patchbay Web Workbench</h1></main></body></html>"
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def _error(self, exc: Exception) -> None:
        status = HTTPStatus.INTERNAL_SERVER_ERROR
        if isinstance(exc, SafetyError):
            status = HTTPStatus.BAD_REQUEST
        elif isinstance(exc, StateError):
            status = HTTPStatus.CONFLICT
        elif isinstance(exc, AiFlowError):
            status = HTTPStatus.BAD_REQUEST
        self._json(
            {
                "error": str(exc),
                "stage": getattr(exc, "stage", None),
                "suggested_next_action": getattr(exc, "suggested_next_action", None),
            },
            status=status,
        )


def _run_action(root: Path, run_id: str, action_name: str) -> dict[str, Any]:
    if action_name not in ACTION_NAMES:
        raise SafetyError(f"Unsupported action: {action_name}", stage="web")
    handler = getattr(service, action_name)
    if action_name == "apply":
        current = service.status(root, run_id)
        gate = current.get("gate_state", {})
        if (
            current.get("status") != REVIEWED_PASS
            or current.get("review_result") != "PASS"
            or not current.get("tests_passed")
            or not gate.get("ready_to_apply")
        ):
            raise StateError(
                "Apply is only available after tests pass and review returns PASS.",
                stage="apply",
                suggested_next_action="Run test and review, then refresh run status before applying.",
            )
    return handler(root, run_id)


def _create_run(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    task = str(payload.get("task", "")).strip()
    if not task:
        raise SafetyError("POST /api/runs requires a non-empty task.", stage="plan")
    background = bool(payload.get("background", False))
    if background:
        return service.start_background_phase(root, "plan", task=task)
    return service.plan(root, task=task)


def _add_provider(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(payload.get("provider_id", "")).strip()
    if not provider_id:
        raise SafetyError("POST /api/providers requires provider_id.", stage="config")
    roles = payload.get("roles", [])
    if not isinstance(roles, list):
        raise SafetyError("Provider roles must be a list.", stage="config")
    args = payload.get("args", [])
    if not isinstance(args, list):
        raise SafetyError("Provider args must be a list.", stage="config")
    return run_config_wizard(
        root,
        provider_id=provider_id,
        provider_roles=[str(role) for role in roles],
        provider_command=str(payload.get("command", "")),
        provider_args=[str(arg) for arg in args],
        prompt_mode=str(payload.get("prompt_mode", "stdin")),
        output_contract=str(payload.get("output_contract", "")),
    )


def _trace(root: Path, run_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
    trace_func = getattr(service, "trace", None)
    if callable(trace_func):
        return trace_func(root, run_id, since=_int_query(query, "since", 0), phase=_str_query(query, "phase"))
    service.status(root, run_id)
    return {"run_id": run_id, "since": _int_query(query, "since", 0), "total": 0, "returned": 0, "trace": []}


def _run_route(path: str) -> tuple[str, str] | None:
    prefix = "/api/runs/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix) :]
    if "/" not in rest:
        return None
    run_id, remainder = rest.split("/", 1)
    return unquote(run_id), remainder


def _action_route(path: str) -> tuple[str, str] | None:
    route = _run_route(path)
    if not route:
        return None
    run_id, remainder = route
    prefix = "actions/"
    if not remainder.startswith(prefix):
        return None
    return run_id, remainder[len(prefix) :]


def _int_query(query: dict[str, list[str]], name: str, default: int) -> int:
    value = _str_query(query, name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SafetyError(f"Query parameter '{name}' must be an integer.", stage="web") from exc


def _optional_int_query(query: dict[str, list[str]], name: str) -> int | None:
    if name not in query:
        return None
    return _int_query(query, name, 0)


def _optional_payload_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _str_query(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    value = values[0]
    return value if value != "" else None


def _bool_query(query: dict[str, list[str]], name: str, default: bool) -> bool:
    value = _str_query(query, name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _default_static_dir() -> Path:
    return Path(__file__).resolve().parent / "web_static"
