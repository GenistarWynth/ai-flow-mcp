from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from . import git_utils
from .adapters import (
    PLANNERS,
    REVIEWERS,
    WRITERS,
    run_codex_reviewer,
    run_mock_planner,
    run_mock_reviewer,
    run_mock_writer,
    run_reasonix_writer,
)
from .artifacts import (
    append_text,
    ensure_layout,
    list_run_artifacts,
    now_iso,
    runs_dir,
    new_run_id,
    read_json,
    read_text,
    run_dir as artifact_run_dir,
    write_json,
    write_text,
)
from .config import (
    allowlisted_test_commands,
    configured_worktree_root,
    config_path,
    example_config_path,
    find_project_root,
    load_config,
    resolve_phase,
)
from .context import build_context
from .errors import AiFlowError, GitError, SafetyError, StateError
from .events import append_event, event_count, latest_event, list_events
from .handoff import build_handoff_context
from .parsing import parse_planner_output, parse_writer_output, review_verdict
from .plan_schema import validate_plan_json
from .runner import run_logged
from .safety import ensure_command_allowed, paths_from_patch, validate_patch_safety
from .state import (
    APPROVED,
    APPLIED,
    FAILED,
    FIXING,
    IMPLEMENTED,
    IMPLEMENTING,
    NEW,
    PLANNED,
    REVIEWED_CHANGES_REQUESTED,
    REVIEWED_PASS,
    REVIEWING,
    TESTED,
    TESTING,
    create_status,
    load_status,
    mark_failed,
    require_status,
    set_status,
)
from .trace import list_trace, trace_count
from .usage import merge_usage_metrics, metrics_from_output


TERMINAL_STATUSES = {APPLIED, FAILED, REVIEWED_PASS, REVIEWED_CHANGES_REQUESTED}
RUN_LOCK_FILE = "RUN.lock"
RESERVED_RUN_ENV = "PATCHBAY_RESERVED_RUN_ID"
INHERITED_LOCK_ENV = "PATCHBAY_INHERITED_LOCK"
LOCK_TOKEN_ENV = "PATCHBAY_LOCK_TOKEN"
ECONOMY_PROVIDER = "reasonix_cli"
ECONOMY_MODEL = "deepseek-v4-pro"


def resolve_root(cwd: Path) -> Path:
    return find_project_root(cwd, prefer_git=True)


def _run_dir(root: Path, run_id: str) -> Path:
    return artifact_run_dir(root, run_id)


def _load_run(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = _run_dir(root, run_id)
    return path, load_status(path)


def _run_path_for_read(root: Path, run_id: str) -> Path:
    run_path = _run_dir(root, run_id)
    if (run_path / "STATUS.json").exists() or _job_path(run_path).exists():
        return run_path
    load_status(run_path)
    return run_path


def _lock_path(run_path: Path) -> Path:
    return run_path / RUN_LOCK_FILE


def _job_path(run_path: Path) -> Path:
    return run_path / "JOB.json"


def _record_job(run_path: Path, data: dict[str, Any]) -> None:
    write_json(_job_path(run_path), data)


def _patchbay_command(root: Path, phase: str) -> list[str]:
    repo_script = root / "scripts" / "patchbay"
    if repo_script.exists():
        return [sys.executable, str(repo_script), phase]
    source_script = Path(__file__).resolve().parents[1] / "patchbay"
    if source_script.exists():
        return [sys.executable, str(source_script), phase]
    return [sys.executable, "-m", "ai_flow.cli", phase]


def _background_spawn_command(phase: str, phase_args: list[str]) -> list[str]:
    runner = """
import os
import sys
from pathlib import Path

root = Path(os.environ["PATCHBAY_BACKGROUND_ROOT"])
source_scripts = Path(os.environ.get("PATCHBAY_BACKGROUND_SOURCE_SCRIPTS", ""))
for candidate in (root / "scripts", source_scripts):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from ai_flow.cli import main
    raise SystemExit(main(sys.argv[1:]))
finally:
    run_dir = os.environ.get("PATCHBAY_BACKGROUND_RUN_DIR")
    token = os.environ.get("PATCHBAY_LOCK_TOKEN")
    phase = os.environ.get("PATCHBAY_BACKGROUND_PHASE", "")
    if run_dir and token:
        lock_path = Path(run_dir) / "RUN.lock"
        try:
            lines = lock_path.read_text(encoding="utf-8").splitlines()
            if len(lines) >= 2 and lines[0] == phase and lines[1] == token:
                lock_path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
""".strip()
    return [sys.executable, "-c", runner, phase, *phase_args]


def _acquire_lock(run_path: Path, phase: str, *, token: str | None = None) -> None:
    path = _lock_path(run_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        raise StateError(
            f"Run is already busy: {read_text(path, default='').strip()}",
            stage=phase,
            suggested_next_action="Wait for the active phase to finish, then poll events/status.",
        )
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(phase + "\n")
        if token:
            handle.write(token + "\n")


def _begin_phase_lock(run_path: Path, phase: str) -> bool:
    inherited = os.environ.get(INHERITED_LOCK_ENV)
    if inherited == phase and _lock_path(run_path).exists():
        return True
    _acquire_lock(run_path, phase)
    return True


def _release_lock(run_path: Path, *, token: str | None = None) -> None:
    path = _lock_path(run_path)
    if not path.exists():
        return
    if token:
        lines = read_text(path, default="").splitlines()
        if len(lines) < 2 or lines[1] != token:
            return
    if path.exists():
        path.unlink()


def start_background_phase(
    cwd: Path,
    phase: str,
    *,
    run_id: str | None = None,
    task: str | None = None,
    mock: bool = False,
) -> dict[str, Any]:
    root = resolve_root(cwd)
    ensure_layout(root)
    phase_args: list[str] = []
    job_started = time.time()
    run_path: Path
    parent_holds_lock = False
    lock_token = uuid.uuid4().hex
    if phase == "plan":
        if not task:
            raise AiFlowError("Background plan requires task.", stage="plan")
        explicit_run_id = run_id is not None
        if explicit_run_id:
            run_path = _reserve_explicit_run_dir(root, run_id)
        else:
            run_id, run_path = _reserve_new_run_dir(root, new_run_id(task))
        _acquire_lock(run_path, phase, token=lock_token)
        parent_holds_lock = True
        write_text(run_path / "events.jsonl", "")
        write_text(run_path / "trace.jsonl", "")
        phase_args.extend(["--task", task, "--run-id", run_id])
        if mock:
            phase_args.append("--mock")
    else:
        if not run_id:
            raise AiFlowError(f"Background {phase} requires run_id.", stage=phase)
        run_path, _ = _load_run(root, run_id)
        _acquire_lock(run_path, phase, token=lock_token)
        parent_holds_lock = True
        phase_args.append(run_id)
        if mock and phase in {"write", "review", "fix"}:
            phase_args.append("--mock")
    command = _background_spawn_command(phase, phase_args)
    env = dict(os.environ)
    env[INHERITED_LOCK_ENV] = phase
    env[LOCK_TOKEN_ENV] = lock_token
    env["PATCHBAY_BACKGROUND_ROOT"] = str(root)
    env["PATCHBAY_BACKGROUND_RUN_DIR"] = str(run_path)
    env["PATCHBAY_BACKGROUND_PHASE"] = phase
    env["PATCHBAY_BACKGROUND_SOURCE_SCRIPTS"] = str(Path(__file__).resolve().parents[1])
    if phase == "plan" and run_id:
        env[RESERVED_RUN_ENV] = run_id
    pending_job = {
        "background": True,
        "phase": phase,
        "pid": None,
        "run_id": run_id or "pending",
        "task": task or "",
        "command": command,
        "started_at": now_iso(),
        "started_at_epoch": job_started,
        "root": str(root),
        "run_dir": str(run_path),
        "events_path": str(run_path / "events.jsonl"),
        "trace_path": str(run_path / "trace.jsonl"),
    }
    _record_job(run_path, pending_job)
    try:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except Exception:
        if parent_holds_lock:
            _release_lock(run_path, token=lock_token)
        raise
    job_data = {
        **pending_job,
        "pid": process.pid,
    }
    early_exit = process.poll()
    if early_exit is not None and parent_holds_lock:
        _release_lock(run_path, token=lock_token)
        job_data["exit_code"] = early_exit
        parent_holds_lock = False
    _record_job(run_path, job_data)
    return job_data


def _plan_may_use_existing_run(run_path: Path, run_id: str) -> bool:
    return (
        os.environ.get(RESERVED_RUN_ENV) == run_id
        and os.environ.get(INHERITED_LOCK_ENV) == "plan"
        and _lock_path(run_path).exists()
        and not (run_path / "STATUS.json").exists()
    )


def _raise_run_exists(run_id: str) -> None:
    raise StateError(
        f"Run already exists: {run_id}",
        stage="plan",
        suggested_next_action="Choose a new run id or inspect the existing run before continuing.",
    )


def _reserve_new_run_dir(root: Path, base_run_id: str) -> tuple[str, Path]:
    suffix = 1
    while True:
        candidate = base_run_id if suffix == 1 else f"{base_run_id}-{suffix}"
        run_path = _run_dir(root, candidate)
        try:
            run_path.mkdir(parents=True, exist_ok=False)
            return candidate, run_path
        except FileExistsError:
            suffix += 1


def _reserve_explicit_run_dir(root: Path, run_id: str) -> Path:
    run_path = _run_dir(root, run_id)
    try:
        run_path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        _raise_run_exists(run_id)
    return run_path


def _base_commit(root: Path) -> str | None:
    if not git_utils.is_repo(root):
        raise GitError(
            "Patchbay requires a git repository so runs can record BASE_COMMIT and create worktrees.",
            stage="plan",
            suggested_next_action="Run Patchbay inside a git repository.",
        )
    commit = git_utils.current_commit(root)
    if not commit:
        raise GitError(
            "Could not resolve HEAD for BASE_COMMIT.",
            stage="plan",
            suggested_next_action="Create an initial commit before running Patchbay.",
        )
    return commit


def _selected_test_commands(root: Path, cfg: dict[str, Any], plan: dict[str, Any], test_phase: dict[str, Any] | None = None) -> list[str]:
    if test_phase:
        phase_commands = [str(command).strip() for command in test_phase.get("commands", []) if str(command).strip()]
        if phase_commands:
            return phase_commands
    plan_commands: list[str] = []
    for key in ("test_commands", "lint_commands", "typecheck_commands"):
        plan_commands.extend(str(command).strip() for command in plan.get(key, []) if str(command).strip())
    if plan_commands:
        return plan_commands
    configured = cfg.get("test", {}).get("commands", [])
    configured_commands = [str(command).strip() for command in configured if str(command).strip()]
    if configured_commands:
        return configured_commands
    if (root / "package.json").exists():
        return [command for command in ("npm test", "npm run lint", "npm run typecheck") if command in allowlisted_test_commands(cfg)]
    if any(root.glob("pyproject.toml")) or any(root.glob("pytest.ini")) or (root / "tests").exists():
        return ["pytest -q"] if "pytest -q" in allowlisted_test_commands(cfg) else []
    if (root / "go.mod").exists() and "go test ./..." in allowlisted_test_commands(cfg):
        return ["go test ./..."]
    if (root / "Cargo.toml").exists() and "cargo test" in allowlisted_test_commands(cfg):
        return ["cargo test"]
    return []


def _affected_file_context(root: Path, plan: dict[str, Any], extra_files: list[str] | None = None) -> str:
    paths: list[str] = []
    for item in plan.get("affected_files", []):
        if isinstance(item, dict) and item.get("path"):
            paths.append(str(item["path"]))
    if extra_files:
        paths.extend(extra_files)
    seen: set[str] = set()
    lines = ["# Affected File Context", ""]
    for raw_path in paths:
        normalized = raw_path.replace("\\", "/")
        if normalized in seen:
            continue
        seen.add(normalized)
        candidate = root / normalized
        lines.extend([f"## {normalized}", ""])
        if not candidate.exists():
            lines.append("[File does not exist yet.]")
            lines.append("")
            continue
        if not candidate.is_file():
            lines.append("[Path is not a file.]")
            lines.append("")
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = "[Skipped: not UTF-8 text]"
        if len(text) > 8000:
            text = text[:8000] + "\n[Truncated]\n"
        lines.extend(["```", text.rstrip(), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def _writer_prompt(
    *,
    root: Path,
    run_path: Path,
    task: str,
    repair: bool = False,
    extra_files: list[str] | None = None,
) -> str:
    prompt_name = "repair.md" if repair else "writer.md"
    prompt_path = Path(__file__).resolve().parent / "prompts" / prompt_name
    plan = read_json(run_path / "plan.json")
    parts = [
        read_text(prompt_path).rstrip(),
        "# TASK.md",
        read_text(run_path / "TASK.md").rstrip(),
        "# PLAN.md",
        read_text(run_path / "PLAN.md").rstrip(),
        "# plan.json",
        json.dumps(plan, ensure_ascii=False, indent=2),
        _affected_file_context(root, plan, extra_files),
    ]
    if repair:
        parts.extend(
            [
                "# TEST.log",
                read_text(run_path / "TEST.log", default="").rstrip(),
                "# REVIEW.md",
                read_text(run_path / "REVIEW.md", default="").rstrip(),
                "# Current Diff",
                git_utils.diff(Path(load_status(run_path)["worktree_path"])).rstrip(),
            ]
        )
    return "\n\n".join(parts).rstrip() + "\n"


def _reasonix_agent_prompt(
    *,
    root: Path,
    run_path: Path,
    repair: bool = False,
) -> str:
    plan = read_json(run_path / "plan.json")
    parts = [
        "# Patchbay Reasonix Agent Task",
        "",
        "You are the implementation writer. Use your native filesystem tools to edit the isolated worktree.",
        "Implement only the approved plan. Do not emit a patch; Patchbay will capture the final git diff.",
        "Do not run tests or shell commands. Patchbay handles test, lint, typecheck, review, and apply stages.",
        "Do not modify `.git`, `.env*`, secret-like files, CI secrets, or files outside the worktree.",
        "# TASK.md",
        read_text(run_path / "TASK.md").rstrip(),
        "# PLAN.md",
        read_text(run_path / "PLAN.md").rstrip(),
        "# plan.json",
        json.dumps(plan, ensure_ascii=False, indent=2),
        _affected_file_context(root, plan),
    ]
    if repair:
        parts.extend(
            [
                "# TEST.log",
                read_text(run_path / "TEST.log", default="").rstrip(),
                "# REVIEW.md",
                read_text(run_path / "REVIEW.md", default="").rstrip(),
                "# Current Diff",
                git_utils.diff(Path(load_status(run_path)["worktree_path"])).rstrip(),
            ]
        )
    return "\n\n".join(parts).rstrip() + "\n"


def _phase_config(cfg: dict[str, Any], *, role: str, model: str | None) -> dict[str, Any]:
    phase_cfg = deepcopy(cfg)
    if model:
        phase_cfg.setdefault("models", {})[role] = model
    return phase_cfg


def _usage_event_kwargs(output: Any) -> dict[str, Any]:
    metrics = metrics_from_output(output)
    result: dict[str, Any] = {}
    token_usage = metrics.get("token_usage")
    if isinstance(token_usage, dict) and token_usage.get("known"):
        result["token_usage"] = {
            key: value
            for key, value in token_usage.items()
            if key != "known" and value is not None
        }
    cost = metrics.get("cost")
    if isinstance(cost, dict) and cost.get("known"):
        result["cost"] = {
            "currency": cost.get("currency") or "USD",
            "estimated_total": cost.get("estimated_total"),
        }
    return result


def _call_writer(
    *,
    root: Path,
    run_path: Path,
    cfg: dict[str, Any],
    mock: bool,
    repair: bool = False,
) -> tuple[str, str, dict[str, Any]]:
    status = load_status(run_path)
    task = str(status["task"])
    log_path = run_path / "writer.log"
    max_attempts = int(cfg.get("writer", {}).get("max_patch_attempts", 3))
    extra_files: list[str] = []
    raw = ""
    summary = ""
    usage_parts: list[dict[str, Any]] = []
    for attempt in range(max_attempts):
        write_phase = resolve_phase(cfg, "write" if not repair else "fix")
        adapter_cfg = _phase_config(cfg, role="writer", model=write_phase.get("model"))
        provider = write_phase["provider"]
        if (not mock) and provider == "reasonix_cli":
            prompt = _reasonix_agent_prompt(root=root, run_path=run_path, repair=repair)
        else:
            prompt = _writer_prompt(
                root=root,
                run_path=run_path,
                task=task,
                repair=repair,
                extra_files=extra_files,
            )
        append_text(log_path, f"\n## Writer attempt {attempt + 1}\n\n")
        p_command_key = write_phase.get("command_key", "reasonix")
        p_timeout = write_phase.get("timeout", 900)
        p_env = write_phase.get("env") or None
        if mock or provider == "mock":
            iteration = int(status.get("fix_iterations") or 0) if repair else 0
            raw = WRITERS["mock"](task=task, repair=repair, iteration=iteration)
        else:
            worktree = Path(status["worktree_path"])
            writer = WRITERS.get(provider)
            if writer is None:
                raise AiFlowError(
                    f"Unknown writer provider: {provider}",
                    stage="write",
                    suggested_next_action="Set [phases.write].provider or [writer].provider to reasonix_cli or mock.",
                )
            try:
                raw = writer(
                    prompt=prompt,
                    config=adapter_cfg,
                    cwd=worktree,
                    log_path=log_path,
                    command_key=p_command_key,
                    timeout=p_timeout,
                    env=p_env,
                    phase="fix" if repair else "write",
                )
                append_text(log_path, raw + "\n")
                usage_parts.append(metrics_from_output(raw))
                parsed = parse_writer_output(raw)
                summary = parsed.summary
                if parsed.diff:
                    return parsed.diff, summary, merge_usage_metrics(*usage_parts)
                git_utils.add_all(worktree)
                final_diff = git_utils.diff(worktree)
                if not final_diff.strip():
                    raise AiFlowError(f"{provider} did not produce a worktree diff.", stage="write")
                validate_patch_safety(final_diff)
                return final_diff, summary or f"{provider} edited the isolated worktree.", merge_usage_metrics(*usage_parts)
            except AiFlowError:
                if attempt < max_attempts - 1:
                    append_text(log_path, "\nWriter attempt failed; retrying.\n")
                    continue
                raise
        append_text(log_path, raw + "\n")
        usage_parts.append(metrics_from_output(raw))
        parsed = parse_writer_output(raw)
        summary = parsed.summary
        if parsed.needed_files:
            extra_files.extend(parsed.needed_files)
            continue
        if not parsed.diff:
            raise AiFlowError("Writer did not provide a diff.", stage="write")
        return parsed.diff, summary, merge_usage_metrics(*usage_parts)
    raise AiFlowError(
        "Writer requested more file context too many times.",
        stage="write",
        suggested_next_action="Narrow the task or increase writer.max_patch_attempts.",
    )


def _apply_writer_diff(worktree: Path, patch: str) -> str:
    validate_patch_safety(patch)
    git_utils.apply_diff(worktree, patch if patch.endswith("\n") else patch + "\n", recount=True)
    git_utils.add_paths(worktree, paths_from_patch(patch))
    final_diff = git_utils.diff(worktree)
    validate_patch_safety(final_diff)
    return final_diff


def _planned_paths(plan: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in plan.get("affected_files", []):
        if isinstance(item, dict) and item.get("path"):
            result.add(str(item["path"]).replace("\\", "/").strip())
    return result


def _unexpected_diff_paths(plan: dict[str, Any], diff_text: str) -> set[str]:
    planned = _planned_paths(plan)
    return {
        path
        for path in paths_from_patch(diff_text)
        if path not in planned
    }


def _validate_writer_scope(run_path: Path, final_diff: str, summary: str) -> None:
    plan = read_json(run_path / "plan.json")
    unexpected = _unexpected_diff_paths(plan, final_diff)
    if not unexpected:
        return
    explanation = "\n".join(
        [
            read_text(run_path / "IMPLEMENTATION.md", default=""),
            read_text(run_path / "FIXES.md", default=""),
            summary,
        ]
    )
    missing_explanation = [path for path in sorted(unexpected) if path not in explanation]
    if missing_explanation:
        raise SafetyError(
            "Writer modified files outside plan.json affected_files without explaining them in implementation artifacts: "
            + ", ".join(missing_explanation),
            stage="write",
            suggested_next_action="Update the plan or rerun writer with a clear explanation for extra files.",
        )


def _workspace_snapshot(root: Path) -> tuple[str, list[str]]:
    return git_utils.diff(root), git_utils.status_porcelain(root)


def _artifact_dirty_prefix(run_path: Path) -> str:
    return run_path.relative_to(Path(load_status(run_path)["repo_root"])).as_posix().rstrip("/") + "/"


def _assert_plan_read_only(root: Path, run_path: Path, before: tuple[str, list[str]]) -> None:
    after = _workspace_snapshot(root)
    if after[0] != before[0]:
        raise SafetyError("Planner modified tracked files in the workspace.", stage="plan")
    artifact_prefix = _artifact_dirty_prefix(run_path)
    dirty = [
        line
        for line in after[1]
        if line not in before[1] and not git_utils.dirty_path(line).startswith(artifact_prefix)
    ]
    if dirty:
        raise SafetyError(
            "Planner produced workspace changes outside run artifacts:\n" + "\n".join(dirty),
            stage="plan",
        )


def init_project(cwd: Path) -> dict[str, str]:
    root = resolve_root(cwd)
    ensure_layout(root)
    example = example_config_path(root)
    if not example.exists():
        write_text(example, EXAMPLE_TOML)
    docs_path = root / "docs" / "patchbay.md"
    if not docs_path.exists():
        write_text(docs_path, DOCS_MD)
    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        write_text(agents_path, AGENTS_MD)
    gitignore_path = root / ".gitignore"
    existing = read_text(gitignore_path, default="")
    additions = [
        ".ai/runs/",
        ".ai/logs/",
        ".ai/worktrees/",
        ".ai/patchbay.toml",
        ".ai/ai-flow.toml",
        ".patchbay-worktrees/",
        ".ai-flow-worktrees/",
    ]
    missing = [line for line in additions if line not in existing.splitlines()]
    if missing:
        suffix = "" if existing.endswith("\n") or not existing else "\n"
        write_text(gitignore_path, existing + suffix + "\n".join(missing) + "\n")
    return {
        "root": str(root),
        "example_config": str(example),
        "docs": str(docs_path),
        "agents": str(agents_path),
    }


def plan(cwd: Path, *, task: str, mock: bool = False, run_id: str | None = None) -> dict[str, str]:
    root = resolve_root(cwd)
    ensure_layout(root)
    cfg = load_config(root)
    explicit_run_id = run_id is not None
    if not explicit_run_id:
        run_id, run_path = _reserve_new_run_dir(root, new_run_id(task))
        reserved_run = False
    else:
        run_path = _run_dir(root, run_id)
        reserved_run = _plan_may_use_existing_run(run_path, run_id)
    if explicit_run_id and run_path.exists() and not reserved_run:
        _raise_run_exists(run_id)
    if not run_path.exists():
        run_path = _reserve_explicit_run_dir(root, run_id)
    lock_started = False
    try:
        _begin_phase_lock(run_path, "plan")
        lock_started = True
        base_commit = _base_commit(root)
        before_workspace = _workspace_snapshot(root)
        create_status(
            run_path,
            run_id=run_id,
            task=task,
            repo_root=root,
            config_path=config_path(root),
            base_commit=base_commit,
        )
        write_text(run_path / "TASK.md", task.rstrip() + "\n")
        write_text(run_path / "BASE_COMMIT", (base_commit or "") + "\n")
        write_text(run_path / "FIXES.md", "")
        max_context = int(cfg.get("writer", {}).get("max_context_files", 30))
        context = build_context(root, max_files=max_context)
        plan_phase = resolve_phase(cfg, "plan")
        plan_started = time.time()
        append_event(
            run_path,
            phase="plan",
            provider=plan_phase["provider"],
            model=plan_phase.get("model", ""),
            action="start",
            status="RUNNING",
            run_id=run_id,
            next_action="await plan completion",
        )
        adapter_cfg = _phase_config(cfg, role="planner", model=plan_phase.get("model"))
        if mock:
            raw = PLANNERS["mock"](task=task, context=context)
            write_text(run_path / "claude-planner.log", "mock planner used\n")
        else:
            planner = PLANNERS.get(plan_phase["provider"])
            if planner is None:
                raise AiFlowError(
                    f"Unknown plan provider: {plan_phase['provider']}",
                    stage="plan",
                    suggested_next_action="Set [phases.plan].provider to claude_cli, codex_cli, gemini_cli, or mock.",
                )
            raw = planner(
                task=task,
                context=context,
                config=adapter_cfg,
                cwd=root,
                log_path=run_path / "claude-planner.log",
                command_key=plan_phase.get("command_key", "claude"),
                timeout=plan_phase.get("timeout", 900),
                env=plan_phase.get("env") or None,
            )
        usage_kwargs = _usage_event_kwargs(raw)
        try:
            parsed = parse_planner_output(raw)
            validate_plan_json(parsed.plan_json)
            write_text(run_path / "PLAN.md", parsed.markdown)
            write_json(run_path / "plan.json", parsed.plan_json)
            _assert_plan_read_only(root, run_path, before_workspace)
        except Exception:
            _assert_plan_read_only(root, run_path, before_workspace)
            raise
        set_status(run_path, PLANNED)
        append_event(
            run_path,
            phase="plan",
            provider=plan_phase["provider"],
            model=plan_phase.get("model", ""),
            action="success",
            status="PLANNED",
            detail=str(parsed.plan_json.get("summary", "")),
            run_id=run_id,
            artifact_paths=["PLAN.md", "plan.json", "TASK.md", "BASE_COMMIT"],
            next_action="approve",
            duration_ms=int((time.time() - plan_started) * 1000),
            **usage_kwargs,
        )
        return {
            "run_id": run_id,
            "run_dir": str(run_path),
            "plan_path": str(run_path / "PLAN.md"),
            "summary": str(parsed.plan_json.get("summary", "")),
        }
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "plan")
        raise
    finally:
        if lock_started:
            _release_lock(run_path)


def approve(cwd: Path, run_id: str) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    require_status(status, {PLANNED}, "approve")
    approval = {
        "approved": True,
        "run_id": run_id,
        "approved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
    }
    write_json(run_path / "APPROVAL.json", approval)
    result = set_status(run_path, APPROVED)
    append_event(
        run_path,
        phase="approve",
        action="approve_granted",
        status="APPROVED",
        run_id=run_id,
        next_action="write",
    )
    return result


def write(cwd: Path, run_id: str, *, mock: bool = False) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    try:
        with git_utils.log_to(run_path / "git.log"):
            require_status(status, {APPROVED}, "write")
            _begin_phase_lock(run_path, "write")
            if not (run_path / "APPROVAL.json").exists():
                raise StateError("Missing APPROVAL.json.", stage="write")
            if not git_utils.is_repo(root):
                raise GitError(
                    "write requires a git repository because it creates an isolated worktree.",
                    stage="write",
                    suggested_next_action="Run Patchbay inside a git repository.",
                )
            cfg = load_config(root)
            write_phase = resolve_phase(cfg, "write")
            write_started = time.time()
            append_event(
                run_path,
                phase="write",
                provider=write_phase["provider"],
                model=write_phase.get("model", ""),
                action="start",
                status="RUNNING",
                run_id=run_id,
                artifact_paths=["TASK.md", "PLAN.md", "plan.json", "APPROVAL.json"],
                next_action="await write completion",
            )
            branch_prefix = str(cfg.get("workflow", {}).get("default_branch_prefix", "patchbay")).strip("/")
            worktree_root = configured_worktree_root(root, cfg)
            worktree_path = worktree_root / run_id
            branch_name = f"{branch_prefix}/{run_id}"
            set_status(run_path, IMPLEMENTING)
            git_utils.create_worktree(root, worktree_path, branch_name)
            write_text(run_path / "WORKTREE_PATH", str(worktree_path) + "\n")
            set_status(run_path, IMPLEMENTING, worktree_path=str(worktree_path))
            patch, summary, usage_metrics = _call_writer(root=root, run_path=run_path, cfg=cfg, mock=mock)
            if _writer_edits_worktree(cfg, mock, repair=False):
                final_diff = patch
            else:
                final_diff = _apply_writer_diff(worktree_path, patch)
            _validate_writer_scope(run_path, final_diff, summary)
            write_text(run_path / "IMPLEMENTATION.md", summary.rstrip() + "\n")
            write_text(run_path / "FINAL.diff", final_diff)
            result = set_status(run_path, IMPLEMENTED)
            append_event(
                run_path,
                phase="write",
                provider=write_phase["provider"],
                model=write_phase.get("model", ""),
                action="success",
                status="IMPLEMENTED",
                run_id=run_id,
                artifact_paths=["IMPLEMENTATION.md", "FINAL.diff", "writer.log"],
                next_action="test",
                duration_ms=int((time.time() - write_started) * 1000),
                **_usage_event_kwargs(usage_metrics),
            )
            return result
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "write")
        raise
    finally:
        _release_lock(run_path)


def test(cwd: Path, run_id: str) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    try:
        with git_utils.log_to(run_path / "git.log"):
            require_status(status, {IMPLEMENTED}, "test")
            _begin_phase_lock(run_path, "test")
            worktree = Path(status["worktree_path"])
            cfg = load_config(root)
            plan_json = read_json(run_path / "plan.json")
            test_phase = resolve_phase(cfg, "test")
            test_started = time.time()
            append_event(
                run_path,
                phase="test",
                action="start",
                status="RUNNING",
                run_id=run_id,
                artifact_paths=["FINAL.diff", "TEST.log"],
                next_action="await tests",
            )
            commands = _selected_test_commands(worktree, cfg, plan_json, test_phase)
            allowlist = allowlisted_test_commands(cfg)
            timeout = int(test_phase.get("timeout") or 900)
            set_status(run_path, TESTING)
            write_text(run_path / "TEST.log", "")
            if not commands:
                append_text(run_path / "TEST.log", "No test commands selected.\n")
                allow_without_tests = bool(cfg.get("workflow", {}).get("allow_apply_without_tests", False))
                result = set_status(
                    run_path,
                    TESTED,
                    tests_passed=allow_without_tests,
                    tests_status="SKIPPED_ALLOWED" if allow_without_tests else "SKIPPED",
                )
                append_event(
                    run_path,
                    phase="test",
                    action="skipped_allowed" if allow_without_tests else "skipped",
                    status="SKIPPED_ALLOWED" if allow_without_tests else "SKIPPED",
                    detail=(
                        "No test commands selected; workflow.allow_apply_without_tests=true permits apply."
                        if allow_without_tests
                        else "No test commands selected; apply remains blocked until tests are configured or allow_apply_without_tests is enabled."
                    ),
                    run_id=run_id,
                    artifact_paths=["TEST.log"],
                    next_action="review",
                    duration_ms=int((time.time() - test_started) * 1000),
                )
                return result
            for command in commands:
                ensure_command_allowed(command, allowlist)
                result = run_logged(
                    command,
                    cwd=worktree,
                    log_path=run_path / "TEST.log",
                    shell=True,
                    timeout=timeout,
                    env=test_phase.get("env") or None,
                )
                if not result.ok:
                    raise AiFlowError(
                        f"Test command failed: {command}",
                        stage="test",
                        suggested_next_action="Run `scripts/patchbay fix <run_id>` after inspecting TEST.log.",
                    )
            result = set_status(run_path, TESTED, tests_passed=True, tests_status="PASSED")
            append_event(
                run_path,
                phase="test",
                action="success",
                status="TESTED",
                detail=f"{len(commands)} test command(s) passed.",
                run_id=run_id,
                artifact_paths=["TEST.log"],
                next_action="review",
                duration_ms=int((time.time() - test_started) * 1000),
            )
            return result
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "test")
        raise
    finally:
        _release_lock(run_path)


def _review_prompt(run_path: Path) -> str:
    prompt = read_text(Path(__file__).resolve().parent / "prompts" / "reviewer.md")
    return "\n\n".join(
        [
            prompt.rstrip(),
            "# TASK.md",
            read_text(run_path / "TASK.md").rstrip(),
            "# PLAN.md",
            read_text(run_path / "PLAN.md").rstrip(),
            "# FINAL.diff",
            read_text(run_path / "FINAL.diff").rstrip(),
            "# TEST.log",
            read_text(run_path / "TEST.log", default="").rstrip(),
        ]
    ).rstrip() + "\n"


def _tests_phase_completed(status: dict[str, Any]) -> bool:
    return bool(status.get("tests_passed")) or str(status.get("tests_status") or "") in {
        "PASSED",
        "SKIPPED",
        "SKIPPED_ALLOWED",
    }


def review(cwd: Path, run_id: str, *, mock: bool = False) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    try:
        with git_utils.log_to(run_path / "git.log"):
            cfg = load_config(root)
            review_phase = resolve_phase(cfg, "review")
            output_command_key = str(review_phase.get("command_key") or "codex")
            cached_output = run_path / f"{output_command_key}-reviewer.output.md"
            can_recover_cached = status.get("status") == REVIEWING or (
                status.get("status") == FAILED and status.get("stage") == "review"
            )
            if can_recover_cached and cached_output.exists():
                cached = read_text(cached_output).strip()
                if cached.startswith("PASS") or cached.startswith("CHANGES_REQUESTED"):
                    _ensure_review_did_not_change_diff(run_path, status)
                    verdict = review_verdict(cached)
                    write_text(run_path / "REVIEW.md", cached.rstrip() + "\n")
                    if verdict == "PASS":
                        return set_status(run_path, REVIEWED_PASS, review_result="PASS")
                    return set_status(
                        run_path,
                        REVIEWED_CHANGES_REQUESTED,
                        review_result="CHANGES_REQUESTED",
                    )
            elif cached_output.exists():
                cached_output.unlink()
            allowed_statuses = {TESTED}
            if (
                status.get("status") == FAILED
                and status.get("stage") in {"git", "review"}
                and _tests_phase_completed(status)
                and not status.get("review_result")
            ):
                allowed_statuses.add(FAILED)
            require_status(status, allowed_statuses, "review")
            _begin_phase_lock(run_path, "review")
            worktree = Path(status["worktree_path"])
            review_started = time.time()
            append_event(
                run_path,
                phase="review",
                provider=review_phase["provider"],
                model=review_phase.get("model", ""),
                action="start",
                status="RUNNING",
                run_id=run_id,
                artifact_paths=["FINAL.diff", "TEST.log"],
                next_action="await review completion",
            )
            set_status(run_path, REVIEWING)
            before = git_utils.diff(worktree)
            before_status = git_utils.status_porcelain(worktree)
            prompt = _review_prompt(run_path)
            adapter_cfg = _phase_config(cfg, role="reviewer", model=review_phase.get("model"))
            try:
                if mock:
                    raw = REVIEWERS["mock"](prompt=prompt)
                    write_text(run_path / "codex-reviewer.log", "mock reviewer used\n")
                else:
                    reviewer = REVIEWERS.get(review_phase["provider"])
                    if reviewer is None:
                        raise AiFlowError(
                            f"Unknown review provider: {review_phase['provider']}",
                            stage="review",
                            suggested_next_action="Set [phases.review].provider to codex_cli, claude_cli, gemini_cli, or mock.",
                        )
                    raw = reviewer(
                        prompt=prompt,
                        config=adapter_cfg,
                        cwd=worktree,
                        log_path=run_path / "codex-reviewer.log",
                        command_key=review_phase.get("command_key", "codex"),
                        timeout=review_phase.get("timeout", 900),
                        env=review_phase.get("env") or None,
                    )
            except Exception:
                after = git_utils.diff(worktree)
                after_status = git_utils.status_porcelain(worktree)
                if after != before or after_status != before_status:
                    raise SafetyError("Reviewer modified files in the worktree.", stage="review")
                raise
            after = git_utils.diff(worktree)
            after_status = git_utils.status_porcelain(worktree)
            if after != before or after_status != before_status:
                raise SafetyError("Reviewer modified files in the worktree.", stage="review")
            verdict = review_verdict(raw)
            usage_kwargs = _usage_event_kwargs(raw)
            write_text(run_path / "REVIEW.md", raw)
            if verdict == "PASS":
                result = set_status(run_path, REVIEWED_PASS, review_result="PASS")
                append_event(
                    run_path,
                    phase="review",
                    provider=review_phase["provider"],
                    model=review_phase.get("model", ""),
                    action="success",
                    status="PASS",
                    run_id=run_id,
                    artifact_paths=["REVIEW.md"],
                    next_action="apply",
                    duration_ms=int((time.time() - review_started) * 1000),
                    **usage_kwargs,
                )
                return result
            result = set_status(
                run_path,
                REVIEWED_CHANGES_REQUESTED,
                review_result="CHANGES_REQUESTED",
            )
            append_event(
                run_path,
                phase="review",
                provider=review_phase["provider"],
                model=review_phase.get("model", ""),
                action="success",
                status="CHANGES_REQUESTED",
                run_id=run_id,
                artifact_paths=["REVIEW.md"],
                next_action="fix",
                duration_ms=int((time.time() - review_started) * 1000),
                **usage_kwargs,
            )
            return result
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "review")
        raise
    finally:
        _release_lock(run_path)


def _ensure_review_did_not_change_diff(run_path: Path, status: dict[str, Any]) -> None:
    worktree_raw = status.get("worktree_path")
    if not worktree_raw:
        return
    expected = read_text(run_path / "FINAL.diff", default="")
    worktree = Path(worktree_raw)
    current = git_utils.diff(worktree)
    if current != expected:
        raise SafetyError("Reviewer modified files in the worktree.", stage="review")
    expected_paths = set(paths_from_patch(expected))
    extra_dirty = [path for path in git_utils.dirty_paths(worktree) if path not in expected_paths]
    if extra_dirty:
        raise SafetyError("Reviewer modified files in the worktree.", stage="review")


def fix(cwd: Path, run_id: str, *, mock: bool = False) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    try:
        with git_utils.log_to(run_path / "git.log"):
            allowed = {REVIEWED_CHANGES_REQUESTED}
            if status.get("status") == FAILED and status.get("stage") == "test":
                allowed.add(FAILED)
            require_status(status, allowed, "fix")
            _begin_phase_lock(run_path, "fix")
            cfg = load_config(root)
            max_repairs = int(cfg.get("writer", {}).get("max_repair_iterations", 2))
            iterations = int(status.get("fix_iterations") or 0)
            if iterations >= max_repairs:
                raise StateError(
                    f"Maximum fix iterations reached: {max_repairs}",
                    stage="fix",
                    suggested_next_action="Inspect artifacts manually or start a new run.",
                )
            worktree = Path(status["worktree_path"])
            fix_phase = resolve_phase(cfg, "fix")
            fix_started = time.time()
            append_event(
                run_path,
                phase="fix",
                provider=fix_phase["provider"],
                model=fix_phase.get("model", ""),
                action="start",
                status="RUNNING",
                detail=f"Fix iteration {iterations + 1}/{max_repairs}",
                run_id=run_id,
                artifact_paths=["FINAL.diff", "REVIEW.md", "TEST.log"],
                next_action="await fix completion",
            )
            set_status(run_path, FIXING)
            patch, summary, usage_metrics = _call_writer(root=root, run_path=run_path, cfg=cfg, mock=mock, repair=True)
            if _writer_edits_worktree(cfg, mock, repair=True):
                final_diff = patch
            else:
                final_diff = _apply_writer_diff(worktree, patch)
            _validate_writer_scope(run_path, final_diff, summary)
            append_text(run_path / "FIXES.md", f"## Fix iteration {iterations + 1}\n\n{summary.rstrip()}\n\n")
            write_text(run_path / "FINAL.diff", final_diff)
            result = set_status(
                run_path,
                IMPLEMENTED,
                fix_iterations=iterations + 1,
                tests_passed=False,
                tests_status="NOT_RUN",
                review_result=None,
            )
            append_event(
                run_path,
                phase="fix",
                provider=fix_phase["provider"],
                model=fix_phase.get("model", ""),
                action="success",
                status="IMPLEMENTED",
                detail=f"Fix iteration {iterations + 1} complete.",
                run_id=run_id,
                artifact_paths=["FIXES.md", "FINAL.diff"],
                next_action="test",
                duration_ms=int((time.time() - fix_started) * 1000),
                **_usage_event_kwargs(usage_metrics),
            )
            return result
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "fix")
        raise
    finally:
        _release_lock(run_path)


def _writer_edits_worktree(cfg: dict[str, Any], mock: bool, *, repair: bool = False) -> bool:
    if mock:
        return False
    phase = "fix" if repair else "write"
    provider = resolve_phase(cfg, phase)["provider"]
    if provider == "reasonix_cli":
        return True
    provider_cfg = cfg.get("providers", {}).get(provider, {})
    if isinstance(provider_cfg, dict):
        return str(provider_cfg.get("output_contract", "")) == "worktree_diff"
    return False


def status(cwd: Path, run_id: str) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path = _run_dir(root, run_id)
    try:
        _, data = _load_run(root, run_id)
    except StateError:
        job_path = _job_path(run_path)
        if not job_path.exists():
            raise
        job = read_json(job_path)
        data = {
            "run_id": run_id,
            "status": "RUNNING",
            "task": "",
            "repo_root": str(root),
            "config_path": str(config_path(root)),
            "worktree_path": None,
            "tests_passed": False,
            "tests_status": "NOT_RUN",
            "review_result": None,
            "fix_iterations": 0,
            "created_at": job.get("started_at"),
            "updated_at": job.get("started_at"),
            "error": None,
            "stage": job.get("phase", "background"),
            "suggested_next_action": "Poll events/status until the background job writes STATUS.json.",
        }
    data = dict(data)
    data["run_dir"] = str(run_path)
    data["artifacts"] = list_run_artifacts(run_path)
    latest = latest_event(run_path)
    if latest:
        data["latest_event"] = latest
    data["current_phase"] = data.get("stage") or (latest or {}).get("phase") or _current_phase_from_status(str(data.get("status", "")))
    data["event_count"] = event_count(run_path)
    run_metrics = _run_metrics(run_path)
    data["next_commands"] = _next_commands(data)
    data["gate_state"] = _gate_state(data)
    if data.get("status") == FAILED:
        data["failure_recovery"] = _failure_recovery(data)
    cfg = load_config(root)
    effective: dict[str, Any] = {}
    for phase in ("plan", "write", "review", "fix"):
        resolved = resolve_phase(cfg, phase)
        effective[phase] = {
            "provider": resolved.get("provider", ""),
            "model": resolved.get("model", ""),
            "command_key": resolved.get("command_key", ""),
        }
    data["effective_phase_providers"] = effective
    data["routing_evidence"] = _run_routing_evidence(run_metrics, effective)
    run_metrics["routing_evidence"] = data["routing_evidence"]
    data["run_metrics"] = run_metrics
    job_path = _job_path(run_path)
    if job_path.exists():
        data["job"] = read_json(job_path)
    return data


def _failure_recovery(status_data: dict[str, Any]) -> dict[str, Any]:
    stage = str(status_data.get("stage") or status_data.get("current_phase") or "unknown")
    artifacts = list(status_data.get("artifacts") or [])
    inspect = _failure_artifacts_for_stage(stage, artifacts)
    suggested = str(status_data.get("suggested_next_action") or "").strip()
    if not suggested:
        suggested = "Inspect diagnostics before retrying or starting a replacement run."
    return {
        "stage": stage,
        "error": str(status_data.get("error") or "Run failed."),
        "suggested_next_action": suggested,
        "safe_actions": ["status", "events", "artifact", "diff", "new_run"],
        "artifacts": inspect,
        "summary": f"Run failed in {stage}; inspect {', '.join(inspect) if inspect else 'diagnostics'} before taking another action.",
    }


def _failure_artifacts_for_stage(stage: str, artifacts: list[str]) -> list[str]:
    preferred: dict[str, list[str]] = {
        "plan": ["PLAN.md", "plan.json", "claude-planner.log", "events.jsonl", "trace.jsonl", "STATUS.json"],
        "write": ["writer.log", "IMPLEMENTATION.md", "FINAL.diff", "events.jsonl", "trace.jsonl", "STATUS.json"],
        "test": ["TEST.log", "FINAL.diff", "events.jsonl", "trace.jsonl", "STATUS.json"],
        "review": ["REVIEW.md", "codex-reviewer.log", "FINAL.diff", "events.jsonl", "trace.jsonl", "STATUS.json"],
        "fix": ["writer.log", "FIXES.md", "FINAL.diff", "TEST.log", "REVIEW.md", "events.jsonl", "trace.jsonl", "STATUS.json"],
        "apply": ["FINAL.diff", "git.log", "events.jsonl", "trace.jsonl", "STATUS.json"],
    }
    ordered = preferred.get(stage, ["events.jsonl", "trace.jsonl", "STATUS.json"])
    available = [name for name in ordered if name in artifacts]
    if available:
        return available
    fallback = [name for name in artifacts if name.endswith((".log", ".md", ".diff", ".json", ".jsonl"))]
    return fallback[:6]


def _run_metrics(run_path: Path) -> dict[str, Any]:
    entries = list_events(run_path)
    phase_durations: dict[str, int] = {}
    phase_attempts: dict[str, int] = {}
    open_phase_starts: dict[str, str] = {}
    provider_usage: dict[tuple[str, str, str], dict[str, Any]] = {}
    provider_order: list[tuple[str, str, str]] = []
    token_totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
    }
    token_known = False
    token_by_phase: dict[str, dict[str, Any]] = {}
    cost_total = 0.0
    cost_known = False
    cost_currency = "USD"
    cost_by_phase: dict[str, dict[str, Any]] = {}

    for entry in entries:
        phase = str(entry.get("phase") or "")
        action = str(entry.get("action") or "")
        timestamp = str(entry.get("timestamp") or "")
        if phase and action == "start":
            phase_attempts[phase] = phase_attempts.get(phase, 0) + 1
            open_phase_starts[phase] = timestamp

        duration_ms = _event_duration_ms(entry)
        if phase and duration_ms is not None:
            phase_durations[phase] = phase_durations.get(phase, 0) + duration_ms
            open_phase_starts.pop(phase, None)
        elif phase and action != "start":
            estimated = _estimate_duration_ms(open_phase_starts.pop(phase, ""), timestamp)
            if estimated is not None:
                phase_durations[phase] = phase_durations.get(phase, 0) + estimated

        provider = str(entry.get("provider") or "")
        model = str(entry.get("model") or "")
        provider_bucket: dict[str, Any] | None = None
        if provider or model:
            key = (phase, provider, model)
            if key not in provider_usage:
                provider_usage[key] = {
                    "phase": phase,
                    "provider": provider,
                    "model": model,
                    "events": 0,
                    "duration_ms": 0,
                }
                provider_order.append(key)
            provider_bucket = provider_usage[key]
            provider_bucket["events"] += 1
            if duration_ms is not None:
                provider_bucket["duration_ms"] += duration_ms

        usage = metrics_from_output(entry)
        token_usage = usage.get("token_usage")
        if isinstance(token_usage, dict) and token_usage.get("known"):
            token_known = True
            if provider_bucket is not None:
                _accumulate_provider_tokens(provider_bucket, token_usage)
            _accumulate_phase_tokens(token_by_phase, phase, token_usage)
            for field in ("input_tokens", "output_tokens", "cached_tokens", "total_tokens"):
                value = token_usage.get(field)
                if value is not None:
                    token_totals[field] += int(value)

        cost = usage.get("cost")
        if isinstance(cost, dict) and cost.get("known"):
            cost_known = True
            if provider_bucket is not None:
                _accumulate_provider_cost(provider_bucket, cost)
            estimated = cost.get("estimated_total")
            if estimated is not None:
                cost_total += float(estimated)
            currency = str(cost.get("currency") or "USD")
            if cost_currency == "USD" or cost_currency == currency:
                cost_currency = currency
            _accumulate_phase_cost(cost_by_phase, phase, cost)

    total_duration_ms = sum(phase_durations.values()) if phase_durations else None
    return {
        "duration_known": bool(phase_durations),
        "duration_source": "event_or_timestamp" if phase_durations else "unknown",
        "total_duration_ms": total_duration_ms,
        "phase_durations_ms": phase_durations,
        "phase_attempts": phase_attempts,
        "event_count": event_count(run_path),
        "trace_count": trace_count(run_path),
        "provider_usage": [provider_usage[key] for key in provider_order],
        "cost": {
            "known": cost_known,
            "currency": cost_currency,
            "estimated_total": round(cost_total, 6) if cost_known else None,
            "by_phase": cost_by_phase,
        },
        "token_usage": {
            "known": token_known,
            "input_tokens": token_totals["input_tokens"] if token_known else None,
            "output_tokens": token_totals["output_tokens"] if token_known else None,
            "cached_tokens": token_totals["cached_tokens"] if token_known else None,
            "total_tokens": token_totals["total_tokens"] if token_known else None,
            "by_phase": token_by_phase,
        },
    }


def _run_routing_evidence(run_metrics: dict[str, Any], effective: dict[str, Any]) -> dict[str, Any]:
    provider_usage = [
        entry
        for entry in run_metrics.get("provider_usage", [])
        if isinstance(entry, dict) and (entry.get("provider") or entry.get("model"))
    ]
    phases: dict[str, dict[str, Any]] = {}
    configured_economy_phases: list[str] = []
    observed_economy_phases: list[str] = []
    missing_evidence: list[str] = []
    for phase in ("write", "fix"):
        configured = _routing_phase_snapshot(effective.get(phase) or {})
        observed = [
            _routing_phase_snapshot(entry)
            for entry in provider_usage
            if str(entry.get("phase") or "") == phase
        ]
        configured_economy = _is_economy_route(configured)
        observed_economy = any(_is_economy_route(entry) for entry in observed)
        if configured_economy:
            configured_economy_phases.append(phase)
        if observed_economy:
            observed_economy_phases.append(phase)
        if not observed:
            missing_evidence.append(phase)
        phases[phase] = {
            "configured": configured,
            "observed": observed,
            "configured_economy": configured_economy,
            "observed_economy": observed_economy,
            "status": "observed_economy" if observed_economy else "observed_other" if observed else "not_observed",
        }
    economy_configured = configured_economy_phases == ["write", "fix"]
    return {
        "target": {"provider": ECONOMY_PROVIDER, "model": ECONOMY_MODEL},
        "economy_configured": economy_configured,
        "configured_economy_phases": configured_economy_phases,
        "observed_economy_phases": observed_economy_phases,
        "missing_evidence": missing_evidence,
        "phases": phases,
        "summary": _routing_evidence_summary(
            economy_configured=economy_configured,
            observed_economy_phases=observed_economy_phases,
            missing_evidence=missing_evidence,
        ),
    }


def _routing_phase_snapshot(route: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "provider": str(route.get("provider") or ""),
        "model": str(route.get("model") or ""),
    }
    for key in ("phase", "command_key", "events", "duration_ms", "input_tokens", "output_tokens", "cached_tokens", "total_tokens"):
        value = route.get(key)
        if value not in (None, ""):
            snapshot[key] = value
    for key in ("cost", "token_usage"):
        value = route.get(key)
        if isinstance(value, dict) and value:
            snapshot[key] = value
    return snapshot


def _is_economy_route(route: dict[str, Any]) -> bool:
    return route.get("provider") == ECONOMY_PROVIDER and route.get("model") == ECONOMY_MODEL


def _routing_evidence_summary(
    *,
    economy_configured: bool,
    observed_economy_phases: list[str],
    missing_evidence: list[str],
) -> str:
    if economy_configured and set(observed_economy_phases) == {"write", "fix"}:
        return "Economy route configured and observed for write/fix."
    if economy_configured and observed_economy_phases:
        missing = "/".join(missing_evidence) if missing_evidence else "remaining phases"
        observed = "/".join(observed_economy_phases)
        return f"Economy route configured; observed {observed}, {missing} not observed yet."
    if economy_configured:
        return "Economy route configured for write/fix; provider evidence is not observed yet."
    if observed_economy_phases:
        observed = "/".join(observed_economy_phases)
        return f"Observed {observed} on Reasonix/DeepSeek, but current write/fix config is not fully economy."
    return "Economy route is not configured or not observed for write/fix."


def _accumulate_phase_tokens(store: dict[str, dict[str, Any]], phase: str, token_usage: dict[str, Any]) -> None:
    if not phase:
        phase = "unknown"
    bucket = store.setdefault(
        phase,
        {
            "known": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
        },
    )
    bucket["known"] = True
    for field in ("input_tokens", "output_tokens", "cached_tokens", "total_tokens"):
        value = token_usage.get(field)
        if value is not None:
            bucket[field] += int(value)


def _accumulate_provider_tokens(bucket: dict[str, Any], token_usage: dict[str, Any]) -> None:
    provider_tokens = bucket.setdefault(
        "token_usage",
        {
            "known": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
        },
    )
    provider_tokens["known"] = True
    for field in ("input_tokens", "output_tokens", "cached_tokens", "total_tokens"):
        value = token_usage.get(field)
        if value is not None:
            provider_tokens[field] += int(value)
        bucket[field] = provider_tokens[field]


def _accumulate_phase_cost(store: dict[str, dict[str, Any]], phase: str, cost: dict[str, Any]) -> None:
    if not phase:
        phase = "unknown"
    bucket = store.setdefault(
        phase,
        {
            "known": False,
            "currency": str(cost.get("currency") or "USD"),
            "estimated_total": 0.0,
        },
    )
    bucket["known"] = True
    estimated = cost.get("estimated_total")
    if estimated is not None:
        bucket["estimated_total"] += float(estimated)
    currency = str(cost.get("currency") or bucket.get("currency") or "USD")
    bucket["currency"] = currency


def _accumulate_provider_cost(bucket: dict[str, Any], cost: dict[str, Any]) -> None:
    provider_cost = bucket.setdefault(
        "cost",
        {
            "known": False,
            "currency": str(cost.get("currency") or "USD"),
            "estimated_total": 0.0,
        },
    )
    provider_cost["known"] = True
    estimated = cost.get("estimated_total")
    if estimated is not None:
        provider_cost["estimated_total"] = round(float(provider_cost["estimated_total"]) + float(estimated), 6)
    provider_cost["currency"] = str(cost.get("currency") or provider_cost.get("currency") or "USD")


def _event_duration_ms(entry: dict[str, Any]) -> int | None:
    value = entry.get("duration_ms")
    if value is None:
        return None
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return None
    if duration < 0:
        return None
    return duration


def _estimate_duration_ms(start: str, end: str) -> int | None:
    if not start or not end:
        return None
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
    except ValueError:
        return None
    duration = int((end_time - start_time).total_seconds() * 1000)
    return duration if duration >= 0 else None


def _current_phase_from_status(status_value: str) -> str:
    mapping = {
        NEW: "plan",
        PLANNED: "approve",
        APPROVED: "write",
        IMPLEMENTING: "write",
        IMPLEMENTED: "test",
        TESTING: "test",
        TESTED: "review",
        REVIEWING: "review",
        REVIEWED_PASS: "apply",
        REVIEWED_CHANGES_REQUESTED: "fix",
        FIXING: "fix",
        APPLIED: "cleanup",
        FAILED: "error",
    }
    return mapping.get(status_value, "")


def _next_commands(data: dict[str, Any]) -> list[str]:
    current = str(data.get("status", ""))
    if current == PLANNED:
        return ["approve"]
    if current == APPROVED:
        return ["write"]
    if current == IMPLEMENTED:
        return ["test"]
    if current == TESTED:
        return ["review"]
    if current == REVIEWED_CHANGES_REQUESTED:
        return ["fix"]
    if current == REVIEWED_PASS and data.get("tests_passed"):
        return ["apply"]
    if current == APPLIED:
        return ["cleanup"]
    return []


def _gate_state(data: dict[str, Any]) -> dict[str, Any]:
    status_value = str(data.get("status"))
    stage_value = str(data.get("stage") or data.get("current_phase") or "")
    return {
        "approved": status_value not in {"NEW", PLANNED} and not (status_value == "RUNNING" and stage_value == "plan"),
        "tests_passed": bool(data.get("tests_passed")),
        "tests_status": data.get("tests_status", "NOT_RUN"),
        "review_result": data.get("review_result"),
        "ready_to_apply": data.get("status") == REVIEWED_PASS and bool(data.get("tests_passed")),
    }


def context(
    cwd: Path,
    run_id: str,
    *,
    since_event: int = 0,
    since_trace: int = 0,
    include_trace: bool = False,
) -> dict[str, Any]:
    """Return a unified run handoff digest for CLI, MCP, and web clients."""
    root = resolve_root(cwd)
    run_path = _run_path_for_read(root, run_id)
    status_data = status(root, run_id)
    return build_handoff_context(
        run_path=run_path,
        status_data=status_data,
        since_event=since_event,
        since_trace=since_trace,
        include_trace=include_trace,
    )


def metrics(cwd: Path, run_id: str) -> dict[str, Any]:
    """Return the run efficiency digest without the full handoff payload."""
    status_data = status(cwd, run_id)
    return {
        "run_id": run_id,
        "status": status_data.get("status"),
        "current_phase": status_data.get("current_phase"),
        "effective_phase_providers": status_data.get("effective_phase_providers", {}),
        "routing_evidence": status_data.get("routing_evidence", {}),
        "run_metrics": status_data.get("run_metrics", {}),
    }


def events(cwd: Path, run_id: str, *, since: int = 0, phase: str | None = None) -> dict[str, Any]:
    """Return event log entries for a run (used by CLI ``events`` and MCP ``patchbay_events``)."""
    root = resolve_root(cwd)
    run_path = _run_path_for_read(root, run_id)
    entries = list_events(run_path, since=since, phase=phase)
    return {
        "run_id": run_id,
        "since": since,
        "total": event_count(run_path),
        "returned": len(entries),
        "events": entries,
    }


def trace(cwd: Path, run_id: str, *, since: int = 0, phase: str | None = None) -> dict[str, Any]:
    """Return structured trace entries for a run (used by CLI ``trace`` and MCP ``patchbay_trace``)."""
    root = resolve_root(cwd)
    run_path = _run_path_for_read(root, run_id)
    entries = list_trace(run_path, since=since, phase=phase)
    return {
        "run_id": run_id,
        "since": since,
        "total": trace_count(run_path),
        "returned": len(entries),
        "trace": entries,
    }


def runs(cwd: Path, *, limit: int = 20) -> dict[str, Any]:
    root = resolve_root(cwd)
    ensure_layout(root)
    items: list[dict[str, Any]] = []
    for candidate in sorted(runs_dir(root).iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not candidate.is_dir():
            continue
        try:
            if (candidate / "STATUS.json").exists():
                data = load_status(candidate)
            elif (candidate / "JOB.json").exists():
                job = read_json(candidate / "JOB.json")
                data = {
                    "run_id": job.get("run_id", candidate.name),
                    "status": "RUNNING",
                    "task": job.get("task", ""),
                    "updated_at": job.get("started_at"),
                }
            else:
                continue
        except Exception:
            continue
        items.append(
            {
                "run_id": data.get("run_id", candidate.name),
                "status": data.get("status"),
                "task": data.get("task"),
                "updated_at": data.get("updated_at"),
                "run_dir": str(candidate),
            }
        )
        if len(items) >= limit:
            break
    return {"count": len(items), "runs": items}


def artifact(cwd: Path, run_id: str, artifact_name: str, *, tail: int | None = None) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path = _run_path_for_read(root, run_id)
    normalized = artifact_name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
        raise SafetyError("Invalid artifact name; use a file name inside the run directory.", stage="artifact")
    path = run_path / normalized
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(run_path.resolve()):
            raise SafetyError("Invalid artifact name; use a file name inside the run directory.", stage="artifact")
    except AttributeError:
        if str(path.resolve()).startswith(str(run_path.resolve())) is False:
            raise SafetyError("Invalid artifact name; use a file name inside the run directory.", stage="artifact")
    if not path.exists() or not path.is_file():
        raise StateError(f"Missing artifact: {artifact_name}", stage="artifact")
    text = read_text(path)
    lines = text.splitlines()
    if tail is not None and tail >= 0:
        lines = lines[-tail:] if tail else []
        text = "\n".join(lines)
        if text:
            text += "\n"
    return {
        "run_id": run_id,
        "artifact": normalized,
        "path": str(path),
        "text": text,
        "lines_returned": len(lines),
    }


def diff(cwd: Path, run_id: str) -> str:
    root = resolve_root(cwd)
    run_path = _run_path_for_read(root, run_id)
    data = load_status(run_path) if (run_path / "STATUS.json").exists() else {}
    final = run_path / "FINAL.diff"
    if final.exists():
        return read_text(final)
    worktree_raw = data.get("worktree_path")
    if worktree_raw:
        return git_utils.diff(Path(worktree_raw))
    return ""


def _ensure_apply_has_no_executor(apply_phase: dict[str, Any]) -> None:
    disallowed = []
    for key in ("provider", "model", "command", "command_key"):
        if str(apply_phase.get(key, "")).strip():
            disallowed.append(key)
    if disallowed:
        raise AiFlowError(
            "Apply phase does not support model/tool executors; Patchbay applies the reviewed FINAL.diff via git. "
            "Remove phases.apply provider/model/command/command_key and keep only timeout/env if needed. "
            f"Configured executor fields: {', '.join(disallowed)}",
            stage="apply",
            suggested_next_action="Remove executor fields from [phases.apply] or use plan/write/review/fix phase overrides.",
        )


def apply(cwd: Path, run_id: str) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    try:
        with git_utils.log_to(run_path / "git.log"):
            require_status(status, {REVIEWED_PASS}, "apply")
            if not status.get("tests_passed"):
                append_event(
                    run_path,
                    phase="apply",
                    action="apply_denied",
                    status="DENIED",
                    detail="Cannot apply because tests_passed is false.",
                    run_id=run_id,
                )
                raise StateError("Cannot apply because tests_passed is false.", stage="apply")
            cfg = load_config(root)
            apply_phase = resolve_phase(cfg, "apply")
            _ensure_apply_has_no_executor(apply_phase)
            if cfg.get("workflow", {}).get("fail_on_dirty_workspace", True):
                git_utils.ensure_clean(root)
            patch = read_text(run_path / "FINAL.diff")
            validate_patch_safety(patch)
            try:
                git_utils.apply_diff(root, patch)
            except GitError:
                try:
                    git_utils.apply_diff(root, patch, recount=True, threeway=True)
                except GitError:
                    git_utils.apply_diff(root, patch, recount=True, ignore_space_change=True)
            result = set_status(run_path, APPLIED)
            append_event(
                run_path,
                phase="apply",
                action="apply_granted",
                status="APPLIED",
                detail=f"Applied FINAL.diff to {root}",
                run_id=run_id,
            )
            return result
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "apply")
        raise


def cleanup(cwd: Path, run_id: str) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, data = _load_run(root, run_id)
    with git_utils.log_to(run_path / "git.log"):
        worktree_raw = data.get("worktree_path")
        if worktree_raw and git_utils.is_repo(root):
            git_utils.remove_worktree(root, Path(worktree_raw))
    return status(cwd, run_id)


def _mark_failure_if_possible(run_path: Path, exc: Exception, stage: str) -> None:
    if not (run_path / "STATUS.json").exists():
        return
    suggested = getattr(exc, "suggested_next_action", None) or "Inspect run artifacts and rerun the failed stage."
    mark_failed(run_path, error=str(exc), stage=getattr(exc, "stage", None) or stage, suggested_next_action=suggested)
    try:
        append_event(
            run_path,
            phase=stage,
            action="error",
            status="ERROR",
            detail=str(exc),
        )
    except Exception:
        pass


EXAMPLE_TOML = """[models]
planner = "claude-opus-4-7"
writer = "deepseek-v4-pro"
reviewer = "gpt-5.5"

[commands]
claude = "claude"
codex = "codex"
gemini = "gemini"
reasonix = ""

[writer]
provider = "reasonix_cli" # Reasonix agent (默认)
max_context_files = 30
max_patch_attempts = 3
max_repair_iterations = 2

[workflow]
require_plan_approval = true
default_branch_prefix = "patchbay"
worktree_root = "../.patchbay-worktrees"
fail_on_dirty_workspace = true
apply_to_current_workspace_only_after_review_pass = true
allow_apply_without_tests = false # set true only for demo/mock repos that intentionally skip tests

[commands_allowlist]
test = [
  "npm test",
  "npm run test",
  "npm run lint",
  "npm run typecheck",
  "pytest",
  "pytest -q",
  "go test ./...",
  "cargo test"
]

# ---------------------------------------------------------------------------
# Per-phase executors (host-agnostic).
# Uncomment any section to override the default provider / model for that phase.
# Supported providers per phase:
#   plan:   claude_cli | codex_cli | gemini_cli | mock
#   write:  reasonix_cli | mock
#   review: codex_cli | claude_cli | gemini_cli | mock
#   fix:    (defaults to write provider) reasonix_cli | mock
#   test:   no LLM executor (command allowlist only)
#   apply:  no LLM executor (git apply only)
# ---------------------------------------------------------------------------

# [phases.plan]
# provider = "claude_cli"      # claude_cli | codex_cli | gemini_cli | mock
# model = "claude-opus-4-7"

# [phases.write]
# provider = "reasonix_cli"    # reasonix_cli | mock (默认)
# model = "deepseek-v4-pro"
# command_key = "reasonix"     # 仅 provider = reasonix_cli 时有效

# [phases.review]
# provider = "codex_cli"       # codex_cli | claude_cli | gemini_cli | mock
# model = "gpt-5.5"

# [phases.fix]
# provider = ""                # defaults to phases.write.provider
# model = ""                   # defaults to phases.write.model

# [phases.test]
# commands = []                # optional ordered test commands; every command must be in commands_allowlist.test
# timeout = 900                # per-command timeout in seconds

# [phases.apply]
# # no LLM executor; Patchbay applies the reviewed FINAL.diff via git after tests and review pass
"""


AGENTS_MD = """# Multi-Agent Workflow

当用户明确说：
- “走多模型流程”
- “multi-agent workflow”

你必须使用 `scripts/patchbay`，不要直接改代码。旧入口 `scripts/ai-flow` 仍可兼容使用，但新文档优先使用 Patchbay 名称。

Patchbay 支持任意 MCP host 作为交互入口（Claude Code、Claude Desktop、Codex CLI、Codex Desktop、Gemini CLI 等），流程和门禁完全一致。如果当前 MCP host 已配置 `patchbay_*` MCP 工具，可以用 MCP 调用同一套 Patchbay 编排器；旧的 `ai_flow_*` 工具名也保留为兼容别名。每个阶段（plan/write/review/fix）的 provider 和模型可以通过 `.ai/patchbay.toml` 的 `[phases.<phase>]` 独立配置。无论入口是什么，仍然必须遵守下面的阶段顺序和确认门禁。

流程：

1. 运行：
   `scripts/patchbay plan --task "<用户任务>"`

2. 阅读并展示：
   `.ai/runs/<run_id>/PLAN.md`

3. 等待用户明确确认。

4. 用户确认后运行：
   `scripts/patchbay approve <run_id>`
   `scripts/patchbay write <run_id>`
   `scripts/patchbay test <run_id>`
   `scripts/patchbay review <run_id>`

5. 如果 review 是 CHANGES_REQUESTED：
   最多运行两轮：
   `scripts/patchbay fix <run_id>`
   `scripts/patchbay test <run_id>`
   `scripts/patchbay review <run_id>`

6. 只有 review PASS 且测试通过后，才询问用户是否 apply。

7. 未经用户确认，不要运行：
   `scripts/patchbay apply <run_id>`
"""


DOCS_MD = """# Patchbay

Patchbay 是一个本地补丁编排器：任意支持 MCP 的客户端都可以作为入口，默认把规划、实现、测试、审查和应用拆成可审计阶段。当前默认角色绑定是 Claude 规划，Reasonix (默认 Agent) 实现，Codex 审查；后续可以把这些槽位换成别的工具。

## 环境准备

- 登录 Claude Code，并确保 `claude` CLI 可用。
- 登录 Codex CLI，并确保 `codex` CLI 可用。

## 配置

运行：

```bash
scripts/patchbay init
cp .ai/patchbay.example.toml .ai/patchbay.toml
```

按需编辑 `.ai/patchbay.toml`，尤其是 writer provider、命令路径和测试 allowlist。

Writer 使用 Reasonix ACP coding agent（`reasonix acp`），由 Reasonix 自己的文件系统工具修改独立 worktree，Patchbay 只负责审批权限并捕获最终 `git diff`。

## 常用命令

```bash
scripts/patchbay plan --task "..."
scripts/patchbay approve <run_id>
scripts/patchbay write <run_id>
scripts/patchbay test <run_id>
scripts/patchbay review <run_id>
scripts/patchbay fix <run_id>
scripts/patchbay status <run_id>
scripts/patchbay diff <run_id>
scripts/patchbay apply <run_id>
scripts/patchbay cleanup <run_id>
```

mock 模式：

```bash
scripts/patchbay plan --task "..." --mock
scripts/patchbay write <run_id> --mock
scripts/patchbay review <run_id> --mock
```

## MCP 使用方式

当用户要求“走多模型流程”时，先运行 plan 并展示 `.ai/runs/<run_id>/PLAN.md`。只有用户确认计划后，才能 approve/write/test/review。未经用户确认，不要 apply。

如果在带网络沙箱的 MCP host 中运行真实模型阶段，`plan`、`write`、`review` 需要允许子进程访问对应上游。默认 `worktree_root = "../.patchbay-worktrees"` 时，`write`、`test`、`review` 还需要能访问仓库兄弟目录里的 worktree。若 Claude 日志里出现 `ConnectionRefused`、`duration_api_ms: 0` 或上游没有请求记录，通常是编排器子进程没有网络权限，而不是 key/base URL 本身不可用。

## MCP

CLI 跑通后可以把同一套流程作为 MCP 工具暴露给任意 MCP host：

```bash
codex mcp add patchbay -- python scripts/patchbay_mcp_server.py
```

MCP 只调用 `scripts.ai_flow.service` 中已有函数，不复制业务逻辑。新工具名使用 `patchbay_*`，旧的 `ai_flow_*` 作为兼容别名保留。

## 故障排查

- Claude CLI 不存在：检查 `[commands].claude`，或用 `--mock` 验证流程。
- Codex CLI 不存在：检查 `[commands].codex`，或用 `--mock` 验证审查流程。
- Reasonix 只聊天不改文件：确认 `[writer].provider = "reasonix_cli"`，且 `[commands].reasonix` 指向 `reasonix.cmd`/`reasonix`。Patchbay 会自动使用 `reasonix acp`。
- Claude 输出空 result 但其实已生成计划：Patchbay 会从 `stream-json` assistant event 和 Claude transcript 中恢复计划文本；查看 `claude-planner.log` 确认恢复路径。
- patch apply 失败：检查 `writer.log` 和 `FINAL.diff`。
- test command 不在 allowlist：把确认安全的命令加入 `.ai/patchbay.toml` 的 `commands_allowlist.test`。
- Windows PowerShell 拒绝运行 `.ps1` 脚本：优先使用 `codex.cmd` 与 `reasonix.cmd`（以及 `scripts/patchbay.cmd`）等 `.cmd` 入口，避免修改系统 ExecutionPolicy。

## 安全说明

Patchbay 拒绝修改 repo 外路径、`.git/`、`.env*`、secret-like 文件、绝对路径 patch、路径穿越 patch，并要求测试命令在 allowlist 中。

## 清理 worktree

```bash
scripts/patchbay cleanup <run_id>
```
"""
