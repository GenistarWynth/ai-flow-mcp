from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from . import git_utils
from .adapters import (
    PLANNERS,
    REVIEWERS,
    WRITERS,
    run_codex_reviewer,
    run_deepseek_writer,
    run_mock_planner,
    run_mock_reviewer,
    run_mock_writer,
    run_reasonix_writer,
)
from .artifacts import (
    append_text,
    ensure_layout,
    list_run_artifacts,
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


def resolve_root(cwd: Path) -> Path:
    return find_project_root(cwd, prefer_git=True)


def _run_dir(root: Path, run_id: str) -> Path:
    return artifact_run_dir(root, run_id)


def _load_run(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = _run_dir(root, run_id)
    return path, load_status(path)


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


def _call_writer(
    *,
    root: Path,
    run_path: Path,
    cfg: dict[str, Any],
    mock: bool,
    repair: bool = False,
) -> tuple[str, str]:
    status = load_status(run_path)
    task = str(status["task"])
    log_path = run_path / "writer.log"
    max_attempts = int(cfg.get("writer", {}).get("max_patch_attempts", 3))
    extra_files: list[str] = []
    raw = ""
    summary = ""
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
                    suggested_next_action="Set [phases.write].provider or [writer].provider to reasonix_cli, deepseek_api, or mock.",
                )
            try:
                if provider == "reasonix_cli":
                    raw = writer(prompt=prompt, config=adapter_cfg, cwd=worktree, log_path=log_path, command_key=p_command_key, timeout=p_timeout, env=p_env)
                    append_text(log_path, raw + "\n")
                    parsed = parse_writer_output(raw)
                    summary = parsed.summary
                    git_utils.add_all(worktree)
                    final_diff = git_utils.diff(worktree)
                    if not final_diff.strip():
                        raise AiFlowError("Reasonix agent did not produce a worktree diff.", stage="write")
                    validate_patch_safety(final_diff)
                    return final_diff, summary
                elif provider == "deepseek_api":
                    raw = writer(prompt=prompt, config=adapter_cfg, log_path=log_path, command_key=p_command_key, timeout=p_timeout, env=p_env)
                else:
                    raise AiFlowError(f"Unknown writer provider: {provider}", stage="write")
            except AiFlowError:
                if attempt < max_attempts - 1:
                    append_text(log_path, "\nWriter attempt failed; retrying.\n")
                    continue
                raise
        append_text(log_path, raw + "\n")
        parsed = parse_writer_output(raw)
        summary = parsed.summary
        if parsed.needed_files:
            extra_files.extend(parsed.needed_files)
            continue
        if not parsed.diff:
            raise AiFlowError("Writer did not provide a diff.", stage="write")
        return parsed.diff, summary
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


def plan(cwd: Path, *, task: str, mock: bool = False) -> dict[str, str]:
    root = resolve_root(cwd)
    ensure_layout(root)
    cfg = load_config(root)
    run_id = new_run_id(task)
    run_path = _run_dir(root, run_id)
    run_path.mkdir(parents=True, exist_ok=True)
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
    try:
        write_text(run_path / "TASK.md", task.rstrip() + "\n")
        write_text(run_path / "BASE_COMMIT", (base_commit or "") + "\n")
        write_text(run_path / "FIXES.md", "")
        max_context = int(cfg.get("writer", {}).get("max_context_files", 30))
        context = build_context(root, max_files=max_context)
        plan_phase = resolve_phase(cfg, "plan")
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
        return {
            "run_id": run_id,
            "run_dir": str(run_path),
            "plan_path": str(run_path / "PLAN.md"),
            "summary": str(parsed.plan_json.get("summary", "")),
        }
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "plan")
        raise


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
    return set_status(run_path, APPROVED)


def write(cwd: Path, run_id: str, *, mock: bool = False) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    try:
        with git_utils.log_to(run_path / "git.log"):
            require_status(status, {APPROVED}, "write")
            if not (run_path / "APPROVAL.json").exists():
                raise StateError("Missing APPROVAL.json.", stage="write")
            if not git_utils.is_repo(root):
                raise GitError(
                    "write requires a git repository because it creates an isolated worktree.",
                    stage="write",
                    suggested_next_action="Run Patchbay inside a git repository.",
                )
            cfg = load_config(root)
            branch_prefix = str(cfg.get("workflow", {}).get("default_branch_prefix", "patchbay")).strip("/")
            worktree_root = configured_worktree_root(root, cfg)
            worktree_path = worktree_root / run_id
            branch_name = f"{branch_prefix}/{run_id}"
            set_status(run_path, IMPLEMENTING)
            git_utils.create_worktree(root, worktree_path, branch_name)
            write_text(run_path / "WORKTREE_PATH", str(worktree_path) + "\n")
            set_status(run_path, IMPLEMENTING, worktree_path=str(worktree_path))
            patch, summary = _call_writer(root=root, run_path=run_path, cfg=cfg, mock=mock)
            if _writer_edits_worktree(cfg, mock, repair=False):
                final_diff = patch
            else:
                final_diff = _apply_writer_diff(worktree_path, patch)
            _validate_writer_scope(run_path, final_diff, summary)
            write_text(run_path / "IMPLEMENTATION.md", summary.rstrip() + "\n")
            write_text(run_path / "FINAL.diff", final_diff)
            return set_status(run_path, IMPLEMENTED)
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "write")
        raise


def test(cwd: Path, run_id: str) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, status = _load_run(root, run_id)
    try:
        with git_utils.log_to(run_path / "git.log"):
            require_status(status, {IMPLEMENTED}, "test")
            worktree = Path(status["worktree_path"])
            cfg = load_config(root)
            plan_json = read_json(run_path / "plan.json")
            test_phase = resolve_phase(cfg, "test")
            commands = _selected_test_commands(worktree, cfg, plan_json, test_phase)
            allowlist = allowlisted_test_commands(cfg)
            timeout = int(test_phase.get("timeout") or 900)
            set_status(run_path, TESTING)
            write_text(run_path / "TEST.log", "")
            if not commands:
                append_text(run_path / "TEST.log", "No test commands selected.\n")
                return set_status(run_path, TESTED, tests_passed=True)
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
            return set_status(run_path, TESTED, tests_passed=True)
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "test")
        raise


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
                and status.get("tests_passed")
                and not status.get("review_result")
            ):
                allowed_statuses.add(FAILED)
            require_status(status, allowed_statuses, "review")
            worktree = Path(status["worktree_path"])
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
            write_text(run_path / "REVIEW.md", raw)
            if verdict == "PASS":
                return set_status(run_path, REVIEWED_PASS, review_result="PASS")
            return set_status(
                run_path,
                REVIEWED_CHANGES_REQUESTED,
                review_result="CHANGES_REQUESTED",
            )
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "review")
        raise


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
            set_status(run_path, FIXING)
            patch, summary = _call_writer(root=root, run_path=run_path, cfg=cfg, mock=mock, repair=True)
            if _writer_edits_worktree(cfg, mock, repair=True):
                final_diff = patch
            else:
                final_diff = _apply_writer_diff(worktree, patch)
            _validate_writer_scope(run_path, final_diff, summary)
            append_text(run_path / "FIXES.md", f"## Fix iteration {iterations + 1}\n\n{summary.rstrip()}\n\n")
            write_text(run_path / "FINAL.diff", final_diff)
            return set_status(
                run_path,
                IMPLEMENTED,
                fix_iterations=iterations + 1,
                tests_passed=False,
                review_result=None,
            )
    except Exception as exc:
        _mark_failure_if_possible(run_path, exc, "fix")
        raise


def _writer_edits_worktree(cfg: dict[str, Any], mock: bool, *, repair: bool = False) -> bool:
    if mock:
        return False
    phase = "fix" if repair else "write"
    return resolve_phase(cfg, phase)["provider"] == "reasonix_cli"


def status(cwd: Path, run_id: str) -> dict[str, Any]:
    root = resolve_root(cwd)
    run_path, data = _load_run(root, run_id)
    data = dict(data)
    data["run_dir"] = str(run_path)
    data["artifacts"] = list_run_artifacts(run_path)
    return data


def diff(cwd: Path, run_id: str) -> str:
    root = resolve_root(cwd)
    run_path, data = _load_run(root, run_id)
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
            return set_status(run_path, APPLIED)
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
provider = "deepseek_api" # 可选：reasonix_cli / deepseek_api
max_context_files = 30
max_patch_attempts = 3
max_repair_iterations = 2

[deepseek]
base_url = "https://api.deepseek.com"
api_key_env = "DEEPSEEK_API_KEY"

[workflow]
require_plan_approval = true
default_branch_prefix = "patchbay"
worktree_root = "../.patchbay-worktrees"
fail_on_dirty_workspace = true
apply_to_current_workspace_only_after_review_pass = true

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
#   write:  reasonix_cli | deepseek_api | mock
#   review: codex_cli | claude_cli | gemini_cli | mock
#   fix:    (defaults to write provider) reasonix_cli | deepseek_api | mock
#   test:   no LLM executor (command allowlist only)
#   apply:  no LLM executor (git apply only)
# ---------------------------------------------------------------------------

# [phases.plan]
# provider = "claude_cli"      # claude_cli | codex_cli | gemini_cli | mock
# model = "claude-opus-4-7"

# [phases.write]
# provider = "deepseek_api"    # reasonix_cli | deepseek_api | mock
# model = "deepseek-v4-pro"

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
- “用 Claude 规划，DeepSeek 实现，Codex 审查”
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

Patchbay 是一个本地补丁编排器：任意支持 MCP 的客户端都可以作为入口，默认把规划、实现、测试、审查和应用拆成可审计阶段。当前默认角色绑定是 Claude 规划，Reasonix/DeepSeek 实现，Codex 审查；后续可以把这些槽位换成别的工具。

## 环境准备

- 登录 Claude Code，并确保 `claude` CLI 可用。
- 登录 Codex CLI，并确保 `codex` CLI 可用。
- 使用 DeepSeek API 时，设置 `DEEPSEEK_API_KEY`。

## 配置

运行：

```bash
scripts/patchbay init
cp .ai/patchbay.example.toml .ai/patchbay.toml
```

按需编辑 `.ai/patchbay.toml`，尤其是 writer provider、命令路径和测试 allowlist。

Writer 有两种实现入口：

- `reasonix_cli`：调用 Reasonix ACP coding agent（`reasonix acp`），由 Reasonix 自己的文件系统工具修改独立 worktree，Patchbay 只负责审批权限并捕获最终 `git diff`。
- `deepseek_api`：直接调用 OpenAI-compatible Chat Completions API，要求模型按 sentinel 返回 unified diff；这是 API fallback，不等同于 Agent。

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
- DeepSeek API key 缺失：设置 `DEEPSEEK_API_KEY` 或切换 writer provider。
- Reasonix 只聊天不改文件：确认 `[writer].provider = "reasonix_cli"`，且 `[commands].reasonix` 指向 `reasonix.cmd`/`reasonix`。Patchbay 会自动使用 `reasonix acp`，不要把 `deepseek_api` 当作 Reasonix Agent。
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
