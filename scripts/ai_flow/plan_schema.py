from __future__ import annotations

from typing import Any

from .errors import AiFlowError


REQUIRED_KEYS = {
    "version",
    "summary",
    "requires_user_decision",
    "questions",
    "assumptions",
    "affected_files",
    "implementation_steps",
    "test_commands",
    "lint_commands",
    "typecheck_commands",
    "acceptance_criteria",
    "risks",
    "out_of_scope",
    "review_checklist",
}


def validate_plan_json(data: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_KEYS - set(data))
    if missing:
        raise AiFlowError(
            "plan.json is missing required keys: " + ", ".join(missing),
            stage="plan",
        )
    if data.get("version") != 1:
        raise AiFlowError("plan.json version must be 1.", stage="plan")
    if not isinstance(data.get("affected_files"), list):
        raise AiFlowError("plan.json affected_files must be a list.", stage="plan")
    if not isinstance(data.get("implementation_steps"), list):
        raise AiFlowError("plan.json implementation_steps must be a list.", stage="plan")


def empty_plan(task: str) -> dict[str, Any]:
    return {
        "version": 1,
        "summary": f"Mock plan for: {task}",
        "requires_user_decision": False,
        "questions": [],
        "assumptions": ["Mock mode is being used; no external model was called."],
        "affected_files": [
            {
                "path": "AI_FLOW_MOCK_OUTPUT.md",
                "operation": "create",
                "reason": "Provide a deterministic mock implementation artifact.",
            }
        ],
        "implementation_steps": [
            {
                "id": "S1",
                "description": "Create a deterministic mock output file.",
                "files": ["AI_FLOW_MOCK_OUTPUT.md"],
                "verification": ["Confirm the file exists and contains the task text."],
            }
        ],
        "test_commands": [],
        "lint_commands": [],
        "typecheck_commands": [],
        "acceptance_criteria": [
            "Mock write creates a patch in an isolated worktree.",
            "Review can pass without external model access.",
        ],
        "risks": [],
        "out_of_scope": ["Real provider behavior is not exercised in mock mode."],
        "review_checklist": ["Patch is scoped to the mock output file."],
    }
