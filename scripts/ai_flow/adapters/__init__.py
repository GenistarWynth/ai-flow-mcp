from __future__ import annotations

from typing import Any, Callable

from .claude_planner import run_claude_planner, run_mock_planner
from .claude_reviewer import run_claude_reviewer
from .codex_planner import run_codex_planner
from .codex_reviewer import run_codex_reviewer, run_mock_reviewer
from .deepseek_writer import run_deepseek_writer
from .gemini_planner import run_gemini_planner
from .gemini_reviewer import run_gemini_reviewer
from .mock_writer import run_mock_writer
from .reasonix_writer import run_reasonix_writer

# ---------------------------------------------------------------------------
# Provider registries — keyed by provider id string.
# Each value is a callable whose signature matches the phase role.
# ---------------------------------------------------------------------------

PLANNERS: dict[str, Callable[..., Any]] = {
    "claude_cli": run_claude_planner,
    "codex_cli": run_codex_planner,
    "gemini_cli": run_gemini_planner,
    "mock": run_mock_planner,
}

WRITERS: dict[str, Callable[..., Any]] = {
    "deepseek_api": run_deepseek_writer,
    "reasonix_cli": run_reasonix_writer,
    "mock": run_mock_writer,
}

REVIEWERS: dict[str, Callable[..., Any]] = {
    "claude_cli": run_claude_reviewer,
    "codex_cli": run_codex_reviewer,
    "gemini_cli": run_gemini_reviewer,
    "mock": run_mock_reviewer,
}

# FIXERS reuses the writer registry by default; individual fix providers can be
# added here later without changing service dispatch.
FIXERS: dict[str, Callable[..., Any]] = {
    "deepseek_api": run_deepseek_writer,
    "reasonix_cli": run_reasonix_writer,
    "mock": run_mock_writer,
}

# ---------------------------------------------------------------------------
# Legacy per-function exports — kept for backward-compatible direct imports.
# ---------------------------------------------------------------------------

__all__ = [
    "PLANNERS",
    "WRITERS",
    "REVIEWERS",
    "FIXERS",
    "run_claude_planner",
    "run_claude_reviewer",
    "run_codex_planner",
    "run_gemini_planner",
    "run_gemini_reviewer",
    "run_mock_planner",
    "run_deepseek_writer",
    "run_reasonix_writer",
    "run_mock_writer",
    "run_codex_reviewer",
    "run_mock_reviewer",
]
