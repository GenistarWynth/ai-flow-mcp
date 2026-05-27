from __future__ import annotations

import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import agent, service


STATIC_DIR = Path(__file__).resolve().parent / "agent_static"


def create_agent_server(cwd: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    root = service.resolve_root(cwd)

    class AgentHandler(BaseHTTPRequestHandler):
        server_version = "PatchbayAgent/0.1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook
            parsed = urlparse(self.path)
            if parsed.path in {"", "/"}:
                self._send_static("index.html")
                return
            if parsed.path.startswith("/static/"):
                self._send_static(parsed.path.removeprefix("/static/"))
                return
            if parsed.path == "/api/status":
                query = parse_qs(parsed.query)
                run_id = _first(query, "run_id")
                if not run_id:
                    self._send_json({"ok": False, "error": "run_id is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                since = _int_value(_first(query, "since"), 0)
                self._send_json(agent.agent_status(root, run_id, since=since))
                return
            if parsed.path == "/api/events":
                query = parse_qs(parsed.query)
                run_id = _first(query, "run_id")
                if not run_id:
                    self._send_json({"ok": False, "error": "run_id is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(service.events(root, run_id, since=_int_value(_first(query, "since"), 0)))
                return
            if parsed.path == "/api/events/stream":
                self._send_event_stream(parsed.query)
                return
            if parsed.path == "/api/artifact":
                query = parse_qs(parsed.query)
                run_id = _first(query, "run_id")
                name = _first(query, "name")
                if not run_id or not name:
                    self._send_json({"ok": False, "error": "run_id and name are required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(service.artifact(root, run_id, name, tail=_int_optional(_first(query, "tail"))))
                return
            if parsed.path == "/api/diff":
                query = parse_qs(parsed.query)
                run_id = _first(query, "run_id")
                if not run_id:
                    self._send_json({"ok": False, "error": "run_id is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"run_id": run_id, "diff": service.diff(root, run_id)})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            parsed = urlparse(self.path)
            if parsed.path != "/api/message":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("content-length") or "0")
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(body)
                result = agent.agent_message(
                    root,
                    str(payload.get("message") or ""),
                    run_id=str(payload.get("run_id") or "") or None,
                    confirmation=str(payload.get("confirmation") or "none"),
                    include=payload.get("include") if isinstance(payload.get("include"), dict) else {},
                )
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(result)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_static(self, name: str) -> None:
            path = (STATIC_DIR / name).resolve()
            try:
                if not path.is_relative_to(STATIC_DIR.resolve()) or not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
            except AttributeError:
                if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
            data = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_event_stream(self, query_text: str) -> None:
            query = parse_qs(query_text)
            run_id = _first(query, "run_id")
            if not run_id:
                self._send_json({"ok": False, "error": "run_id is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            payload = service.events(root, run_id, since=_int_value(_first(query, "since"), 0))
            data = f"event: events\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/event-stream; charset=utf-8")
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((host, int(port)), AgentHandler)
    return server


def run_agent_server(cwd: Path, host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = False) -> dict[str, Any]:
    server = create_agent_server(cwd, host=host, port=port)
    url = f"http://{host}:{server.server_address[1]}"
    print(f"Patchbay Agent UI: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {"url": url, "stopped": True}


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return values[0] if values else ""


def _int_value(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_optional(value: str) -> int | None:
    if value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
