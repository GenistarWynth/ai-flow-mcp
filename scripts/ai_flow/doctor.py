from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Any

from .config import config_path, example_config_path, find_project_root, load_config
from .config_wizard import _profile_status, _run_doctor as run_config_doctor
from .mcp_install import run_mcp_doctor
from .skill_install import run_skill_doctor


def run_doctor(
    cwd: Path,
    *,
    root: str | Path | None = None,
    include_mcp: bool = True,
    skill_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run read-only readiness checks for CLI, config, MCP, Skill, and repo layout."""
    repo_root = Path(root).expanduser().resolve() if root else find_project_root(cwd, prefer_git=True)
    checks: dict[str, Any] = {
        "repo": _repo_check(repo_root),
        "config": _config_check(repo_root),
        "cli": _cli_check(repo_root),
        "mcp": _mcp_check(repo_root, include_mcp=include_mcp),
        "skill": run_skill_doctor(repo_root, path=skill_path),
    }
    return _summarize(repo_root, checks)


def _repo_check(root: Path) -> dict[str, Any]:
    git_root = _git_root(root)
    required_files = [
        "AGENTS.md",
        "docs/patchbay.md",
        ".ai/patchbay.example.toml",
    ]
    file_status = {path: (root / path).exists() for path in required_files}
    missing = [path for path, exists in file_status.items() if not exists]
    return {
        "ok": git_root is not None and not missing,
        "root": str(root),
        "git_root": str(git_root) if git_root else "",
        "git_repo": git_root is not None,
        "required_files": file_status,
        "missing_files": missing,
    }


def _config_check(root: Path) -> dict[str, Any]:
    try:
        cfg = load_config(root)
        doctor = run_config_doctor(cfg)
    except Exception as exc:
        return {
            "ok": False,
            "config": str(config_path(root)),
            "example_config": str(example_config_path(root)),
            "error": str(exc),
        }
    warnings = doctor.get("phases", {}).get("_warnings", [])
    return {
        "ok": bool(doctor.get("config_valid")),
        "config": str(config_path(root)),
        "config_exists": config_path(root).exists(),
        "example_config": str(example_config_path(root)),
        "example_config_exists": example_config_path(root).exists(),
        "phases": doctor.get("phases", {}),
        "profile": _profile_status(cfg),
        "warnings": warnings,
    }


def _cli_check(root: Path) -> dict[str, Any]:
    script = root / "scripts" / "patchbay"
    cmd_script = root / "scripts" / "patchbay.cmd"
    package_script = Path(__file__).resolve().parents[1] / "patchbay"
    package_cmd_script = Path(__file__).resolve().parents[1] / "patchbay.cmd"
    command = shutil.which("patchbay")
    mcp_command = shutil.which("patchbay-mcp")
    return {
        "ok": script.exists() or cmd_script.exists() or package_script.exists() or package_cmd_script.exists() or bool(command),
        "script": str(script),
        "script_exists": script.exists(),
        "windows_script": str(cmd_script),
        "windows_script_exists": cmd_script.exists(),
        "package_script": str(package_script),
        "package_script_exists": package_script.exists(),
        "package_windows_script": str(package_cmd_script),
        "package_windows_script_exists": package_cmd_script.exists(),
        "command": command or "",
        "command_exists": bool(command),
        "mcp_command": mcp_command or "",
        "mcp_command_exists": bool(mcp_command),
    }


def _mcp_check(root: Path, *, include_mcp: bool) -> dict[str, Any]:
    if not include_mcp:
        return {
            "ok": True,
            "skipped": True,
            "note": "Skipped by --skip-mcp; run `patchbay mcp doctor` for stdio probing.",
        }
    try:
        result = run_mcp_doctor(root)
    except Exception as exc:
        return {"ok": False, "server_reachable": False, "error": str(exc)}
    return {
        **result,
        "ok": bool(result.get("server_reachable")) and bool(result.get("required_tools_present")),
    }


def _summarize(root: Path, checks: dict[str, Any]) -> dict[str, Any]:
    required_sections = ("repo", "config", "cli", "mcp", "skill")
    next_actions = _next_actions(checks)
    ok = all(bool(checks.get(section, {}).get("ok")) for section in required_sections) and not next_actions
    return {
        "ok": ok,
        "root": str(root),
        "checks": checks,
        "next_actions": next_actions,
        "recommendations": _recommendations(checks),
    }


def _next_actions(checks: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    repo = checks.get("repo", {})
    if not repo.get("git_repo"):
        actions.append("Run this command from a git checkout or pass --root <repo>.")
    if repo.get("missing_files"):
        actions.append("Run `patchbay init` in the target repository so Patchbay project files exist.")
    cli = checks.get("cli", {})
    if not cli.get("ok"):
        actions.append("Install Patchbay or run from a local checkout with `python scripts/patchbay ...`.")
    config = checks.get("config", {})
    if not config.get("config_exists"):
        actions.append("Copy .ai/patchbay.example.toml to .ai/patchbay.toml, then adjust providers and commands.")
    if not config.get("ok"):
        actions.append("Run `patchbay config --doctor --json` and fix any phase resolution errors.")
    mcp = checks.get("mcp", {})
    if not mcp.get("ok"):
        if mcp.get("skipped"):
            actions.append("Run `patchbay doctor` without --skip-mcp before registering a host.")
        else:
            actions.append("Run `patchbay mcp doctor --json`; then re-run `patchbay mcp install <host>` if tools are missing.")
    skill = checks.get("skill", {})
    if not skill.get("source_exists"):
        actions.append("Reinstall Patchbay; the bundled Codex Skill source is missing.")
    elif not skill.get("installed"):
        actions.append("Run `patchbay skill install codex` so Codex can discover the Patchbay Skill.")
    return actions


def _recommendations(checks: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    config = checks.get("config", {})
    profile = config.get("profile", {})
    if config.get("ok") and profile.get("profile") == "custom":
        recommendations.append(
            "Run `patchbay config profile apply economy` to route write/fix implementation work to Reasonix/DeepSeek."
        )
    return recommendations


def _git_root(root: Path) -> Path | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    return Path(completed.stdout.strip()).resolve()
