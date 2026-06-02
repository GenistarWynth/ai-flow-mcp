from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .action_contract import group_actions
from .errors import AiFlowError
from .mcp_install import normalize_mcp_host


SKILL_NAME = "patchbay"
CODEX_SKILL_HOST_ALIASES = "codex, Codex CLI, Codex Desktop, Codex 桌面, OpenAI Codex"
SKILL_SOURCE_CANDIDATES = [
    Path(__file__).resolve().parent / "skill_templates" / SKILL_NAME,
    Path(__file__).resolve().parents[2] / "skills" / SKILL_NAME,
]


def run_skill_install(
    cwd: Path,
    host: str = "codex",
    *,
    path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    _normalize_skill_host(host, action="installation")
    source = _skill_source()
    skills_root = _skills_root(path)
    destination = skills_root / SKILL_NAME
    if dry_run:
        actions = [_skill_doctor_action(path)]
        return {
            "host": "codex",
            "source": str(source),
            "destination": str(destination),
            "dry_run": True,
            "actions": actions,
            "action_groups": group_actions(actions),
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    actions = [_skill_doctor_action(path)]
    return {
        "host": "codex",
        "source": str(source),
        "destination": str(destination),
        "installed": True,
        "note": "Restart or reload Codex so the new Skill metadata is discovered.",
        "actions": actions,
        "action_groups": group_actions(actions),
    }


def run_skill_print(cwd: Path, host: str = "codex") -> dict[str, Any]:
    _normalize_skill_host(host, action="printing")
    source = _skill_source()
    files: dict[str, str] = {}
    for file_path in sorted(source.rglob("*")):
        if file_path.is_file():
            files[str(file_path.relative_to(source)).replace("\\", "/")] = file_path.read_text(encoding="utf-8")
    return {"host": "codex", "source": str(source), "files": files}


def run_skill_doctor(cwd: Path, host: str = "codex", *, path: str | Path | None = None) -> dict[str, Any]:
    _normalize_skill_host(host, action="diagnostics")
    source = _find_skill_source()
    skills_root = _skills_root(path)
    destination = skills_root / SKILL_NAME
    source_files: list[str] = []
    if source:
        source_files = [
            str(file_path.relative_to(source)).replace("\\", "/")
            for file_path in sorted(source.rglob("*"))
            if file_path.is_file()
        ]
    missing_source_files = [
        file_name
        for file_name in ("SKILL.md", "agents/openai.yaml", "references/install.md")
        if file_name not in source_files
    ]
    source_ok = bool(source) and not missing_source_files
    installed = (destination / "SKILL.md").exists()
    installed_files: list[str] = []
    missing_installed_files: list[str] = []
    changed_installed_files: list[str] = []
    installed_matches_source = False
    if installed and source:
        installed_files = [
            str(file_path.relative_to(destination)).replace("\\", "/")
            for file_path in sorted(destination.rglob("*"))
            if file_path.is_file()
        ]
        missing_installed_files, changed_installed_files = _skill_install_drift(source, destination, source_files)
        installed_matches_source = not missing_installed_files and not changed_installed_files
    next_actions: list[str] = []
    if not source_ok:
        next_actions.append("Reinstall Patchbay; the bundled Codex Skill source is missing or incomplete.")
    elif not installed:
        next_actions.append("Run `patchbay skill install codex` so Codex can discover the Patchbay Skill.")
    elif not installed_matches_source:
        next_actions.append("Run `patchbay skill install codex` to update the installed Patchbay Skill from the bundled source.")
    actions: list[dict[str, Any]] = []
    if source_ok and (not installed or not installed_matches_source):
        actions.append(_skill_install_action(path))
    if next_actions:
        actions.append(_skill_doctor_action(path))
    ready = source_ok and installed and installed_matches_source
    return {
        "host": "codex",
        "ok": source_ok,
        "ready": ready,
        "status": "installed" if ready else "missing_source" if not source_ok else "not_installed" if not installed else "outdated",
        "source": str(source) if source else "",
        "source_exists": bool(source),
        "source_file_count": len(source_files),
        "missing_source_files": missing_source_files,
        "skills_root": str(skills_root),
        "destination": str(destination),
        "installed": installed,
        "installed_file_count": len(installed_files),
        "installed_matches_source": installed_matches_source,
        "missing_installed_files": missing_installed_files,
        "changed_installed_files": changed_installed_files,
        "install_command": "patchbay skill install codex",
        "doctor_command": "patchbay skill doctor codex",
        "next_actions": next_actions,
        "actions": actions,
        "action_groups": group_actions(actions),
    }


def _skill_install_drift(source: Path, destination: Path, source_files: list[str]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    changed: list[str] = []
    for file_name in source_files:
        source_file = source / file_name
        installed_file = destination / file_name
        if not installed_file.exists():
            missing.append(file_name)
            continue
        if source_file.read_bytes() != installed_file.read_bytes():
            changed.append(file_name)
    return missing, changed


def _normalize_skill_host(host: str | None, *, action: str) -> str:
    raw = str(host or "codex").strip() or "codex"
    try:
        normalized = normalize_mcp_host(raw, strict=True)
    except AiFlowError as exc:
        raise AiFlowError(
            f"Unknown Skill host: {raw}. Only the Codex Skill currently supports {action}. "
            f"Accepted Codex aliases: {CODEX_SKILL_HOST_ALIASES}.",
            stage="skill",
            suggested_next_action='Run `patchbay skill install codex` or `patchbay skill install "Codex Desktop"`.',
        ) from exc
    if normalized != "codex":
        raise AiFlowError(
            f"Only the Codex Skill currently supports {action}; {raw} is an MCP host, not a Codex Skill host. "
            f"Accepted Codex aliases: {CODEX_SKILL_HOST_ALIASES}.",
            stage="skill",
            suggested_next_action='Run `patchbay skill install codex` or `patchbay skill install "Codex Desktop"`.',
        )
    return normalized


def _skills_root(path: str | Path | None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "skills").resolve()
    return (Path.home() / ".codex" / "skills").resolve()


def _skill_install_action(path: str | Path | None) -> dict[str, Any]:
    action = {
        "id": "install_skill",
        "label": "Install Codex Skill",
        "kind": "local_agent" if path is None else "command",
        "command": _skill_command("install", path),
        "safe": True,
        "reason": (
            "Install the bundled Patchbay Skill without attempting MCP host registration."
            if path is None
            else "Install the bundled Patchbay Skill into the selected Codex skills root."
        ),
    }
    if path is None:
        action["message"] = "install Codex Skill"
        action["host"] = "codex"
    return action


def _skill_doctor_action(path: str | Path | None) -> dict[str, Any]:
    return {
        "id": "refresh_skill_doctor",
        "label": "Refresh Skill doctor",
        "kind": "command",
        "command": _skill_command("doctor", path) + " --json",
        "safe": True,
        "reason": "Re-check the bundled and installed Patchbay Skill state.",
    }


def _skill_command(command: str, path: str | Path | None) -> str:
    base = f"patchbay skill {command} codex"
    if not path:
        return base
    return f"{base} --path {_quote_arg(str(Path(path).expanduser()))}"


def _quote_arg(value: str) -> str:
    if value and not any(char.isspace() for char in value) and '"' not in value:
        return value
    return '"' + value.replace('"', '\\"') + '"'


def _skill_source() -> Path:
    found = _find_skill_source()
    if found:
        return found
    searched = ", ".join(str(path) for path in SKILL_SOURCE_CANDIDATES)
    raise AiFlowError(f"Missing bundled Skill source. Searched: {searched}", stage="skill")


def _find_skill_source() -> Path | None:
    for candidate in SKILL_SOURCE_CANDIDATES:
        if (candidate / "SKILL.md").exists():
            return candidate
    return None
