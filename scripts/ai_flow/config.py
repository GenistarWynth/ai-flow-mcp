from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

from .artifacts import ai_dir


EXAMPLE_CONFIG_NAME = "patchbay.example.toml"
CONFIG_NAME = "patchbay.toml"
LEGACY_EXAMPLE_CONFIG_NAME = "ai-flow.example.toml"
LEGACY_CONFIG_NAME = "ai-flow.toml"


DEFAULT_CONFIG: dict[str, Any] = {
    "models": {
        "planner": "claude-opus-4-7",
        "writer": "deepseek-v4-pro",
        "reviewer": "gpt-5.5",
    },
    "commands": {
        "claude": "claude",
        "codex": "codex",
        "gemini": "gemini",
        "reasonix": "",
    },
    "writer": {
        "provider": "reasonix_cli",
        "max_context_files": 30,
        "max_patch_attempts": 3,
        "max_repair_iterations": 2,
    },
    "workflow": {
        "require_plan_approval": True,
        "default_branch_prefix": "patchbay",
        "worktree_root": "../.patchbay-worktrees",
        "fail_on_dirty_workspace": True,
        "apply_to_current_workspace_only_after_review_pass": True,
        "allow_apply_without_tests": False,
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
    "profiles": {
        "economy": {
            "provider": "reasonix_cli",
            "model": "deepseek-v4-pro",
            "command_key": "reasonix",
            "label": "Reasonix/DeepSeek",
        },
    },
    "phases": {
        "plan": {
            "provider": "",
            "model": "",
            "command_key": "",
            "env": {},
            "timeout": 900,
        },
        "write": {
            "provider": "",
            "model": "",
            "command_key": "",
            "env": {},
            "timeout": 900,
        },
        "review": {
            "provider": "",
            "model": "",
            "command_key": "",
            "env": {},
            "timeout": 900,
        },
        "fix": {
            "provider": "",
            "model": "",
            "command_key": "",
            "env": {},
            "timeout": 900,
        },
        "test": {
            "provider": "",
            "model": "",
            "command_key": "",
            "env": {},
            "timeout": 900,
        },
        "apply": {
            "provider": "",
            "model": "",
            "command_key": "",
            "env": {},
            "timeout": 900,
        },
    },
}


def economy_target(cfg: dict[str, Any]) -> dict[str, str]:
    profiles = cfg.get("profiles", {}) if isinstance(cfg.get("profiles"), dict) else {}
    raw = profiles.get("economy", {}) if isinstance(profiles.get("economy"), dict) else {}
    provider = str(raw.get("provider") or "reasonix_cli").strip()
    model = str(raw.get("model") or "").strip()
    if not model and provider == "reasonix_cli":
        model = "deepseek-v4-pro"
    command_key = str(raw.get("command_key") or "").strip()
    if not command_key:
        command_key = _PROVIDER_COMMAND_KEY_DEFAULTS.get(provider, "")
    label = str(raw.get("label") or "").strip()
    if not label:
        label = route_label({"provider": provider, "model": model, "command_key": command_key})
    return {
        "provider": provider,
        "model": model,
        "command_key": command_key,
        "label": label,
    }


def route_label(route: dict[str, Any]) -> str:
    provider = str(route.get("provider") or "").strip()
    model = str(route.get("model") or "").strip()
    command_key = str(route.get("command_key") or "").strip()
    if provider and model:
        return f"{provider}/{model}"
    if provider and command_key:
        return f"{provider}/{command_key}"
    return provider or model or "configured economy target"


def route_matches_economy(route: dict[str, Any], target: dict[str, Any]) -> bool:
    provider = str(route.get("provider") or "").strip()
    model = str(route.get("model") or "").strip()
    target_provider = str(target.get("provider") or "").strip()
    target_model = str(target.get("model") or "").strip()
    if not target_provider or provider != target_provider:
        return False
    return not target_model or model == target_model


def route_command_status(cfg: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    provider = str(route.get("provider") or "").strip()
    command_key = str(route.get("command_key") or "").strip()
    if provider == "reasonix_cli":
        commands = cfg.get("commands", {}) if isinstance(cfg.get("commands"), dict) else {}
        key = command_key or "reasonix"
        return _command_status(
            provider=provider,
            command_key=command_key,
            command_value=commands.get(key, ""),
            source=f"commands.{key}",
            target_label="Reasonix",
        )

    providers = cfg.get("providers", {}) if isinstance(cfg.get("providers"), dict) else {}
    provider_cfg = providers.get(provider)
    if not isinstance(provider_cfg, dict) or "command" not in provider_cfg:
        return {
            "required": False,
            "ready": True,
            "provider": provider,
            "command_key": command_key,
        }
    return _command_status(
        provider=provider,
        command_key=command_key,
        command_value=provider_cfg.get("command", ""),
        source=f"providers.{provider}.command",
        target_label=route_label(route),
    )


def _command_status(
    *,
    provider: str,
    command_key: str,
    command_value: Any,
    source: str,
    target_label: str,
) -> dict[str, Any]:
    command = _display_command(command_value)
    try:
        parts = split_command(command_value)
    except ValueError as exc:
        return {
            "required": True,
            "ready": False,
            "status": "invalid",
            "provider": provider,
            "command_key": command_key,
            "command": command,
            "executable": "",
            "resolved": "",
            "source": source,
            "recommendation": f"Fix {source}: {exc}",
        }
    executable = parts[0] if parts else ""
    resolved = shutil.which(executable) if executable else None
    if not command:
        return {
            "required": True,
            "ready": False,
            "status": "missing_config",
            "provider": provider,
            "command_key": command_key,
            "command": command,
            "executable": executable,
            "resolved": "",
            "source": source,
            "recommendation": f"Set {source} to the {target_label} executable.",
        }
    return {
        "required": True,
        "ready": bool(resolved),
        "status": "ready" if resolved else "not_found",
        "provider": provider,
        "command_key": command_key,
        "command": command,
        "executable": executable,
        "resolved": resolved or "",
        "source": source,
        "recommendation": ""
        if resolved
        else f"Install {target_label} or set {source} to its full executable path.",
    }


def _display_command(command: Any) -> str:
    if isinstance(command, (list, tuple)):
        return " ".join(str(part) for part in command if str(part))
    return str(command or "").strip()


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
            return _finalize_config(deep_merge(DEFAULT_CONFIG, tomllib.load(handle)))
    legacy_path = ai_dir(root) / LEGACY_CONFIG_NAME
    if legacy_path.exists():
        with legacy_path.open("rb") as handle:
            return _finalize_config(deep_merge(DEFAULT_CONFIG, tomllib.load(handle)))
    example = example_config_path(root)
    if example.exists():
        with example.open("rb") as handle:
            return _finalize_config(deep_merge(DEFAULT_CONFIG, tomllib.load(handle)))
    legacy_example = ai_dir(root) / LEGACY_EXAMPLE_CONFIG_NAME
    if legacy_example.exists():
        with legacy_example.open("rb") as handle:
            return _finalize_config(deep_merge(DEFAULT_CONFIG, tomllib.load(handle)))
    return _finalize_config(deepcopy(DEFAULT_CONFIG))


def _finalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    from .adapters import register_custom_providers

    register_custom_providers(cfg)
    return cfg


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
    return [_strip_wrapping_quotes(part) for part in shlex.split(command, posix=os.name != "nt")]


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def configured_worktree_root(root: Path, cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("workflow", {}).get("worktree_root") or "../.patchbay-worktrees")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def allowlisted_test_commands(cfg: dict[str, Any]) -> set[str]:
    values = cfg.get("commands_allowlist", {}).get("test", [])
    return {str(value).strip() for value in values if str(value).strip()}


# ---------------------------------------------------------------------------
# Per-phase resolver: user [phases.<x>] > legacy [models]/[commands]/[writer] > DEFAULT_CONFIG
# ---------------------------------------------------------------------------

_PHASE_PROVIDER_DEFAULTS: dict[str, str] = {
    "plan": "claude_cli",
    "write": "reasonix_cli",
    "review": "codex_cli",
    "fix": "",
    "test": "",
    "apply": "",
}

_PHASE_COMMAND_KEY_DEFAULTS: dict[str, str] = {
    "plan": "claude",
    "write": "reasonix",
    "review": "codex",
    "fix": "reasonix",
    "test": "",
    "apply": "",
}

_PROVIDER_COMMAND_KEY_DEFAULTS: dict[str, str] = {
    "claude_cli": "claude",
    "codex_cli": "codex",
    "gemini_cli": "gemini",
    "reasonix_cli": "reasonix",
    "mock": "",
}

_PROVIDER_MODEL_DEFAULTS: dict[str, str] = {
    "claude_cli": "claude-opus-4-7",
    "codex_cli": "gpt-5.5",
    "gemini_cli": "gemini-2.5-pro",
    "reasonix_cli": "deepseek-v4-pro",
    "mock": "mock",
}


def resolve_phase(cfg: dict[str, Any], phase: str) -> dict[str, Any]:
    """Return effective {provider, model, command_key, env, timeout} for *phase*.

    Precedence:
    1. ``[phases.<phase>]`` in the user config (already deep-merged over DEFAULT_CONFIG).
    2. Legacy keys: ``[models]``, ``[commands]``, ``[writer].provider``.
    3. Hard-coded per-phase defaults.

    The ``fix`` phase defaults its provider and model to whatever *write* resolves to.
    """
    phases_cfg = cfg.get("phases", {})
    phase_cfg = dict(phases_cfg.get(phase, {}))
    inherited_write_phase = resolve_phase(cfg, "write") if phase == "fix" else None

    # -- provider --
    provider = str(phase_cfg.get("provider", "")).strip()
    if not provider:
        if phase == "write":
            provider = str(cfg.get("writer", {}).get("provider", "reasonix_cli")).strip()
        elif phase == "fix":
            provider = str(inherited_write_phase.get("provider", "") if inherited_write_phase else "")
        else:
            provider = _PHASE_PROVIDER_DEFAULTS.get(phase, "")
    phase_cfg["provider"] = provider

    # -- model --
    model = str(phase_cfg.get("model", "")).strip()
    if not model:
        if phase == "plan":
            if provider == _PHASE_PROVIDER_DEFAULTS["plan"]:
                model = str(cfg.get("models", {}).get("planner", "claude-opus-4-7"))
            else:
                model = _PROVIDER_MODEL_DEFAULTS.get(provider, "")
        elif phase == "write":
            legacy_provider = str(cfg.get("writer", {}).get("provider", "reasonix_cli")).strip()
            if provider == legacy_provider:
                model = str(cfg.get("models", {}).get("writer", "deepseek-v4-pro"))
            else:
                model = _PROVIDER_MODEL_DEFAULTS.get(provider, "")
        elif phase == "fix":
            model = str(inherited_write_phase.get("model", "") if inherited_write_phase else "")
        elif phase == "review":
            if provider == _PHASE_PROVIDER_DEFAULTS["review"]:
                model = str(cfg.get("models", {}).get("reviewer", "gpt-5.5"))
            else:
                model = _PROVIDER_MODEL_DEFAULTS.get(provider, "")
    phase_cfg["model"] = model

    # -- command_key --
    command = str(phase_cfg.get("command", "")).strip()
    command_key = str(phase_cfg.get("command_key", "")).strip()
    if command:
        command_key = f"phase_{phase}"
        cfg.setdefault("commands", {})[command_key] = command
    if not command_key:
        if phase == "fix":
            command_key = str(inherited_write_phase.get("command_key", "") if inherited_write_phase else "")
        if not command_key:
            command_key = _PROVIDER_COMMAND_KEY_DEFAULTS.get(provider, "")
        if not command_key:
            command_key = _PHASE_COMMAND_KEY_DEFAULTS.get(phase, "")
    phase_cfg["command_key"] = command_key

    raw_env = phase_cfg.get("env", {})
    if phase == "fix" and isinstance(raw_env, dict) and not raw_env and inherited_write_phase:
        merged_env = dict(inherited_write_phase.get("env") or os.environ)
    else:
        merged_env = dict(os.environ)
    if isinstance(raw_env, dict) and not (phase == "fix" and not raw_env and inherited_write_phase):
        merged_env.update({str(key): str(value) for key, value in raw_env.items()})
    phase_cfg["env"] = merged_env
    if (
        phase == "fix"
        and inherited_write_phase
        and phase_cfg.get("timeout", DEFAULT_CONFIG["phases"]["fix"]["timeout"])
        == DEFAULT_CONFIG["phases"]["fix"]["timeout"]
    ):
        phase_cfg["timeout"] = inherited_write_phase.get("timeout", 900)
    else:
        phase_cfg.setdefault("timeout", 900)

    # -- validate provider supports this phase role --
    if provider:
        from .adapters import provider_supports_phase as _check_role
        if not _check_role(provider, phase):
            from .errors import AiFlowError
            raise AiFlowError(
                f"Provider '{provider}' does not support the '{phase}' phase role. "
                f"Check that the provider advertises the required capability.",
                stage=phase,
                suggested_next_action=f"Pick a provider that supports the '{phase}' role or add a [providers.<id>] entry.",
            )

    return phase_cfg
