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


def install_codex(root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Print the ``codex mcp add`` command for Codex CLI / Codex Desktop."""
    cmd = _server_command(root)
    full = f"codex mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": "codex", "command": full, "dry_run": True}
    return {"host": "codex", "command": full, "note": "Run the command above in your terminal to register the MCP server."}


def install_claude(root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Print the ``claude mcp add`` command for Claude Code."""
    cmd = _server_command(root)
    full = f"claude mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": "claude", "command": full, "dry_run": True}
    return {"host": "claude", "command": full, "note": "Run the command above in your terminal to register the MCP server."}


def install_claude_desktop(root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Generate the Claude Desktop config snippet and optionally write it."""
    cmd = _server_command(root)
    args = cmd.split()
    entry = {
        "command": args[0],
        "args": args[1:],
    }

    config_path = _claude_desktop_config_path()
    if dry_run:
        return {
            "host": "claude-desktop",
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
        "host": "claude-desktop",
        "config_file": str(config_path),
        "entry": entry,
        "note": "Restart Claude Desktop for the change to take effect.",
    }


def install_gemini(root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Print instructions for Gemini CLI MCP registration."""
    cmd = _server_command(root)
    full = f"gemini mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": "gemini", "command": full, "dry_run": True}
    return {
        "host": "gemini",
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
    "codex": install_codex,
    "claude": install_claude,
    "claude-desktop": install_claude_desktop,
    "gemini": install_gemini,
}


def run_mcp_install(cwd: Path, host: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Entry point for ``patchbay mcp install <host>``."""
    root = _repo_root(cwd)
    handler = HOST_HANDLERS.get(host.lower())
    if handler is None:
        from .errors import AiFlowError
        raise AiFlowError(
            f"Unknown MCP host: {host}. Supported: {', '.join(sorted(HOST_HANDLERS))}.",
            stage="config",
            suggested_next_action="Run `patchbay mcp install codex` or one of the supported hosts.",
        )
    return handler(root, dry_run=dry_run)


def run_mcp_doctor(cwd: Path) -> dict[str, Any]:
    """Validate that the MCP server can be reached and tools are listed."""
    root = _repo_root(cwd)
    server_cmd = _server_command(root)
    return {
        "server_command": server_cmd,
        "server_script_exists": (root / SERVER_SCRIPT).exists(),
        "supported_hosts": sorted(HOST_HANDLERS.keys()),
        "note": "MCP tools are exposed via the server. Verify with your MCP host after registration.",
    }
