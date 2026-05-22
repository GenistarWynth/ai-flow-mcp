# ai-flow MCP

Local multi-agent coding workflow for Codex Desktop.

`ai-flow` orchestrates Claude Code as a read-only planner, Reasonix ACP or a DeepSeek-compatible API as the implementation writer, local test commands as factual verification, and Codex CLI as a read-only reviewer. The same workflow is exposed through an MCP server.

## What It Provides

- CLI workflow: `plan`, `approve`, `write`, `test`, `review`, `fix`, `status`, `diff`, `apply`, `cleanup`.
- MCP tools: `ai_flow_plan`, `ai_flow_approve`, `ai_flow_write`, `ai_flow_test`, `ai_flow_review`, `ai_flow_fix`, `ai_flow_status`, `ai_flow_diff`, `ai_flow_apply`.
- Isolated git worktrees by default.
- File-backed run artifacts under `.ai/runs/<run_id>/`.
- Human approval gate before implementation.
- Patch safety checks and read-only reviewer verification.

## Quick Start

```bash
python scripts/ai-flow init
cp .ai/ai-flow.example.toml .ai/ai-flow.toml
```

Edit `.ai/ai-flow.toml` for your local CLI commands, model names, provider, and test allowlist. Do not commit `.ai/ai-flow.toml`; it is intentionally ignored.

## CLI Usage

```bash
python scripts/ai-flow plan --task "..."
python scripts/ai-flow approve <run_id>
python scripts/ai-flow write <run_id>
python scripts/ai-flow test <run_id>
python scripts/ai-flow review <run_id>
python scripts/ai-flow apply <run_id>
```

Mock mode can validate the workflow without model credentials:

```bash
python scripts/ai-flow plan --task "mock smoke" --mock
python scripts/ai-flow write <run_id> --mock
python scripts/ai-flow review <run_id> --mock
```

## MCP Install

From the repository root:

```bash
codex mcp add ai-flow -- python scripts/ai_flow/mcp_server.py
```

Then restart or refresh Codex Desktop so it reloads MCP servers.

## Configuration

The public example config lives at `.ai/ai-flow.example.toml`. It contains environment variable names only, not API keys.

Supported writer providers:

- `reasonix_cli`: uses `reasonix acp` as a real coding agent.
- `deepseek_api`: direct OpenAI-compatible Chat Completions fallback that returns a patch.

## Security

- `.ai/ai-flow.toml`, `.ai/runs/`, `.ai/logs/`, `.ai/worktrees/`, and `.ai-flow-worktrees/` are ignored.
- Writer patches are rejected for `.git`, `.env*`, secret-like paths, absolute paths, and path traversal.
- Reasonix ACP execute permissions are rejected; unknown permission requests are conservative.
- Reviewer runs read-only and ai-flow checks that review did not mutate the worktree.
- Logs redact environment-derived secrets and adapter-known API keys.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
