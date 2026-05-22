# Patchbay MCP

[中文说明](README.zh-CN.md)

Patchbay is a local patch orchestration server for teams of coding agents. Any MCP-capable client can be the front door: Codex Desktop, Claude Desktop, Claude Code, Codex CLI, Gemini CLI, or another host that can call MCP tools.

The default workflow uses Claude Code as the read-only planner, Reasonix ACP or a DeepSeek-compatible API as the writer, local test commands as factual verification, and Codex CLI as the read-only reviewer. Those role bindings are configuration, not the product boundary.

## What It Provides

- CLI workflow: `plan`, `approve`, `write`, `test`, `review`, `fix`, `status`, `diff`, `apply`, `cleanup`.
- MCP tools: `patchbay_plan`, `patchbay_approve`, `patchbay_write`, `patchbay_test`, `patchbay_review`, `patchbay_fix`, `patchbay_status`, `patchbay_diff`, `patchbay_apply`.
- Legacy MCP aliases: `ai_flow_*`.
- Isolated git worktrees by default.
- File-backed run artifacts under `.ai/runs/<run_id>/`.
- Human approval gate before implementation.
- Patch safety checks and read-only reviewer verification.

## Quick Start

```bash
python scripts/patchbay init
cp .ai/patchbay.example.toml .ai/patchbay.toml
```

Edit `.ai/patchbay.toml` for your local CLI commands, model names, provider, and test allowlist. Do not commit `.ai/patchbay.toml`; it is intentionally ignored.

The old `scripts/ai-flow` command and `.ai/ai-flow.toml` config still work as compatibility aliases.

## CLI Usage

```bash
python scripts/patchbay plan --task "..."
python scripts/patchbay approve <run_id>
python scripts/patchbay write <run_id>
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id>
python scripts/patchbay apply <run_id>
```

Mock mode can validate the workflow without model credentials:

```bash
python scripts/patchbay plan --task "mock smoke" --mock
python scripts/patchbay write <run_id> --mock
python scripts/patchbay review <run_id> --mock
```

## MCP Install

From the repository root:

```bash
codex mcp add patchbay -- python scripts/patchbay_mcp_server.py
```

Use the equivalent MCP server registration command for Claude Desktop, Claude Code, Gemini CLI, or any other MCP host.

## Configuration

The public example config lives at `.ai/patchbay.example.toml`. It contains environment variable names only, not API keys.

Supported writer providers:

- `reasonix_cli`: uses `reasonix acp` as a real coding agent.
- `deepseek_api`: direct OpenAI-compatible Chat Completions fallback that returns a patch.

## Security

- `.ai/patchbay.toml`, `.ai/runs/`, `.ai/logs/`, `.ai/worktrees/`, and `.patchbay-worktrees/` are ignored.
- Writer patches are rejected for `.git`, `.env*`, secret-like paths, absolute paths, and path traversal.
- Reasonix ACP execute permissions are rejected; unknown permission requests are conservative.
- Reviewer runs read-only and Patchbay checks that review did not mutate the worktree.
- Logs redact environment-derived secrets and adapter-known API keys.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
