from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AI_DIR = ".ai"
RUNS_DIR = "runs"
LOGS_DIR = "logs"
WORKTREES_DIR = "worktrees"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str, limit: int = 52) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        slug = "task"
    return slug[:limit].strip("-") or "task"


def new_run_id(task: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{slugify(task)}"


def ai_dir(root: Path) -> Path:
    return root / AI_DIR


def runs_dir(root: Path) -> Path:
    return ai_dir(root) / RUNS_DIR


def logs_dir(root: Path) -> Path:
    return ai_dir(root) / LOGS_DIR


def default_worktrees_dir(root: Path) -> Path:
    return ai_dir(root) / WORKTREES_DIR


def run_dir(root: Path, run_id: str) -> Path:
    return runs_dir(root) / run_id


def ensure_layout(root: Path) -> None:
    runs_dir(root).mkdir(parents=True, exist_ok=True)
    logs_dir(root).mkdir(parents=True, exist_ok=True)


def read_text(path: Path, default: str | None = None) -> str:
    if default is not None and not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write_text(temp_path, payload)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def find_run_dir(start: Path, run_id: str) -> Path:
    current = start.resolve()
    candidates: list[Path] = []
    for parent in [current, *current.parents]:
        candidates.append(run_dir(parent, run_id))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return run_dir(current, run_id)


def list_run_artifacts(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(child.name for child in path.iterdir() if child.is_file())
