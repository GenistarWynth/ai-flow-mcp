from __future__ import annotations

from typing import Any


def skill_contract_summary() -> dict[str, Any]:
    return {
        "kind": "progressive-skill",
        "entrypoint": "skills/patchbay/SKILL.md",
        "references": [
            {
                "path": "skills/patchbay/references/install.md",
                "purpose": "Setup, host registration, local-only install, Skill install, and doctor guidance.",
            },
            {
                "path": "skills/patchbay/references/agent-contract.md",
                "purpose": "Structured actions, action_groups, gate diagnosis, failure recovery, background jobs, and economy evidence.",
            },
        ],
        "commands": [
            "patchbay skill doctor codex --json",
            "patchbay skill print codex",
        ],
        "structured_fields": [
            "actions[]",
            "action_groups[]",
            "gate_diagnosis",
            "failure_recovery",
            "routing_evidence",
            "efficiency_summary",
        ],
        "local_only_supported": True,
        "no_mcp_prompts": [
            "no MCP",
            "use Chrome Skill instead of MCP",
            "不要用这个MCP",
            "不走 MCP",
            "走本地模式",
            "只用本地工具",
        ],
    }
