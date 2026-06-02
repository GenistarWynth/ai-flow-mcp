from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Any

from .action_contract import group_actions
from .config import config_path, example_config_path, find_project_root, load_config, route_label
from .config_wizard import _configure_reasonix_action, _profile_status, _run_doctor as run_config_doctor
from .mcp_install import normalize_mcp_host, run_mcp_doctor
from .routing import profile_routing_digest
from .skill_install import run_skill_doctor


def run_doctor(
    cwd: Path,
    *,
    root: str | Path | None = None,
    include_mcp: bool = False,
    suppress_mcp_actions: bool = False,
    skill_path: str | Path | None = None,
    host: str = "codex",
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
    return _summarize(repo_root, checks, host=host, suppress_mcp_actions=suppress_mcp_actions)


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
            "note": "Skipped by default; run `patchbay doctor --probe-mcp` or `patchbay mcp doctor` for stdio probing.",
        }
    try:
        result = run_mcp_doctor(root)
    except Exception as exc:
        return {"ok": False, "server_reachable": False, "error": str(exc)}
    return {
        **result,
        "ok": bool(result.get("server_reachable")) and bool(result.get("required_tools_present")),
    }


def _summarize(root: Path, checks: dict[str, Any], *, host: str, suppress_mcp_actions: bool = False) -> dict[str, Any]:
    required_sections = ("repo", "config", "cli", "mcp", "skill")
    normalized_host = _doctor_host(host)
    next_actions = _next_actions(checks, host=normalized_host, suppress_mcp_actions=suppress_mcp_actions)
    recommendations = _recommendations(checks)
    routing = _routing_digest(checks)
    actions = _structured_actions(
        checks,
        next_actions,
        recommendations,
        host=normalized_host,
        suppress_mcp_actions=suppress_mcp_actions,
    )
    ok = all(bool(checks.get(section, {}).get("ok")) for section in required_sections) and not next_actions
    summary = {
        "ok": ok,
        "root": str(root),
        "host": normalized_host,
        "checks": checks,
        "next_actions": next_actions,
        "recommendations": recommendations,
        "actions": actions,
        "action_groups": group_actions(actions),
    }
    if routing:
        summary["routing"] = routing
    return summary


def _routing_digest(checks: dict[str, Any]) -> dict[str, Any] | None:
    config = checks.get("config", {}) if isinstance(checks.get("config"), dict) else {}
    profile = config.get("profile") if isinstance(config.get("profile"), dict) else None
    return profile_routing_digest(profile) if profile else None


def _next_actions(checks: dict[str, Any], *, host: str, suppress_mcp_actions: bool = False) -> list[str]:
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
    if not suppress_mcp_actions and not mcp.get("ok"):
        if mcp.get("skipped"):
            actions.append(f"Run `patchbay doctor --host {host} --probe-mcp --json` before registering a host if you need stdio tool-list evidence.")
        else:
            actions.append(f"Run `patchbay mcp doctor --json`; then re-run `patchbay mcp install {host}` if tools are missing.")
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
    economy = profile.get("economy", {}) if isinstance(profile.get("economy"), dict) else {}
    target = economy.get("target", {}) if isinstance(economy.get("target"), dict) else {}
    target_name = str(target.get("label") or route_label(target))
    if config.get("ok") and profile.get("profile") == "custom":
        recommendations.append(
            f"Run `patchbay config profile apply economy` to route write/fix implementation work to {target_name}."
        )
    if config.get("ok") and economy.get("matches") and economy.get("command_ready") is False:
        status = _first_not_ready_command_status(economy.get("command_status"))
        source = str(status.get("source") or "the configured provider command")
        if target.get("provider") == "reasonix_cli":
            recommendations.append(
                f"Set `commands.reasonix` so the {target_name} write/fix economy route can actually execute."
            )
        else:
            recommendations.append(
                f"Fix `{source}` so the {target_name} write/fix economy route can actually execute."
            )
    return recommendations


def _structured_actions(
    checks: dict[str, Any],
    next_actions: list[str],
    recommendations: list[str],
    *,
    host: str,
    suppress_mcp_actions: bool = False,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    repo = checks.get("repo", {})
    config = checks.get("config", {})
    cli = checks.get("cli", {})
    mcp = checks.get("mcp", {})
    skill = checks.get("skill", {})
    profile = config.get("profile", {}) if isinstance(config.get("profile"), dict) else {}
    economy = profile.get("economy", {}) if isinstance(profile.get("economy"), dict) else {}
    target = economy.get("target", {}) if isinstance(economy.get("target"), dict) else {}
    target_name = str(target.get("label") or route_label(target))

    if repo.get("missing_files") or not config.get("config_exists"):
        actions.append(
            {
                "id": "run_setup",
                "label": "Run setup",
                "kind": "local_agent",
                "message": _setup_message(host),
                "host": host,
                "safe": True,
                "reason": "Initialize Patchbay project files, local config, Skill installation, MCP guidance, and a doctor summary.",
            }
        )
    if skill.get("source_exists") and not skill.get("installed"):
        actions.append(
            {
                "id": "install_skill",
                "label": "Install Codex Skill",
                "kind": "local_agent",
                "message": "install Codex Skill",
                "host": "codex",
                "command": "patchbay skill install codex",
                "safe": True,
                "reason": "Install the bundled Patchbay Skill without attempting MCP host registration.",
            }
        )
    if not suppress_mcp_actions and mcp.get("skipped"):
        actions.append(
            {
                "id": "probe_mcp",
                "label": "Probe MCP",
                "kind": "command",
                "command": f"patchbay doctor --host {host} --probe-mcp --json",
                "host": host,
                "safe": True,
                "reason": "Run the stdio MCP probe when the host needs full tool registration evidence.",
            }
        )
    elif not suppress_mcp_actions and not mcp.get("ok"):
        actions.append(
            {
                "id": "install_mcp",
                "label": "Register MCP",
                "kind": "command",
                "command": f"patchbay mcp install {_doctor_host(host)}",
                "host": _doctor_host(host),
                "safe": True,
                "reason": "Register the Patchbay MCP server with the target host after inspecting the doctor output.",
            }
        )
    if not cli.get("ok"):
        actions.append(
            {
                "id": "install_patchbay",
                "label": "Install Patchbay",
                "kind": "command",
                "command": "uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex",
                "safe": True,
                "reason": "Install or launch Patchbay from the published package path.",
            }
        )
    if any("config profile apply economy" in item for item in recommendations):
        actions.append(
            {
                "id": "apply_economy_profile",
                "label": "Apply economy profile",
                "kind": "local_agent",
                "message": "apply economy profile",
                "safe": True,
                "reason": f"Route high-volume write/fix implementation work to {target_name}.",
            }
        )
    if any("commands.reasonix" in item for item in recommendations):
        actions.append(_configure_reasonix_action(target_name))
        actions.append(_configure_deepseek_provider_action())
    if economy.get("command_ready") is False and target.get("provider") != "reasonix_cli":
        status = _first_not_ready_command_status(economy.get("command_status"))
        source = str(status.get("source") or "providers.<id>.command")
        if source.startswith("providers."):
            actions.append(_configure_provider_command_action(source, target_name))
        actions.append(
            {
                "id": "inspect_economy_provider_command",
                "label": "Inspect provider command",
                "kind": "local_agent",
                "message": "readiness",
                "safe": True,
                "reason": f"Inspect the configured command for the {target_name} economy provider.",
            }
        )
    if next_actions or recommendations:
        actions.append(
            {
                "id": "refresh_readiness",
                "label": "Refresh readiness",
                "kind": "local_agent",
                "message": "readiness",
                "host": host,
                "safe": True,
                "reason": "Re-run read-only readiness checks after applying setup or routing changes.",
            }
        )
    return _dedupe_actions(actions)


def _first_not_ready_command_status(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    for item in value.values():
        if isinstance(item, dict) and item.get("required") and item.get("ready") is False:
            return item
    return {}


def _configure_provider_command_action(source: str, target_name: str) -> dict[str, Any]:
    return {
        "id": "configure_economy_provider_command",
        "label": "Copy provider command",
        "kind": "command",
        "command": f"patchbay config --set-key {source} --set-value <command>",
        "safe": True,
        "reason": f"Copy the command for the {target_name} economy provider into .ai/patchbay.toml.",
    }


def _configure_deepseek_provider_action() -> dict[str, Any]:
    return {
        "id": "configure_deepseek_provider",
        "label": "Configure DeepSeek provider",
        "kind": "local_agent",
        "message": "configure DeepSeek provider",
        "safe": True,
        "reason": "Offer a custom low-cost CLI writer template when the default Reasonix/DeepSeek route is not executable.",
    }


def _setup_message(host: str) -> str:
    normalized = _doctor_host(host)
    return "patchbay setup" if normalized == "codex" else f"patchbay setup for {normalized}"


def _doctor_host(host: str) -> str:
    return normalize_mcp_host(host, strict=False)


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for action in actions:
        action_id = str(action.get("id") or "")
        if action_id in seen:
            continue
        seen.add(action_id)
        result.append(action)
    return result


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
