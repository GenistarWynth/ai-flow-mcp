from __future__ import annotations

import os
import shlex
import subprocess
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

from .artifacts import ai_dir


EXAMPLE_CONFIG_NAME = "ai-flow.example.toml"
CONFIG_NAME = "ai-flow.toml"


DEFAULT_CONFIG: dict[str, Any] = {
    "models": {
        "planner": "claude-opus-4-7",
        "writer": "deepseek-v4-pro",
        "reviewer": "gpt-5.5",
    },
    "commands": {
        "claude": "claude",
        "codex": "codex",
        "reasonix": "",
    },
    "writer": {
        "provider": "deepseek_api",
        "max_context_files": 30,
        "max_patch_attempts": 3,
        "max_repair_iterations": 2,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "workflow": {
        "require_plan_approval": True,
        "default_branch_prefix": "ai-flow",
        "worktree_root": "../.ai-flow-worktrees",
        "fail_on_dirty_workspace": True,
        "apply_to_current_workspace_only_after_review_pass": True,
    },
    "commands_allowlist": {
        "test": [
            "npm test",
            "npm run test",
            "npm run lint",
            "npm run typecheck",
            "pytest",
            "pytest -q",
            "go test ./...",
            "cargo test",
        ],
    },
}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def config_path(root: Path) -> Path:
    return ai_dir(root) / CONFIG_NAME


def example_config_path(root: Path) -> Path:
    return ai_dir(root) / EXAMPLE_CONFIG_NAME


def load_config(root: Path) -> dict[str, Any]:
    path = config_path(root)
    if path.exists():
        with path.open("rb") as handle:
            return deep_merge(DEFAULT_CONFIG, tomllib.load(handle))
    example = example_config_path(root)
    if example.exists():
        with example.open("rb") as handle:
            return deep_merge(DEFAULT_CONFIG, tomllib.load(handle))
    return deepcopy(DEFAULT_CONFIG)


def is_git_repo(start: Path) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(start),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def find_project_root(start: Path, *, prefer_git: bool = True) -> Path:
    start = start.resolve()
    if prefer_git and is_git_repo(start):
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return Path(completed.stdout.strip()).resolve()
    return start


def split_command(command: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command if str(part)]
    if not command:
        return []
    return shlex.split(command, posix=os.name != "nt")


def configured_worktree_root(root: Path, cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("workflow", {}).get("worktree_root") or "../.ai-flow-worktrees")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def allowlisted_test_commands(cfg: dict[str, Any]) -> set[str]:
    values = cfg.get("commands_allowlist", {}).get("test", [])
    return {str(value).strip() for value in values if str(value).strip()}
