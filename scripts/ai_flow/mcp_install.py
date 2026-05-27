"""MCP host registration helpers — no hand-editing JSON/TOML required.

``patchbay mcp install <host>`` writes or prints the registration for the
local Patchbay MCP server.  Supported hosts:

    codex       Codex CLI / Codex Desktop
    claude      Claude Code
    claude-desk Claude Desktop (edits claude_desktop_config.json)
    gemini      Gemini CLI

``patchbay mcp doctor`` validates that the MCP tools are reachable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SERVER_SCRIPT = "scripts/patchbay_mcp_server.py"
SERVER_NAME = "patchbay"


def _repo_root(cwd: Path) -> Path:
    from .config import find_project_root
    return find_project_root(cwd, prefer_git=True)


def _server_command(root: Path) -> str:
    """Return the command string that starts the MCP server."""
    server_path = root / SERVER_SCRIPT
    if server_path.exists():
        return f"python {server_path} --root {root}"
    return f"patchbay-mcp --root {root}"


def _server_argv(root: Path) -> list[str]:
    server_path = root / SERVER_SCRIPT
    if server_path.exists():
        return [sys.executable, str(server_path), "--root", str(root)]
    return ["patchbay-mcp", "--root", str(root)]


def install_codex(root: Path, dry_run: bool = False, *, host_name: str = "codex") -> dict[str, Any]:
    """Print the ``codex mcp add`` command for Codex CLI / Codex Desktop."""
    cmd = _server_command(root)
    full = f"codex mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": host_name, "command": full, "dry_run": True}
    return {"host": host_name, "command": full, "note": "Run the command above in your terminal to register the MCP server."}


def install_claude(root: Path, dry_run: bool = False, *, host_name: str = "claude") -> dict[str, Any]:
    """Print the ``claude mcp add`` command for Claude Code."""
    cmd = _server_command(root)
    full = f"claude mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": host_name, "command": full, "dry_run": True}
    return {"host": host_name, "command": full, "note": "Run the command above in your terminal to register the MCP server."}


def install_claude_desktop(root: Path, dry_run: bool = False, *, host_name: str = "claude-desktop") -> dict[str, Any]:
    """Generate the Claude Desktop config snippet and optionally write it."""
    args = _server_argv(root)
    entry = {
        "command": args[0],
        "args": args[1:],
    }

    config_path = _claude_desktop_config_path()
    if dry_run:
        return {
            "host": host_name,
            "config_file": str(config_path),
            "entry": entry,
            "dry_run": True,
        }

    # Try to read existing config
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    mcp_servers = existing.get("mcpServers", {})
    if isinstance(mcp_servers, dict):
        mcp_servers[SERVER_NAME] = entry
    else:
        mcp_servers = {SERVER_NAME: entry}
    existing["mcpServers"] = mcp_servers

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    return {
        "host": host_name,
        "config_file": str(config_path),
        "entry": entry,
        "note": "Restart Claude Desktop for the change to take effect.",
    }


def install_gemini(root: Path, dry_run: bool = False, *, host_name: str = "gemini") -> dict[str, Any]:
    """Print instructions for Gemini CLI MCP registration."""
    cmd = _server_command(root)
    full = f"gemini mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": host_name, "command": full, "dry_run": True}
    return {
        "host": host_name,
        "command": full,
        "note": "Run the command above in your terminal, or use the Gemini CLI MCP config UI.",
    }


def _claude_desktop_config_path() -> Path:
    """Return the platform-specific Claude Desktop config path."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming" / "Claude"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Claude"
    else:
        base = Path.home() / ".config" / "Claude"
    return base / "claude_desktop_config.json"


HOST_HANDLERS: dict[str, Any] = {
    "codex": lambda root, dry_run=False: install_codex(root, dry_run=dry_run, host_name="codex"),
    "claude": lambda root, dry_run=False: install_claude(root, dry_run=dry_run, host_name="claude"),
    "claude-code": lambda root, dry_run=False: install_claude(root, dry_run=dry_run, host_name="claude-code"),
    "claude-desktop": lambda root, dry_run=False: install_claude_desktop(root, dry_run=dry_run, host_name="claude-desktop"),
    "gemini": lambda root, dry_run=False: install_gemini(root, dry_run=dry_run, host_name="gemini"),
}


def run_mcp_install(cwd: Path, host: str, *, root: str | Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Entry point for ``patchbay mcp install <host>``."""
    repo_root = Path(root).expanduser().resolve() if root else _repo_root(cwd)
    handler = HOST_HANDLERS.get(host.lower())
    if handler is None:
        from .errors import AiFlowError
        raise AiFlowError(
            f"Unknown MCP host: {host}. Supported: {', '.join(sorted(HOST_HANDLERS))}.",
            stage="config",
            suggested_next_action="Run `patchbay mcp install codex` or one of the supported hosts.",
        )
    return handler(repo_root, dry_run=dry_run)


def run_mcp_doctor(cwd: Path, *, root: str | Path | None = None) -> dict[str, Any]:
    """Validate that the MCP server can be reached and tools are listed."""
    repo_root = Path(root).expanduser().resolve() if root else _repo_root(cwd)
    server_cmd = _server_command(repo_root)
    probe = _probe_mcp_server(repo_root)
    return {
        "server_command": server_cmd,
        "server_script_exists": (repo_root / SERVER_SCRIPT).exists(),
        "supported_hosts": sorted(HOST_HANDLERS.keys()),
        "server_reachable": probe["ok"],
        "tool_count": probe.get("tool_count", 0),
        "required_tools_present": probe.get("required_tools_present", False),
        "missing_tools": probe.get("missing_tools", []),
        "server_info": probe.get("server_info", {}),
        "error": probe.get("error"),
        "note": "Doctor starts the stdio MCP server and verifies initialize/tools/list.",
    }


def _probe_mcp_server(root: Path) -> dict[str, Any]:
    required = {
        "patchbay_agent",
        "patchbay_plan",
        "patchbay_context",
        "patchbay_metrics",
        "patchbay_setup",
        "patchbay_events",
        "patchbay_apply",
        "patchbay_doctor",
    }
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    try:
        completed = subprocess.run(
            _server_argv(root),
            cwd=str(root),
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if completed.returncode != 0:
        return {"ok": False, "error": (completed.stderr or completed.stdout or f"server exited {completed.returncode}").strip()}
    responses: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            responses.append(parsed)
    initialize = next((item for item in responses if item.get("id") == 1), {})
    tools_response = next((item for item in responses if item.get("id") == 2), {})
    tools = tools_response.get("result", {}).get("tools", [])
    names = {str(tool.get("name")) for tool in tools if isinstance(tool, dict)}
    missing = sorted(required - names)
    return {
        "ok": bool(initialize.get("result")) and not missing,
        "server_info": initialize.get("result", {}).get("serverInfo", {}),
        "tool_count": len(tools),
        "required_tools_present": not missing,
        "missing_tools": missing,
        "error": None if not missing else "Missing required tools: " + ", ".join(missing),
    }
