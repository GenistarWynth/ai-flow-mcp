from __future__ import annotations

import re
from pathlib import PurePosixPath

from .errors import SafetyError


ABSOLUTE_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
SECRET_NAME_RE = re.compile(r"(private[_-]?key|token|credential|secret)", re.IGNORECASE)


def _strip_diff_prefix(path: str) -> str:
    path = path.strip().strip('"').replace("\\", "/")
    if path in {"/dev/null", "dev/null"}:
        return path
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def paths_from_patch(patch: str) -> list[str]:
    paths: list[str] = []
    for raw_line in patch.splitlines():
        line = raw_line.strip()
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                paths.extend([_strip_diff_prefix(parts[2]), _strip_diff_prefix(parts[3])])
        elif line.startswith("--- ") or line.startswith("+++ "):
            value = line[4:].split("\t", 1)[0]
            paths.append(_strip_diff_prefix(value))
        elif line.startswith("rename from ") or line.startswith("rename to "):
            paths.append(_strip_diff_prefix(line.split(" ", 2)[2]))
    return [path for path in paths if path and path not in {"/dev/null", "dev/null"}]


def validate_repo_relative_path(path: str) -> None:
    normalized = path.replace("\\", "/").strip()
    if normalized.startswith("/") or ABSOLUTE_WINDOWS_RE.match(normalized):
        raise SafetyError(f"Patch contains absolute path: {path}", stage="safety")
    pure = PurePosixPath(normalized)
    if any(part == ".." for part in pure.parts):
        raise SafetyError(f"Patch contains path traversal: {path}", stage="safety")
    if any(part == ".git" for part in pure.parts):
        raise SafetyError(f"Patch modifies .git: {path}", stage="safety")
    name = pure.name
    if name == ".env" or name.startswith(".env."):
        raise SafetyError(f"Patch modifies environment file: {path}", stage="safety")
    if SECRET_NAME_RE.search(normalized):
        raise SafetyError(f"Patch touches a secret-like path: {path}", stage="safety")


def validate_patch_safety(patch: str) -> None:
    if not patch.strip():
        raise SafetyError("Patch is empty.", stage="safety")
    paths = paths_from_patch(patch)
    if not paths:
        raise SafetyError("Patch does not contain recognizable git diff paths.", stage="safety")
    for path in paths:
        validate_repo_relative_path(path)


def ensure_command_allowed(command: str, allowlist: set[str]) -> None:
    normalized = command.strip()
    if normalized not in allowlist:
        raise SafetyError(
            f"Test command is not allowlisted: {command}",
            stage="test",
            suggested_next_action="Add the command to .ai/ai-flow.toml commands_allowlist.test after reviewing it.",
        )
