from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from .claude_planner import run_claude_planner, run_mock_planner
from .claude_reviewer import run_claude_reviewer
from .codex_planner import run_codex_planner
from .codex_reviewer import run_codex_reviewer, run_mock_reviewer
from .gemini_planner import run_gemini_planner
from .gemini_reviewer import run_gemini_reviewer
from .mock_writer import run_mock_writer
from .reasonix_writer import run_reasonix_writer
from ..artifacts import append_text
from ..config import split_command
from ..errors import AiFlowError
from ..runner import merged_env, redact
from ..usage import metrics_from_text, with_usage

# ---------------------------------------------------------------------------
# Role constants used as capability flags.
# ---------------------------------------------------------------------------

ROLE_PLAN = "plan"
ROLE_WRITE = "write"
ROLE_REVIEW = "review"
ROLE_FIX = "fix"

# ---------------------------------------------------------------------------
# Per-role registries — these are the actual dispatch tables used by service.py.
# Each maps a provider id string to a callable.  The unified PROVIDERS dict
# below declares which provider ids are valid for which roles (for validation),
# but the per-role registries are the authoritative callable lookup.
# ---------------------------------------------------------------------------

PLANNERS: dict[str, Callable[..., Any]] = {
    "claude_cli": run_claude_planner,
    "codex_cli": run_codex_planner,
    "gemini_cli": run_gemini_planner,
    "mock": run_mock_planner,
}

WRITERS: dict[str, Callable[..., Any]] = {
    "reasonix_cli": run_reasonix_writer,
    "mock": run_mock_writer,
}

REVIEWERS: dict[str, Callable[..., Any]] = {
    "claude_cli": run_claude_reviewer,
    "codex_cli": run_codex_reviewer,
    "gemini_cli": run_gemini_reviewer,
    "mock": run_mock_reviewer,
}

FIXERS: dict[str, Callable[..., Any]] = {
    "reasonix_cli": run_reasonix_writer,
    "mock": run_mock_writer,
}

# ---------------------------------------------------------------------------
# Unified PROVIDERS role-capability mask — used by resolve_phase to validate
# that a provider advertises the required role.  A provider id may appear in
# multiple per-role registries with different callables (e.g. codex_cli is in
# both PLANNERS and REVIEWERS).  The mask simply records which roles the id is
# registered for.
# ---------------------------------------------------------------------------

ProviderRoles = set[str]

PROVIDERS: dict[str, ProviderRoles] = {
    "claude_cli": {ROLE_PLAN, ROLE_REVIEW},
    "codex_cli": {ROLE_PLAN, ROLE_REVIEW},
    "gemini_cli": {ROLE_PLAN, ROLE_REVIEW},
    "reasonix_cli": {ROLE_WRITE, ROLE_FIX},
    "mock": {ROLE_PLAN, ROLE_WRITE, ROLE_REVIEW, ROLE_FIX},
}


BUILTIN_PROVIDER_IDS = set(PROVIDERS)
_BUILTIN_PLANNERS = dict(PLANNERS)
_BUILTIN_WRITERS = dict(WRITERS)
_BUILTIN_REVIEWERS = dict(REVIEWERS)
_BUILTIN_FIXERS = dict(FIXERS)
_BUILTIN_PROVIDERS = {provider_id: set(roles) for provider_id, roles in PROVIDERS.items()}


def _collect_provider_ids(*registries: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for registry in registries:
        ids.update(registry.keys())
    return ids


_ALL_KNOWN = _collect_provider_ids(PLANNERS, WRITERS, REVIEWERS, FIXERS)
for _pid in _ALL_KNOWN:
    PROVIDERS.setdefault(_pid, set())


# ---------------------------------------------------------------------------
# Helpers for phase resolution and validation.
# ---------------------------------------------------------------------------

_ROLE_BY_PHASE: dict[str, str] = {
    "plan": ROLE_PLAN,
    "write": ROLE_WRITE,
    "review": ROLE_REVIEW,
    "fix": ROLE_FIX,
}


def provider_roles(provider_id: str) -> set[str]:
    """Return the capability roles advertised by *provider_id*."""
    roles = PROVIDERS.get(provider_id)
    if roles is None:
        raise KeyError(f"Unknown provider id: {provider_id}")
    return roles


def provider_supports_phase(provider_id: str, phase: str) -> bool:
    """Return True if *provider_id* advertises the role needed by *phase*."""
    role = _ROLE_BY_PHASE.get(phase)
    if role is None:
        return True  # non-model phases (test, apply) pass through
    return role in provider_roles(provider_id)


def register_custom_providers(config: dict[str, Any]) -> None:
    """Register minimal TOML-defined CLI providers for this process."""
    reset_custom_providers()
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        return
    for provider_id, provider_cfg in providers.items():
        if provider_id in BUILTIN_PROVIDER_IDS:
            raise AiFlowError(
                f"Custom provider id collides with built-in provider: {provider_id}",
                stage="config",
            )
        if not isinstance(provider_cfg, dict):
            raise AiFlowError(f"Provider {provider_id} must be a table.", stage="config")
        roles = {str(role) for role in provider_cfg.get("roles", [])}
        if not roles:
            raise AiFlowError(f"Provider {provider_id} must declare roles.", stage="config")
        invalid = roles - {ROLE_PLAN, ROLE_WRITE, ROLE_REVIEW, ROLE_FIX}
        if invalid:
            raise AiFlowError(
                f"Provider {provider_id} has invalid roles: {', '.join(sorted(invalid))}",
                stage="config",
            )
        PROVIDERS[provider_id] = roles
        if ROLE_PLAN in roles:
            PLANNERS[provider_id] = _custom_plan_runner(provider_id, provider_cfg)
        custom_writer = _custom_writer_runner(provider_id, provider_cfg) if roles & {ROLE_WRITE, ROLE_FIX} else None
        if ROLE_WRITE in roles and custom_writer is not None:
            WRITERS[provider_id] = custom_writer
        if ROLE_REVIEW in roles:
            REVIEWERS[provider_id] = _custom_review_runner(provider_id, provider_cfg)
        if ROLE_FIX in roles and custom_writer is not None:
            FIXERS[provider_id] = custom_writer


def reset_custom_providers() -> None:
    """Remove project-scoped custom providers without overwriting built-in entries."""
    for registry, builtins in (
        (PLANNERS, _BUILTIN_PLANNERS),
        (WRITERS, _BUILTIN_WRITERS),
        (REVIEWERS, _BUILTIN_REVIEWERS),
        (FIXERS, _BUILTIN_FIXERS),
    ):
        for provider_id in list(registry):
            if provider_id not in builtins:
                del registry[provider_id]
        for provider_id, runner in builtins.items():
            registry.setdefault(provider_id, runner)
    for provider_id in list(PROVIDERS):
        if provider_id not in _BUILTIN_PROVIDERS:
            del PROVIDERS[provider_id]
    for provider_id, roles in _BUILTIN_PROVIDERS.items():
        PROVIDERS.setdefault(provider_id, set(roles))


def _provider_argv(provider_cfg: dict[str, Any]) -> list[str]:
    command = split_command(provider_cfg.get("command", ""))
    if not command:
        raise AiFlowError("Custom provider command is empty.", stage="config")
    args = provider_cfg.get("args", [])
    if isinstance(args, str):
        args = split_command(args)
    return [*command, *[str(arg) for arg in args]]


def _run_custom_cli(
    *,
    provider_id: str,
    provider_cfg: dict[str, Any],
    prompt: str,
    cwd: Path,
    log_path: Path,
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    argv = _provider_argv(provider_cfg)
    prompt_mode = str(provider_cfg.get("prompt_mode", "stdin"))
    input_text: str | None = None
    if prompt_mode == "stdin":
        input_text = prompt
    elif prompt_mode == "arg":
        argv.append(prompt)
    elif prompt_mode == "file":
        prompt_file = log_path.parent / f"{provider_id}-prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8", newline="\n")
        argv.append(str(prompt_file))
    else:
        raise AiFlowError(
            f"Custom provider {provider_id} has unsupported prompt_mode: {prompt_mode}",
            stage="config",
        )
    effective_env = merged_env(env)
    append_text(log_path, f"\n## Custom provider {provider_id}\n\n")
    append_text(log_path, f"cwd: {cwd}\ncommand: {redact(' '.join(argv), effective_env)}\n\n")
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=effective_env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AiFlowError(
            f"Custom provider {provider_id} command was not found: {argv[0]}",
            stage="config",
        ) from exc
    append_text(
        log_path,
        "\n".join(
            [
                f"exit_code: {completed.returncode}",
                "",
                "### stdout",
                "",
                redact(completed.stdout or "", effective_env).rstrip(),
                "",
                "### stderr",
                "",
                redact(completed.stderr or "", effective_env).rstrip(),
                "",
            ]
        ),
    )
    if completed.returncode != 0:
        raise AiFlowError(
            f"Custom provider {provider_id} failed with exit code {completed.returncode}.",
            stage="config",
        )
    return with_usage(completed.stdout or "", metrics_from_text(completed.stdout or ""))


def _custom_plan_runner(provider_id: str, provider_cfg: dict[str, Any]) -> Callable[..., str]:
    def run_custom_plan(
        *,
        task: str,
        context: str,
        config: dict[str, Any],
        cwd: Path,
        log_path: Path,
        command_key: str = "",
        timeout: int = 900,
        env: dict[str, str] | None = None,
        phase: str = "write",
    ) -> str:
        prompt = "\n\n".join(["# User Task", task, "# Repository Context", context])
        return _run_custom_cli(
            provider_id=provider_id,
            provider_cfg=provider_cfg,
            prompt=prompt,
            cwd=cwd,
            log_path=log_path,
            timeout=timeout,
            env=env,
        )
    return run_custom_plan


def _custom_writer_runner(provider_id: str, provider_cfg: dict[str, Any]) -> Callable[..., str]:
    def run_custom_writer(
        *,
        prompt: str,
        config: dict[str, Any],
        cwd: Path,
        log_path: Path,
        command_key: str = "",
        timeout: int = 900,
        env: dict[str, str] | None = None,
        phase: str = "write",
    ) -> str:
        output = _run_custom_cli(
            provider_id=provider_id,
            provider_cfg=provider_cfg,
            prompt=prompt,
            cwd=cwd,
            log_path=log_path,
            timeout=timeout,
            env=env,
        )
        contract = str(provider_cfg.get("output_contract", "writer_diff"))
        if contract == "worktree_diff":
            return "\n".join(
                [
                    "BEGIN_WRITER_SUMMARY",
                    output.strip() or f"Custom provider {provider_id} edited the worktree.",
                    "END_WRITER_SUMMARY",
                    "",
                ]
            )
        return output
    return run_custom_writer


def _custom_review_runner(provider_id: str, provider_cfg: dict[str, Any]) -> Callable[..., str]:
    def run_custom_review(
        *,
        prompt: str,
        config: dict[str, Any],
        cwd: Path,
        log_path: Path,
        command_key: str = "",
        timeout: int = 900,
        env: dict[str, str] | None = None,
        phase: str = "review",
    ) -> str:
        return _run_custom_cli(
            provider_id=provider_id,
            provider_cfg=provider_cfg,
            prompt=prompt,
            cwd=cwd,
            log_path=log_path,
            timeout=timeout,
            env=env,
        )
    return run_custom_review


# ---------------------------------------------------------------------------
# Legacy per-function exports — kept for backward-compatible direct imports.
# ---------------------------------------------------------------------------

__all__ = [
    "PLANNERS",
    "WRITERS",
    "REVIEWERS",
    "FIXERS",
    "PROVIDERS",
    "ROLE_PLAN",
    "ROLE_WRITE",
    "ROLE_REVIEW",
    "ROLE_FIX",
    "provider_roles",
    "provider_supports_phase",
    "register_custom_providers",
    "reset_custom_providers",
    "run_claude_planner",
    "run_claude_reviewer",
    "run_codex_planner",
    "run_gemini_planner",
    "run_gemini_reviewer",
    "run_mock_planner",
    "run_reasonix_writer",
    "run_mock_writer",
    "run_codex_reviewer",
    "run_mock_reviewer",
]
