from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import subprocess
from pathlib import Path
from typing import Iterator

from .artifacts import append_text, now_iso
from .errors import GitError
from .runner import redact


IGNORED_DIRTY_PREFIXES = (
    ".ai/runs/",
    ".ai/logs/",
    ".ai/worktrees/",
)


_GIT_LOG_PATH: ContextVar[Path | None] = ContextVar("ai_flow_git_log_path", default=None)


@contextmanager
def log_to(path: Path) -> Iterator[None]:
    token = _GIT_LOG_PATH.set(path)
    try:
        yield
    finally:
        _GIT_LOG_PATH.reset(token)


def git(
    args: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    _log_git(args=args, cwd=cwd, completed=completed)
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise GitError(
            f"git {' '.join(args)} failed: {detail}",
            stage="git",
            suggested_next_action="Check that the target directory is a valid git repository.",
        )
    return completed


def _log_git(*, args: list[str], cwd: Path, completed: subprocess.CompletedProcess[str]) -> None:
    log_path = _GIT_LOG_PATH.get()
    if log_path is None:
        return
    append_text(
        log_path,
        "\n".join(
            [
                f"## Git Command {now_iso()}",
                "",
                f"cwd: {cwd}",
                f"command: {redact('git ' + ' '.join(args))}",
                f"exit_code: {completed.returncode}",
                "",
                "### stdout",
                "",
                redact(completed.stdout or "").rstrip(),
                "",
                "### stderr",
                "",
                redact(completed.stderr or "").rstrip(),
                "",
            ]
        ),
    )


def repo_root(start: Path) -> Path:
    completed = git(["rev-parse", "--show-toplevel"], cwd=start)
    return Path(completed.stdout.strip()).resolve()


def is_repo(start: Path) -> bool:
    completed = git(["rev-parse", "--is-inside-work-tree"], cwd=start, check=False)
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def current_commit(root: Path) -> str | None:
    completed = git(["rev-parse", "HEAD"], cwd=root, check=False)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def status_porcelain(root: Path) -> list[str]:
    completed = git(["status", "--porcelain"], cwd=root)
    return [line for line in completed.stdout.splitlines() if line.strip()]


def dirty_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    return value.replace("\\", "/").strip()


def filtered_dirty_lines(root: Path) -> list[str]:
    result: list[str] = []
    for line in status_porcelain(root):
        path = dirty_path(line)
        if any(path.startswith(prefix) for prefix in IGNORED_DIRTY_PREFIXES):
            continue
        result.append(line)
    return result


def dirty_paths(root: Path) -> list[str]:
    return [dirty_path(line) for line in status_porcelain(root)]


def ensure_clean(root: Path) -> None:
    dirty = filtered_dirty_lines(root)
    if dirty:
        raise GitError(
            "Workspace is not clean:\n" + "\n".join(dirty),
            stage="git",
            suggested_next_action="Commit, stash, or remove unrelated workspace changes before continuing.",
        )


def create_worktree(root: Path, worktree_path: Path, branch_name: str, base_ref: str = "HEAD") -> None:
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        raise GitError(
            f"Worktree path already exists: {worktree_path}",
            stage="write",
            suggested_next_action="Run cleanup for this run or choose a new run id.",
        )
    git(["worktree", "add", "-b", branch_name, str(worktree_path), base_ref], cwd=root)


def remove_worktree(root: Path, worktree_path: Path) -> None:
    if worktree_path.exists():
        git(["worktree", "remove", "--force", str(worktree_path)], cwd=root)


def diff(root: Path) -> str:
    completed = git(["diff", "--binary", "HEAD"], cwd=root)
    return completed.stdout


def apply_diff(
    root: Path,
    patch: str,
    *,
    index: bool = False,
    recount: bool = False,
    threeway: bool = False,
    ignore_space_change: bool = False,
) -> None:
    args = ["apply", "--whitespace=nowarn"]
    if index:
        args.append("--index")
    if recount:
        args.append("--recount")
    if threeway:
        args.append("--3way")
    if ignore_space_change:
        args.append("--ignore-space-change")
    args.append("-")
    git(args, cwd=root, input_text=patch)


def add_paths(root: Path, paths: list[str]) -> None:
    if paths:
        git(["add", "--", *paths], cwd=root)


def add_all(root: Path) -> None:
    git(["add", "--all"], cwd=root)


def diff_name_only(root: Path) -> list[str]:
    completed = git(["diff", "--name-only"], cwd=root)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]
