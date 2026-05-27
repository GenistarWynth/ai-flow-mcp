---
name: patchbay
description: Use Patchbay for multi-agent/multi-model coding workflows when the user asks to use Patchbay, "走多模型流程", "multi-agent workflow", model-orchestrated plan/write/review/fix, or a gated MCP workflow where one agent plans, another writes, tests run locally, and another reviews before apply.
---

# Patchbay

Patchbay is a gated local patch orchestrator. Use it instead of editing files directly when this skill triggers.

## Required Workflow

1. Start with a plan:

```bash
scripts/patchbay plan --task "<user task>"
```

2. Read `.ai/runs/<run_id>/PLAN.md` and show the plan summary to the user.

3. Stop for explicit user approval before implementation.

4. After approval, run:

```bash
scripts/patchbay approve <run_id>
scripts/patchbay write <run_id>
scripts/patchbay test <run_id>
scripts/patchbay review <run_id>
```

5. If review returns `CHANGES_REQUESTED`, run at most two fix loops:

```bash
scripts/patchbay fix <run_id>
scripts/patchbay test <run_id>
scripts/patchbay review <run_id>
```

6. Only after review is `PASS` and tests are not skipped may you ask whether to apply:

```bash
scripts/patchbay apply <run_id>
```

Never apply without explicit user confirmation.

## Preferred MCP Tools

If `patchbay_*` MCP tools are available, prefer them over shell commands:

- `patchbay_agent` for conversational start/resume/advance while preserving gates.
- `patchbay_plan`, `patchbay_approve`, `patchbay_write`, `patchbay_test`, `patchbay_review`, `patchbay_fix`, `patchbay_apply` for explicit phase control.
- `patchbay_context` for cross-host handoff status, next safe action, timeline, gate state, artifacts, and provider trail.
- `patchbay_events` and `patchbay_trace` for focused diagnostics.

Legacy `ai_flow_*` aliases are compatible, but use `patchbay_*` names for new work.

## Installation Reference

For setup details, read `references/install.md` only when installing or debugging setup.
