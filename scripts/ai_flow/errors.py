from __future__ import annotations


class AiFlowError(RuntimeError):
    """Base class for expected Patchbay errors."""

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        suggested_next_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.suggested_next_action = suggested_next_action


class SafetyError(AiFlowError):
    """Raised when a patch, command, or path violates workflow rules."""


class StateError(AiFlowError):
    """Raised when a command is invalid for the current run state."""


class GitError(AiFlowError):
    """Raised for git command failures."""
