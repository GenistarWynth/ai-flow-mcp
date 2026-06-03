---
name: patchbay
description: Use Patchbay for multi-agent/multi-model coding workflows, Patchbay setup/install, Codex Skill installation, local-only/no-MCP Patchbay work, "走多模型流程", "multi-agent workflow", or gated plan/write/test/review/fix flows where one agent plans, another writes, tests run locally, and another reviews before apply.
---

# Patchbay

Patchbay is a gated local patch orchestrator. Use it instead of direct edits when the user asks for Patchbay, a multi-agent/multi-model workflow, Patchbay setup, or a Patchbay Skill/local-only flow.

## Entry Choice

- If `patchbay_*` MCP tools are available and the user has not chosen local-only work, prefer `patchbay_agent` for conversational setup, start, resume, status, readiness, routing, gate-status, and background turns.
- If MCP is unavailable or the user asks not to use MCP, use the local CLI path. Do not call `patchbay_*` MCP tools after explicit no-MCP phrasing.
- Read `references/install.md` only when installing, debugging setup, Skill drift, host registration, or doctor output.
- Read `references/agent-contract.md` only when rendering/handling structured Agent responses, desktop controls, background jobs, economy routing evidence, failure recovery, no-MCP preferences, or action grouping.

## Conversational Agent Path

Use the conversational Agent path whenever possible:

```bash
scripts/patchbay agent message "<user task>" --background --json
scripts/patchbay context <run_id>
scripts/patchbay events <run_id>
```

For MCP, the equivalent is `patchbay_agent` followed by `patchbay_context` or `patchbay_events`.

Render structured `actions[]`, `action_groups[]`, `routing`, `routing_evidence`, `efficiency_summary`, `gate_diagnosis`, and `failure_recovery` when they are present. Prefer these fields over parsing prose. For simple high-volume implementation and repair work, confirm whether write/fix are using the cheaper economy route before approving long work.

## Required Gates

Patchbay remains gated even in conversational mode:

1. Start with a plan and show the generated plan summary.
2. Require explicit plan approval before implementation.
3. Run write, test, and review after approval.
4. If review returns `CHANGES_REQUESTED`, run at most two fix/test/review loops.
5. Only after review is `PASS` and tests are not skipped may you ask whether to apply.
6. Never apply without a separate explicit apply confirmation.

Useful explicit phase commands:

```bash
scripts/patchbay plan --task "<user task>"
scripts/patchbay approve <run_id>
scripts/patchbay write <run_id>
scripts/patchbay test <run_id>
scripts/patchbay review <run_id>
scripts/patchbay fix <run_id>
scripts/patchbay apply <run_id>
```

## Local-Only And Skill-Only Mode

If the user says MCP keeps asking for confirmation, asks to avoid MCP, asks for Chrome/browser Skill instead of MCP, or says `不要用这个MCP`, `不走 MCP`, `走本地模式`, or `只用本地工具`, stay on the local CLI/Skill path:

```bash
scripts/patchbay setup --no-mcp --json
scripts/patchbay doctor --local-only --json
scripts/patchbay agent message "patchbay setup without MCP" --json
scripts/patchbay agent message "readiness without MCP" --json
scripts/patchbay agent message "走本地模式，不走 MCP" --json
scripts/patchbay agent message "install Codex Skill" --json
```

## Economy Routing

Patchbay's default cost profile keeps stronger supervision in plan/review and sends high-volume write/fix work to the cheaper economy route, typically Reasonix/DeepSeek. Use these prompts or commands when the user asks for low-cost writer/fixer work:

```bash
scripts/patchbay config profile apply economy
scripts/patchbay agent message "apply economy profile" --json
scripts/patchbay agent message "configure reasonix command" --json
scripts/patchbay agent message "configure DeepSeek provider" --json
scripts/patchbay agent message "简单 writer/fix 用 DeepSeek 省钱" --json
```

Inspect `routing_evidence` and `efficiency_summary` before claiming economy routing is verified by observed usage.

## Background And Permission Phrases

Use `--background` for long planning or implementation turns and poll context/events. If a concrete `run_id` is already selected, unattended phrases such as `don't ask me`, `full access`, `不要问我`, `所有权限都给你`, `无需向我确认`, or `完全访问权限` may count as plan approval for that run and start background write/test/review autopilot. These phrases never authorize final apply; apply still requires explicit confirmation after tests and review pass.
