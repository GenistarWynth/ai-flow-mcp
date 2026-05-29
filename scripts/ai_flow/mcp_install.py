"""MCP host registration helpers — no hand-editing JSON/TOML required.

``patchbay mcp install <host>`` writes or runs the registration for the local
Patchbay MCP server, falling back to a copyable command when a host CLI is not
available.  Supported hosts:

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
CANONICAL_HOSTS = ("codex", "claude", "claude-code", "claude-desktop", "gemini")
HOST_ALIASES = {
    "codex": "codex",
    "codex cli": "codex",
    "codex desktop": "codex",
    "openai codex": "codex",
    "claude": "claude",
    "claude cli": "claude",
    "anthropic claude": "claude",
    "claude code": "claude-code",
    "claude-code": "claude-code",
    "claude_code": "claude-code",
    "claudecode": "claude-code",
    "claude desktop": "claude-desktop",
    "claude-desktop": "claude-desktop",
    "claude_desktop": "claude-desktop",
    "claudedesktop": "claude-desktop",
    "gemini": "gemini",
    "gemini cli": "gemini",
    "google gemini": "gemini",
}


def _repo_root(cwd: Path) -> Path:
    from .config import find_project_root
    return find_project_root(cwd, prefer_git=True)


def normalize_mcp_host(host: str | None, *, default: str = "codex", strict: bool = False) -> str:
    """Return the canonical MCP host id used by setup, doctor, and install."""
    raw = str(host or default).strip()
    key = " ".join(raw.replace("_", " ").replace("-", " ").split()).lower()
    normalized = HOST_ALIASES.get(key) or HOST_ALIASES.get(raw.lower())
    if normalized:
        return normalized
    if strict:
        from .errors import AiFlowError

        raise AiFlowError(
            f"Unknown MCP host: {raw or host}. Supported: {', '.join(CANONICAL_HOSTS)}. "
            "Common aliases such as Claude Desktop, Claude Code, and Gemini CLI are also accepted.",
            stage="config",
            suggested_next_action="Run `patchbay mcp install codex`, `patchbay mcp install \"Claude Desktop\"`, or one of the supported hosts.",
        )
    return normalize_mcp_host(default, default="codex", strict=True)


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


def _host_install_argv(host: str, root: Path) -> list[str] | None:
    server_argv = _server_argv(root)
    host_lower = host.lower()
    if host_lower in {"codex", "claude", "claude-code", "gemini"}:
        cli = "claude" if host_lower.startswith("claude") and host_lower != "claude-desktop" else host_lower
        return [cli, "mcp", "add", SERVER_NAME, "--", *server_argv]
    return None


def _execute_host_install(host: str, root: Path) -> dict[str, Any]:
    argv = _host_install_argv(host, root)
    if not argv:
        return {"executed": False, "already_registered": False, "exit_code": None, "stdout": "", "stderr": "", "error": None}
    try:
        completed = subprocess.run(
            argv,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return {
            "executed": False,
            "already_registered": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": str(exc),
        }
    combined_output = "\n".join(part for part in (completed.stdout or "", completed.stderr or "") if part)
    if completed.returncode != 0 and _already_registered(combined_output):
        return {
            "executed": True,
            "already_registered": True,
            "exit_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "error": None,
        }
    if completed.returncode != 0:
        return {
            "executed": False,
            "already_registered": False,
            "exit_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "error": (completed.stderr or completed.stdout or f"exit code {completed.returncode}").strip(),
        }
    return {
        "executed": True,
        "already_registered": False,
        "exit_code": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "error": None,
    }


def _already_registered(output: str) -> bool:
    lowered = output.lower()
    return SERVER_NAME in lowered and any(
        phrase in lowered
        for phrase in (
            "already exists",
            "already registered",
            "exists already",
        )
    )


def install_codex(root: Path, dry_run: bool = False, *, host_name: str = "codex") -> dict[str, Any]:
    """Register the server with Codex CLI / Codex Desktop."""
    cmd = _server_command(root)
    full = f"codex mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": host_name, "command": full, "dry_run": True}
    result = _execute_host_install("codex", root)
    if result["executed"]:
        return {
            "host": host_name,
            "command": full,
            **result,
            "note": "MCP server registered successfully.",
        }
    return {
        "host": host_name,
        "command": full,
        **result,
        "note": "Run the command above in your terminal to register the MCP server.",
    }


def install_claude(root: Path, dry_run: bool = False, *, host_name: str = "claude") -> dict[str, Any]:
    """Register the server with Claude Code."""
    cmd = _server_command(root)
    full = f"claude mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": host_name, "command": full, "dry_run": True}
    result = _execute_host_install("claude", root)
    if result["executed"]:
        return {
            "host": host_name,
            "command": full,
            **result,
            "note": "MCP server registered successfully.",
        }
    return {
        "host": host_name,
        "command": full,
        **result,
        "note": "Run the command above in your terminal to register the MCP server.",
    }


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
    """Register the server with Gemini CLI."""
    cmd = _server_command(root)
    full = f"gemini mcp add {SERVER_NAME} -- {cmd}"
    if dry_run:
        return {"host": host_name, "command": full, "dry_run": True}
    result = _execute_host_install("gemini", root)
    if result["executed"]:
        return {
            "host": host_name,
            "command": full,
            **result,
            "note": "MCP server registered successfully.",
        }
    return {
        "host": host_name,
        "command": full,
        **result,
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
    normalized_host = normalize_mcp_host(host, strict=True)
    handler = HOST_HANDLERS[normalized_host]
    return handler(repo_root, dry_run=dry_run)


def run_mcp_doctor(cwd: Path, *, root: str | Path | None = None) -> dict[str, Any]:
    """Validate that the MCP server can be reached and tools are listed."""
    repo_root = Path(root).expanduser().resolve() if root else _repo_root(cwd)
    server_cmd = _server_command(repo_root)
    probe = _probe_mcp_server(repo_root)
    return {
        "server_command": server_cmd,
        "server_script_exists": (repo_root / SERVER_SCRIPT).exists(),
        "supported_hosts": list(CANONICAL_HOSTS),
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
        "patchbay_install",
        "patchbay_skill_install",
        "patchbay_skill_doctor",
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
