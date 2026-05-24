# Patchbay — Project Roadmap & Index

## Overview

Patchbay is a local MCP-friendly patch orchestrator for teams of coding agents.
**Any MCP-capable host** can be the interaction entry point: Codex Desktop, Codex
CLI, Claude Desktop, Claude Code, Gemini CLI, or any other MCP host that can call
MCP tools. The orchestrator splits each task into auditable phases (plan, write,
test, review, fix, apply) with a human approval gate before implementation and
isolated git worktrees per run.

## Current Architecture (shipped)

Each workflow phase can be independently bound to a provider and model in
`.ai/patchbay.toml` under `[phases.<phase>]`:

| Phase | Supported providers | Default |
|-------|-------------------|---------|
| **plan** | `claude_cli`, `codex_cli`, `gemini_cli`, `mock` | `claude_cli` |
| **write** | `reasonix_cli`, `mock` | `reasonix_cli` |
| **review** | `codex_cli`, `claude_cli`, `gemini_cli`, `mock` | `codex_cli` |
| **fix** | same as write (inherits write provider) | `reasonix_cli` |

- There is no HTTP API adapter provider. The previous HTTP adapter has been
  **removed**.
- The **Reasonix ACP** (`reasonix_cli`) uses `reasonix acp` as the coding agent.
  Patchbay manages the isolated worktree; Reasonix edits files inside it using its
  native filesystem tools. Patchbay captures the final `git diff`.
- Legacy `[models]`, `[commands]`, and `[writer].provider` config keys remain
  supported as defaults for phases that are not explicitly configured.
- Legacy `scripts/ai-flow` entry point and `.ai/ai-flow.toml` config file are
  retained as compatibility aliases for `scripts/patchbay` and `.ai/patchbay.toml`.
- MCP tools are exposed as `patchbay_*` with `ai_flow_*` legacy aliases.

## Workflow

```
plan → approve → write → test → review → (fix → test → review) → apply → cleanup
```

1. **plan** — Read-only analysis by the configured planner. Produces `PLAN.md`
   and `plan.json`. No code is modified.
2. **approve** — Human reviews and approves the plan. The `write` phase is
   gated on this approval.
3. **write** — Creates an isolated git worktree. The writer implements the
   approved plan inside the worktree. Saves `FINAL.diff`.
4. **test** — Runs test commands (from plan, config, or auto-detected) inside
   the worktree. Logs to `TEST.log`.
5. **review** — Read-only review by the configured reviewer. Produces `REVIEW.md`
   with a `PASS` or `CHANGES_REQUESTED` verdict.
6. **fix** — If review returns `CHANGES_REQUESTED`, the writer addresses the
   specific issues. Up to 2 fix rounds.
7. **apply** — Applies `FINAL.diff` to the current workspace. Only allowed after
   tests pass and review returns `PASS`.
8. **cleanup** — Removes the worktree and run artifacts.

All artifacts live under `.ai/runs/<run_id>/`. The planner, reviewer, and apply
phases enforce read-only / safety constraints; the writer operates inside an
isolated worktree. Patchbay rejects patches targeting `.git/`, `.env*`,
secret-like files, absolute paths, and path-traversal patterns.

## Status

**Shipped and stable.** The full CLI + MCP workflow, per-phase provider
configuration, mock mode, and safety enforcement are implemented.

**Recently shipped (v0.1.0 → current):**
- **Unified handoff context**: `patchbay context <run_id>` and `patchbay_context` synthesize status, gate state, next safe action, provider trail, artifacts, and timeline into one cross-host resume payload.
- **Cross-host visibility**: `events.jsonl` per run + `patchbay events` CLI + `patchbay_events` MCP tool. Any host can inspect what every phase/agent did, including provider, model, action, and timestamps.
- **Free phase-to-provider routing**: Any configured provider that advertises a role (plan/write/review/fix) can be assigned to any phase. Unsupported assignments fail with a clear error.
- **Interactive configuration**: `patchbay config` wizard + `patchbay config set k v` + `patchbay doctor`. No hand-editing TOML required.
- **Automated MCP registration**: `patchbay mcp install <host>` writes host-specific registration for Codex, Claude Code, Claude Desktop, and Gemini CLI.
- **npx-style installation**: `uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay-mcp --root <repo>` via `pyproject.toml` console_scripts.
- **Gate enforcement events**: Approval and apply-gate decisions are recorded in the event log.

The project is actively maintained.

## Custom Providers

User-defined CLI provider entries (`[providers.<id>]` TOML blocks) are implemented
for the current runtime via `patchbay config provider add-cli`. The broader design
continues to track additional modes and stronger provider-specific controls:

- Four execution modes: `cli_stdin`, `cli_stdout`, `http_api`, `acp`
- Role capability mask (a single provider can be registered for planner, writer,
  reviewer, fixer, or any combination)
- Output parsing contract (sentinel markers, JSON paths)
- Safety constraints (path allowlists, deny patterns, execution blocking)

See [docs/custom-providers-plan.md](docs/custom-providers-plan.md) for the current
CLI baseline and the remaining HTTP/ACP roadmap.

## Pointers

- [README.md](README.md) — English readme, quick start, config reference
- [README.zh-CN.md](README.zh-CN.md) — Chinese readme
- [docs/patchbay.md](docs/patchbay.md) — Full documentation (Chinese)
- [docs/custom-providers-plan.md](docs/custom-providers-plan.md) — Custom providers baseline and roadmap
- [AGENTS.md](AGENTS.md) — Agent instruction block for MCP hosts
