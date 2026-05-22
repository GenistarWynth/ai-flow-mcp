from __future__ import annotations

from pathlib import Path

from . import git_utils


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".ai",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
}
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".zip",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".pdf",
    ".mp4",
    ".mov",
    ".sqlite",
    ".db",
}


def list_context_files(root: Path, *, max_files: int = 30) -> list[Path]:
    files: list[Path] = []
    if git_utils.is_repo(root):
        completed = git_utils.git(["ls-files"], cwd=root, check=False)
        if completed.returncode == 0:
            for line in completed.stdout.splitlines():
                candidate = root / line.strip()
                if candidate.is_file() and not _skip(candidate, root):
                    files.append(candidate)
    if not files:
        for candidate in root.rglob("*"):
            if candidate.is_file() and not _skip(candidate, root):
                files.append(candidate)
    files.sort(key=lambda path: str(path.relative_to(root)).lower())
    return files[:max_files]


def _skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in SKIP_DIRS for part in rel.parts):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def build_context(root: Path, *, max_files: int = 30, max_chars_per_file: int = 5000) -> str:
    lines = ["# Repository Context", "", f"Root: {root}", ""]
    files = list_context_files(root, max_files=max_files)
    lines.append("## Files")
    if not files:
        lines.append("No context files found.")
        return "\n".join(lines) + "\n"
    for path in files:
        rel = path.relative_to(root).as_posix()
        lines.extend(["", f"### {rel}"])
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            lines.append("[Skipped: not UTF-8 text]")
            continue
        if len(text) > max_chars_per_file:
            text = text[:max_chars_per_file] + "\n[Truncated]\n"
        lines.extend(["```", text.rstrip(), "```"])
    return "\n".join(lines) + "\n"
