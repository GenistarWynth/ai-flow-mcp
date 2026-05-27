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

- CLI workflow: `doctor`, `agent message`, `web`, `plan`, `approve`, `write`, `test`, `review`, `fix`, `status`, `context`, `metrics`, `trace`, `diff`, `apply`, `cleanup`.
- MCP tools: `patchbay_agent`, `patchbay_plan`, `patchbay_approve`, `patchbay_write`, `patchbay_test`, `patchbay_review`, `patchbay_fix`, `patchbay_status`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, `patchbay_events`, `patchbay_trace`, `patchbay_runs`, `patchbay_artifact`, `patchbay_config_show`, `patchbay_config_phase_set`, `patchbay_config_command_set`, `patchbay_config_test_add`, `patchbay_config_provider_add_cli`, `patchbay_diff`, `patchbay_apply`.
- Legacy MCP aliases: `ai_flow_*`.
- Isolated git worktrees by default.
- File-backed run artifacts under `.ai/runs/<run_id>/`.
- Human approval gate before implementation.
- Patch safety checks, read-only reviewer verification, and a default apply gate that treats skipped tests as not passed unless `workflow.allow_apply_without_tests = true`.
- **Cross-host visibility**: `patchbay context <run_id>` / `patchbay_context` is the preferred resume call. It returns the current gate state, next safe action, provider trail, artifacts, timeline, and `run_metrics` efficiency evidence in one handoff digest. `patchbay events <run_id>` and `patchbay_status` remain available for focused inspection.

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
patchbay doctor     # Unified config/MCP/Skill readiness checks
patchbay config --doctor     # Validate your resolved phase configuration
patchbay config --set-key models.planner --set-value claude-opus-4-7
```

Edit `.ai/patchbay.toml` for your local CLI commands, model names, provider, and test allowlist. Do not commit `.ai/patchbay.toml`; it is intentionally ignored.

The old `scripts/ai-flow` command and `.ai/ai-flow.toml` config still work as compatibility aliases.

## CLI Usage

```bash
python scripts/patchbay plan --task "..."
python scripts/patchbay agent message "..." --json
python scripts/patchbay agent message readiness --json
python scripts/patchbay web --port 8765
python scripts/patchbay approve <run_id>
python scripts/patchbay write <run_id>
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id>
python scripts/patchbay context <run_id>
python scripts/patchbay metrics <run_id>
python scripts/patchbay apply <run_id>
```

Use `--background` for long conversational turns so the caller can return immediately and poll status/events:

```bash
python scripts/patchbay agent message "..." --background --json
python scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
python scripts/patchbay agent message continue --run-id <run_id> --background --json
```

Background agent turns write `JOB.json`, append `agent` events, and preserve the plan/apply confirmation gates. `apply` remains foreground-only and requires explicit confirmation after tests and review pass. Readiness prompts such as `readiness`, `diagnose`, or `patchbay doctor` return the unified doctor report directly without creating a run.

The web workbench exposes the same conversational flow and has a diagnostics drawer. Its Readiness tab calls the unified doctor checks without MCP stdio probing, so setup gaps are visible from the desktop UI without starting extra child processes.

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

Use the equivalent MCP server registration command for other MCP hosts. Run `patchbay doctor` for full readiness checks or `patchbay mcp doctor` to focus only on server reachability.

`patchbay doctor` is read-only and reports project initialization, phase config validity, CLI shim/installed command availability, MCP reachability/tools, bundled Skill source, and whether the Codex Skill is installed. `patchbay mcp doctor` starts the stdio MCP server, sends `initialize` and `tools/list`, and verifies required tools including `patchbay_agent`, `patchbay_plan`, `patchbay_context`, `patchbay_metrics`, and `patchbay_doctor`. For Codex, Claude Code, and Gemini, `mcp install` prints the registration command to run; Claude Desktop writes its JSON config in place.

## Codex Skill Install

Patchbay also ships as a Codex Skill. The Skill teaches Codex when to invoke the gated workflow; the MCP server provides the tools.

```bash
patchbay skill install codex
patchbay skill print codex --json
```

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

## Custom Provider Support

User-defined CLI providers can be configured under `[providers.<id>]` with `roles`, `command`, `args`, `prompt_mode`, and `output_contract`. Use `patchbay config provider add-cli ...` to add them without hand-editing TOML. The current runtime supports CLI providers; [docs/custom-providers-plan.md](docs/custom-providers-plan.md) tracks the broader future design for HTTP/ACP modes and stricter provider-specific safety controls.

## License

MIT
