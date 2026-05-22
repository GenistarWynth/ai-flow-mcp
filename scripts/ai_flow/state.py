from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import now_iso, read_json, write_json
from .errors import StateError


NEW = "NEW"
PLANNED = "PLANNED"
APPROVED = "APPROVED"
IMPLEMENTING = "IMPLEMENTING"
IMPLEMENTED = "IMPLEMENTED"
TESTING = "TESTING"
TESTED = "TESTED"
REVIEWING = "REVIEWING"
REVIEWED_PASS = "REVIEWED_PASS"
REVIEWED_CHANGES_REQUESTED = "REVIEWED_CHANGES_REQUESTED"
FIXING = "FIXING"
READY_TO_APPLY = "READY_TO_APPLY"
APPLIED = "APPLIED"
FAILED = "FAILED"


STATUS_FILE = "STATUS.json"


def status_path(run_dir: Path) -> Path:
    return run_dir / STATUS_FILE


def create_status(
    run_dir: Path,
    *,
    run_id: str,
    task: str,
    repo_root: Path,
    config_path: Path,
    base_commit: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "run_id": run_id,
        "status": NEW,
        "task": task,
        "repo_root": str(repo_root),
        "config_path": str(config_path),
        "base_commit": base_commit,
        "worktree_path": None,
        "tests_passed": False,
        "review_result": None,
        "fix_iterations": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "error": None,
        "stage": None,
        "suggested_next_action": None,
    }
    save_status(run_dir, data)
    return data


def load_status(run_dir: Path) -> dict[str, Any]:
    path = status_path(run_dir)
    if not path.exists():
        raise StateError(f"Missing STATUS.json for run at {run_dir}", stage="state")
    return read_json(path)


def save_status(run_dir: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = now_iso()
    write_json(status_path(run_dir), data)


def set_status(run_dir: Path, status: str, **updates: Any) -> dict[str, Any]:
    data = load_status(run_dir)
    data.update(updates)
    data["status"] = status
    if status != FAILED:
        data["error"] = None
        data["stage"] = None
        data["suggested_next_action"] = None
    save_status(run_dir, data)
    return data


def mark_failed(
    run_dir: Path,
    *,
    error: str,
    stage: str,
    suggested_next_action: str,
) -> dict[str, Any]:
    data = load_status(run_dir)
    data.update(
        {
            "status": FAILED,
            "error": error,
            "stage": stage,
            "suggested_next_action": suggested_next_action,
        }
    )
    save_status(run_dir, data)
    return data


def require_status(data: dict[str, Any], allowed: set[str], command: str) -> None:
    current = str(data.get("status"))
    if current not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise StateError(
            f"`{command}` cannot run while status is {current}; expected one of: {allowed_text}",
            stage=command,
            suggested_next_action="Run `scripts/ai-flow status <run_id>` and continue from the valid next command.",
        )
