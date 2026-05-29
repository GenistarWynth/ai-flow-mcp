from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .errors import AiFlowError


SKILL_NAME = "patchbay"
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
    if host.lower() != "codex":
        raise AiFlowError("Only Codex Skill installation is currently supported.", stage="skill")
    source = _skill_source()
    skills_root = _skills_root(path)
    destination = skills_root / SKILL_NAME
    if dry_run:
        return {
            "host": "codex",
            "source": str(source),
            "destination": str(destination),
            "dry_run": True,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return {
        "host": "codex",
        "source": str(source),
        "destination": str(destination),
        "installed": True,
        "note": "Restart or reload Codex so the new Skill metadata is discovered.",
    }


def run_skill_print(cwd: Path, host: str = "codex") -> dict[str, Any]:
    if host.lower() != "codex":
        raise AiFlowError("Only Codex Skill printing is currently supported.", stage="skill")
    source = _skill_source()
    files: dict[str, str] = {}
    for file_path in sorted(source.rglob("*")):
        if file_path.is_file():
            files[str(file_path.relative_to(source)).replace("\\", "/")] = file_path.read_text(encoding="utf-8")
    return {"host": "codex", "source": str(source), "files": files}


def run_skill_doctor(cwd: Path, host: str = "codex", *, path: str | Path | None = None) -> dict[str, Any]:
    if host.lower() != "codex":
        raise AiFlowError("Only Codex Skill diagnostics are currently supported.", stage="skill")
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
    next_actions: list[str] = []
    if not source_ok:
        next_actions.append("Reinstall Patchbay; the bundled Codex Skill source is missing or incomplete.")
    elif not installed:
        next_actions.append("Run `patchbay skill install codex` so Codex can discover the Patchbay Skill.")
    return {
        "host": "codex",
        "ok": source_ok,
        "ready": source_ok and installed,
        "status": "installed" if source_ok and installed else "missing_source" if not source_ok else "not_installed",
        "source": str(source) if source else "",
        "source_exists": bool(source),
        "source_file_count": len(source_files),
        "missing_source_files": missing_source_files,
        "skills_root": str(skills_root),
        "destination": str(destination),
        "installed": installed,
        "install_command": "patchbay skill install codex",
        "doctor_command": "patchbay skill doctor codex",
        "next_actions": next_actions,
    }


def _skills_root(path: str | Path | None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "skills").resolve()
    return (Path.home() / ".codex" / "skills").resolve()


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
