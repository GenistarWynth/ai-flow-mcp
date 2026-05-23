# Patchbay MCP

[中文说明](README.zh-CN.md)

Patchbay is a local patch orchestration server for teams of coding agents. Any MCP-capable client can be the front door: Codex Desktop, Claude Desktop, Claude Code, Codex CLI, Gemini CLI, or another host that can call MCP tools.

The default workflow uses Claude Code as the read-only planner, Reasonix ACP as the default Agent writer, local test commands as factual verification, and Codex CLI as the read-only reviewer. Those role bindings are configuration, not the product boundary.

## Per-Phase Executors

Any configured provider that advertises the required role (plan/write/review/fix) can be assigned to any phase — no code changes needed. Unsupported assignments fail with a clear error at resolution time.

Each workflow phase can be independently bound to a provider and model in `.ai/patchbay.toml`:

```toml
[phases.plan]
provider = "claude_cli"       # claude_cli | codex_cli | gemini_cli | mock
model = "claude-opus-4-7"

[phases.write]
provider = "reasonix_cli"     # reasonix_cli | mock
model = "deepseek-v4-pro"

[phases.review]
provider = "codex_cli"        # codex_cli | claude_cli | gemini_cli | mock
model = "gpt-5.5"

[phases.fix]
# defaults to write provider and model

[phases.test]
commands = ["python -m unittest discover -s tests -v"]
timeout = 900
```

Legacy `[models]`, `[commands]`, and `[writer].provider` keys remain supported as defaults. Each CLI phase may use either `command_key` to reference `[commands]` or `command` for an inline command. `apply` has no model executor; it applies the reviewed `FINAL.diff` only after tests and review pass.

## What It Provides

- CLI workflow: `plan`, `approve`, `write`, `test`, `review`, `fix`, `status`, `diff`, `apply`, `cleanup`.
- MCP tools: `patchbay_plan`, `patchbay_approve`, `patchbay_write`, `patchbay_test`, `patchbay_review`, `patchbay_fix`, `patchbay_status`, `patchbay_events`, `patchbay_runs`, `patchbay_artifact`, `patchbay_config_show`, `patchbay_config_phase_set`, `patchbay_config_command_set`, `patchbay_config_test_add`, `patchbay_config_provider_add_cli`, `patchbay_diff`, `patchbay_apply`.
- Legacy MCP aliases: `ai_flow_*`.
- Isolated git worktrees by default.
- File-backed run artifacts under `.ai/runs/<run_id>/`.
- Human approval gate before implementation.
- Patch safety checks and read-only reviewer verification.
- **Cross-host visibility**: `patchbay events <run_id>` and `patchbay_status` reveal what every phase/agent did, including provider, model, action, and timestamps — from any MCP host.

## Quick Start

### npx-style (recommended)

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay init
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay-mcp --root /path/to/repo
```

### From a local checkout

```bash
python scripts/patchbay init
cp .ai/patchbay.example.toml .ai/patchbay.toml
```

### Interactive configuration

```bash
patchbay config     # Interactive wizard — no hand-editing required
patchbay doctor     # Validate your resolved phase configuration
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
# Automated — no hand-editing JSON/TOML required
patchbay mcp install codex          # Codex CLI / Codex Desktop
patchbay mcp install claude         # Claude Code
patchbay mcp install claude-desktop # Claude Desktop (edits config in-place)
patchbay mcp install gemini         # Gemini CLI

# Or manually
codex mcp add patchbay -- python scripts/patchbay_mcp_server.py
```

Use the equivalent MCP server registration command for other MCP hosts. Run `patchbay mcp doctor` to verify the server is reachable.

## Configuration

The public example config lives at `.ai/patchbay.example.toml`. It contains environment variable names only, not API keys.

Supported writer provider:

- `reasonix_cli`: uses `reasonix acp` as a real coding agent. Mock mode (`--mock`) is available for testing without credentials.

## Security

- `.ai/patchbay.toml`, `.ai/runs/`, `.ai/logs/`, `.ai/worktrees/`, and `.patchbay-worktrees/` are ignored.
- Writer patches are rejected for `.git`, `.env*`, secret-like paths, absolute paths, and path traversal.
- Reasonix ACP execute permissions are rejected; unknown permission requests are conservative.
- Reviewer runs read-only and Patchbay checks that review did not mutate the worktree.
- Claude and Codex CLI providers request their native read-only/plan modes; Gemini CLI has no equivalent sandbox flag, so Patchbay treats repository mutation detection before/after plan and review as the enforcement boundary for Gemini.
- Logs redact environment-derived secrets and adapter-known API keys.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Custom Provider Support (planned)

User-defined provider entries are planned for a future release. See [docs/custom-providers-plan.md](docs/custom-providers-plan.md) for the design — TOML schema, output parsing contract, safety constraints, and test surface are enumerated but not yet implemented.

## License

MIT
