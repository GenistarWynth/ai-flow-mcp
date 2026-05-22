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
    """Extract file paths from a git-framed unified diff.

    Only ``diff --git`` sections are parsed.  Within each section the *header
    region* (before the first ``@@ `` hunk header) the ``diff --git`` line and any
    ``rename from`` / ``rename to`` lines are inspected for paths.  ``---`` / ``+++``
    header lines are skipped — in git-framed diffs they always repeat the
    ``diff --git`` paths.  Lines inside hunks are never treated as path-bearing,
    even if their body text happens to look like diff headers.
    Bare unified diffs (no ``diff --git``) return an empty list.
    """
    result: list[str] = []
    seen: set[str] = set()
    in_section = False
    in_header = False

    def _add(path: str) -> None:
        if path and path not in {"/dev/null", "dev/null"} and path not in seen:
            seen.add(path)
            result.append(path)

    for raw_line in patch.splitlines():
        # ── section start ──────────────────────────────────────────────
        if raw_line.startswith("diff --git "):
            in_section = True
            in_header = True
            parts = raw_line.split()
            if len(parts) >= 4:
                _add(_strip_diff_prefix(parts[2]))
                _add(_strip_diff_prefix(parts[3]))
            continue

        if not in_section:
            continue

        # ── transition from header region to hunk body ─────────────────
        if in_header and raw_line.startswith("@@ "):
            in_header = False
            continue

        # ── header-region path lines ───────────────────────────────────
        # In git-framed diffs the --- / +++ lines are always redundant
        # with the ``diff --git a/X b/X`` line, so we skip them and only
        # collect rename source/target which add genuinely new paths.
        if in_header:
            if raw_line.startswith("rename from ") or raw_line.startswith("rename to "):
                _add(_strip_diff_prefix(raw_line.split(" ", 2)[2]))

    return result


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

    # Reject bare unified diffs that lack a ``diff --git`` header.
    # Patchbay writer prompts and git output always emit git-framed diffs,
    # so bare ``---``/``+++`` headers are ambiguous and unsupported.
    has_diffgit = False
    has_bare_header = False
    for raw_line in patch.splitlines():
        if raw_line.startswith("diff --git "):
            has_diffgit = True
            break
        if raw_line.startswith("--- ") or raw_line.startswith("+++ "):
            has_bare_header = True
    if not has_diffgit and has_bare_header:
        raise SafetyError(
            "Patch must be a git-framed unified diff (starting with 'diff --git'). "
            "Bare unified diffs with only ---/+++ file headers are ambiguous "
            "and not supported. Regenerate the patch as a git-framed diff.",
            stage="safety",
            suggested_next_action=(
                "Use 'git diff' or 'git format-patch' to produce a git-framed diff "
                "that includes 'diff --git' headers, or ask Patchbay to regenerate the patch."
            ),
        )

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
            suggested_next_action="Add the command to .ai/patchbay.toml commands_allowlist.test after reviewing it.",
        )
