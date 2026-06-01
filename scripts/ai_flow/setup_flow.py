from __future__ import annotations

from pathlib import Path
from typing import Any

from . import service
from .artifacts import read_text, write_text
from .config import config_path, example_config_path, find_project_root
from .doctor import run_doctor
from .errors import AiFlowError
from .mcp_install import normalize_mcp_host, run_mcp_install
from .skill_install import run_skill_install


MCP_FOLLOWUP_ACTION_IDS = {"install_mcp", "probe_mcp", "register_mcp"}
MCP_FOLLOWUP_TEXT_MARKERS = (
    "--probe-mcp",
    "mcp install",
    "patchbay mcp",
    "register the mcp",
)


def run_setup(
    cwd: Path,
    *,
    root: str | Path | None = None,
    host: str = "codex",
    skill_path: str | Path | None = None,
    dry_run: bool = False,
    skip_skill: bool = False,
    skip_mcp: bool = False,
    mcp_dry_run: bool = False,
    probe_mcp: bool = False,
    create_config: bool = True,
) -> dict[str, Any]:
    """One-command local setup for Patchbay CLI, MCP, and Skill usage."""
    repo_root = Path(root).expanduser().resolve() if root else find_project_root(cwd, prefer_git=True)
    setup_host = normalize_mcp_host(host, strict=True)
    init = _init_step(repo_root, dry_run=dry_run)
    config = _config_step(repo_root, dry_run=dry_run, create_config=create_config)
    skill = (
        {"skipped": True, "reason": "skip_skill"}
        if skip_skill
        else run_skill_install(repo_root, path=skill_path, dry_run=dry_run)
    )
    mcp = (
        {"skipped": True, "reason": "skip_mcp"}
        if skip_mcp
        else run_mcp_install(repo_root, setup_host, root=repo_root, dry_run=dry_run or mcp_dry_run)
    )
    doctor = run_doctor(
        repo_root,
        include_mcp=probe_mcp and not skip_mcp,
        suppress_mcp_actions=skip_mcp,
        skill_path=skill_path,
        host=setup_host,
    )
    next_actions = list(doctor.get("next_actions") or [])
    if isinstance(mcp, dict) and mcp.get("command") and not mcp.get("dry_run") and not mcp.get("executed"):
        next_actions.append(f"Register the MCP server with: {mcp['command']}")
    elif isinstance(mcp, dict) and mcp.get("executed"):
        note = str(mcp.get("note") or "").strip()
        if note:
            next_actions.append(note)
    actions = list(doctor.get("actions") or [])
    if isinstance(mcp, dict) and mcp.get("command") and not mcp.get("dry_run") and not mcp.get("executed"):
        actions.append(
            {
                "id": "register_mcp",
                "label": "Register MCP",
                "kind": "command",
                "command": str(mcp["command"]),
                "host": str(mcp.get("host") or setup_host),
                "safe": True,
                "reason": "Register the MCP server command returned by setup.",
            }
        )
    if skip_mcp:
        next_actions = _without_mcp_followup_text(next_actions)
        actions = _without_mcp_followup_actions(actions)
    return {
        "ok": bool(doctor.get("ok")),
        "dry_run": dry_run,
        "applied": not dry_run,
        "setup_host": setup_host,
        "root": str(repo_root),
        "init": init,
        "config": config,
        "skill": skill,
        "mcp": mcp,
        "doctor": doctor,
        "next_actions": _dedupe(next_actions),
        "actions": _dedupe_actions(actions),
    }


def _init_step(root: Path, *, dry_run: bool) -> dict[str, Any]:
    paths = {
        "example_config": root / ".ai" / "patchbay.example.toml",
        "docs": root / "docs" / "patchbay.md",
        "agents": root / "AGENTS.md",
    }
    if dry_run:
        return {
            "dry_run": True,
            "root": str(root),
            "would_create": [name for name, path in paths.items() if not path.exists()],
        }
    result = service.init_project(root)
    return {**result, "created_or_verified": True}


def _config_step(root: Path, *, dry_run: bool, create_config: bool) -> dict[str, Any]:
    path = config_path(root)
    example = example_config_path(root)
    if not create_config:
        return {
            "skipped": True,
            "path": str(path),
            "exists": path.exists(),
            "reason": "create_config disabled",
        }
    if path.exists():
        return {"path": str(path), "exists": True, "created": False}
    if dry_run:
        return {
            "dry_run": True,
            "path": str(path),
            "exists": False,
            "would_create": True,
            "source": str(example),
        }
    text = read_text(example, default="")
    if not text:
        raise AiFlowError("Missing .ai/patchbay.example.toml after setup initialization.", stage="setup")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, text.rstrip() + "\n")
    return {
        "path": str(path),
        "exists": True,
        "created": True,
        "source": str(example),
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _without_mcp_followup_text(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        lowered = item.lower()
        if any(marker in lowered for marker in MCP_FOLLOWUP_TEXT_MARKERS):
            continue
        result.append(item)
    return result


def _without_mcp_followup_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if str(item.get("id") or "") not in MCP_FOLLOWUP_ACTION_IDS]


def _dedupe_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        action_id = str(item.get("id") or "")
        if action_id in seen:
            continue
        seen.add(action_id)
        result.append(item)
    return result
