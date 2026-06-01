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

The default cost profile keeps expensive reasoning in plan/review and sends high-volume implementation and repair work to the lower-cost Reasonix/DeepSeek writer. If the Reasonix command is not configured yet, readiness will surface a `configure_reasonix_command` action before it offers `start_new_task`; send `patchbay agent message "configure reasonix command" --json` to set the default executable, or `patchbay agent message "configure reasonix command to <path>" --json` for a full local path, without starting a model run. Localized conversational prompts such as `配置 Reasonix 命令` and `把 Reasonix 命令设为 <path>` are accepted through the same Agent and MCP entry points. Reapply the routing profile at any time with `patchbay config profile apply economy`.

Legacy `[models]`, `[commands]`, and `[writer].provider` keys remain supported as defaults. Each CLI phase may use either `command_key` to reference `[commands]` or `command` for an inline command. `apply` has no model executor; it applies the reviewed `FINAL.diff` only after tests and review pass.

## What It Provides

- CLI workflow: `setup`/`install`, `doctor`, `agent message`, `web`, `plan`, `approve`, `write`, `test`, `review`, `fix`, `status`, `context`, `metrics`, `trace`, `diff`, `apply`, `cleanup`.
- MCP tools: `patchbay_agent`, `patchbay_setup`, `patchbay_install`, `patchbay_plan`, `patchbay_approve`, `patchbay_write`, `patchbay_test`, `patchbay_review`, `patchbay_fix`, `patchbay_status`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, `patchbay_skill_install`, `patchbay_skill_print`, `patchbay_skill_doctor`, `patchbay_events`, `patchbay_trace`, `patchbay_runs`, `patchbay_artifact`, `patchbay_config_show`, `patchbay_config_phase_set`, `patchbay_config_command_set`, `patchbay_config_test_add`, `patchbay_config_profile_apply`, `patchbay_config_profile_show`, `patchbay_config_provider_add_cli`, `patchbay_diff`, `patchbay_apply`.
- Legacy MCP aliases: `ai_flow_*`.
- Isolated git worktrees by default.
- File-backed run artifacts under `.ai/runs/<run_id>/`.
- Human approval gate before implementation.
- Patch safety checks, read-only reviewer verification, and a default apply gate that treats skipped tests as not passed unless `workflow.allow_apply_without_tests = true`.
- **Cross-host visibility**: `patchbay context <run_id>` / `patchbay_context` is the preferred resume call. It returns the current gate state, next safe action, provider trail, artifacts, timeline, top-level `routing_evidence` / `efficiency_summary`, and `run_metrics` efficiency evidence in one handoff digest. `run_metrics.routing_evidence` shows whether write/fix are configured for the Reasonix/DeepSeek economy route, whether the Reasonix command can execute, and whether provider events have actually observed it; missing or mismatched explicit `command_key` evidence is treated as routing drift instead of verified economy evidence. `routing_evidence.economy_health` and `agent_activity.health_cards` expose the same signal as machine-readable `healthy`, `pending_evidence`, `command_not_ready`, `drift`, or `not_configured` states, plus an `economy_efficiency` card summarizing `efficiency_summary` for desktop and MCP clients. `patchbay_metrics` also returns top-level `actions[]` mirrored from `routing_evidence.actions[]`, so clients can render safe routing follow-ups such as applying the economy profile, configuring Reasonix, or opening the Trace tab without parsing `economy_health.next_action`. Readiness and setup responses include the same structured action contract; `help` also exposes local-only setup plus host-specific setup/readiness shortcut actions for Codex, Claude Code, Claude Desktop, and Gemini CLI. `patchbay events <run_id>` and `patchbay_status` remain available for focused inspection.
- **Failure recovery**: failed runs expose `failure_recovery` through `status`, `context`, and the conversational Agent, including the failed stage, suggested next action, priority artifacts, and structured `actions[]` for safe inspection or replacement-task follow-ups.

## Quick Start

### npx-style (recommended)

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay doctor
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay web --port 8765
```

Then open `http://127.0.0.1:8765`. Use `patchbay-mcp --root /path/to/repo` only when a host asks for a raw stdio server command.

### From a local checkout

```bash
python scripts/patchbay setup --host codex
python scripts/patchbay doctor
python scripts/patchbay web --port 8765
```

Then open `http://127.0.0.1:8765`.

### Interactive configuration

```bash
patchbay setup --host codex     # init + local config + Codex Skill + MCP registration attempt + doctor summary
patchbay setup --host codex --no-mcp  # local config + Codex Skill only; no MCP registration/probe follow-ups
patchbay install --host codex    # alias for setup
patchbay config     # Interactive wizard — no hand-editing required
patchbay config profile apply economy  # keep write/fix on Reasonix + DeepSeek
patchbay agent message "apply economy profile" --json  # same routing change through the conversational Agent
patchbay agent message "configure reasonix command" --json  # set commands.reasonix; append `to <path>` or use `把 Reasonix 命令设为 <path>`
patchbay doctor     # Unified config/Skill readiness checks; skips stdio MCP probing by default
patchbay doctor --local-only     # Readiness without MCP probe/register follow-up actions
patchbay doctor --probe-mcp     # Add stdio MCP initialize/tools-list verification when needed
patchbay config --doctor     # Validate your resolved phase configuration
patchbay config --set-key models.planner --set-value claude-opus-4-7
```

Edit `.ai/patchbay.toml` for your local CLI commands, model names, provider, and test allowlist. Do not commit `.ai/patchbay.toml`; it is intentionally ignored.

The old `scripts/ai-flow` command and `.ai/ai-flow.toml` config still work as compatibility aliases.

## CLI Usage

```bash
python scripts/patchbay setup --host codex --json
python scripts/patchbay plan --task "..."
python scripts/patchbay agent message "..." --json
python scripts/patchbay agent message "patchbay setup" --json
python scripts/patchbay agent message "patchbay setup for Claude Desktop" --json
python scripts/patchbay agent message status --json
python scripts/patchbay agent message context --json
python scripts/patchbay agent message readiness --json
python scripts/patchbay agent message "readiness for Claude Desktop" --json
python scripts/patchbay web --port 8765
python scripts/patchbay approve <run_id>
python scripts/patchbay write <run_id>
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id>
python scripts/patchbay context <run_id>
python scripts/patchbay metrics <run_id>
python scripts/patchbay apply <run_id>
```

`metrics` includes phase duration/attempt counts, provider usage, token/cost availability, `efficiency_summary` for the verified economy token/cost/time share, and `routing_evidence` with `economy_health` for the write/fix economy route. For desktop and MCP clients, prefer the returned `actions[]` or `routing_evidence.actions[]` over deriving UI controls from `economy_health.next_action`; those actions are already typed as safe `local_agent`, `command`, or `diagnostic_tab` follow-ups and may include a `command` field for exact CLI fallback display. When `command_not_ready` comes from a custom economy provider, render the `configure_economy_provider_command` copy command before the inspect action so users can fix `providers.<id>.command` directly.

Use `--background` for long conversational turns so the caller can return immediately and poll status/events:

```bash
python scripts/patchbay agent message "..." --background --json
python scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
python scripts/patchbay agent message continue --run-id <run_id> --background --json
```

Background agent turns write `JOB.json`, append `agent` events, and preserve the plan/apply confirmation gates. `apply` remains foreground-only and requires explicit confirmation after tests and review pass. Background responses include safe structured `actions[]` for opening the run, opening Trace, polling status, polling context, and polling events; they never expose `continue`, `approve`, or `apply` as direct background follow-ups. If a client sends another background `approve`/`continue` while an Agent job is already active, Patchbay returns the existing job with `already_running: true` and the same safe polling actions instead of spawning a duplicate worker. Local prompts such as `patchbay setup`, `patchbay setup for Claude Desktop`, `install patchbay for Gemini CLI`, `install Codex Skill`, `register MCP for Claude Desktop`, `安装 Codex Skill`, `注册 MCP 到 Gemini 命令行`, `帮我配置 Patchbay`, `帮助我配置 Patchbay 到 Claude 桌面`, `help`, `Patchbay 怎么用`, `使用说明`, `status`, `runs`, `查看最近运行`, `任务列表`, `what should I do next`, `下一步是什么`, `why can't I apply`, `what is blocking apply`, `门禁状态`, `为什么不能应用`, `readiness`, `readiness for Claude Desktop`, `diagnose`, `patchbay doctor`, `检查环境`, `环境自检`, `检查 Gemini 命令行环境`, `show economy profile`, `apply economy profile`, `configure DeepSeek provider`, `configure economy provider command to <path>`, `configure reasonix command`, `configure reasonix command to <path>`, `配置 Reasonix 命令`, or `把 Reasonix 命令设为 <path>` return setup results, guidance, recent runs, readiness, routing changes, gate diagnostics, command templates, or command configuration directly without creating a model run. Host-targeted readiness prompts populate `setup_host` and `doctor.host`, so desktop clients can switch the Readiness host and show concrete MCP probe/setup commands without parsing prose. Next-step questions return `action: "next_step"` with the latest run handoff, `next_action` / `run_reference.next_action`, confirmation requirements, and safe `actions[]`; they do not execute `continue`, `approve`, or `apply` until a concrete run is open and the required confirmation is supplied. Gate-status questions return `action: "gate_status"` with `gate_diagnosis`, `gate_diagnosis.next_action`, blocker checks, and safe diagnostic/open-run actions; blocked direct `apply` on a selected run returns the same `gate_diagnosis.next_action` and safe diagnostic actions instead of asking for apply confirmation. These paths do not approve plans, run tests, review, or apply patches. Natural-language cost routing prompts such as "use DeepSeek for simple writer work" or "大量简单写手工作让便宜模型/DeepSeek 去干" also apply the economy profile instead of starting a new run. Help/setup/readiness/status/profile/next_step/gate_status payloads include machine-readable `actions[]` with `id`, `label`, `kind`, `safe`, `reason`, and either `message`, `command`, `host`, `run_id`, or `tab`; local run handoffs can also use `next_action`, `open_run`, and `focus_composer`. `patchbay_config_profile_show` / `patchbay_config_profile_apply` expose the same structured action contract for MCP and CLI clients. `status`/`runs` without a `run_id` only expose safe local actions such as opening the latest run, focusing the composer, or readiness diagnostics; gated actions like `continue`, `approve`, and `apply` are chosen only after a run is opened. Run-bound prompts such as `continue`, `approve`, `apply`, `context`, `events`, `diff`, `artifact`, or `查看失败原因` without a `run_id` also stay local; when a recent run exists, the response includes a latest-run handoff plus structured `actions[]` to open it before any gated action is chosen. View prompts such as `context`, `handoff context`, `diff`, `events`, `logs`, `artifact`, or `查看失败原因` include `requested_view`; when a run is already selected, they also return safe `diagnostic_tab` actions so clients can open the matching diagnostics tab without running a phase.

Routing questions such as `what model will write/fix use`, `is writer using cheap model`, or `现在写手是不是走便宜模型` are read-only `profile_show` prompts. When a run id is provided, the reply also includes that run's `metrics.efficiency_summary` evidence so clients can distinguish configured routing from observed provider/token/cost behavior. Imperative routing prompts such as `apply economy profile` or “use DeepSeek for simple writer work” are the ones that mutate local routing configuration.

 The web workbench exposes the same conversational flow and has a diagnostics drawer. Its Readiness tab calls the unified doctor checks without MCP stdio probing, so setup gaps are visible from the desktop UI without starting extra child processes. The Readiness host selector passes the target host into doctor/setup, so command actions use concrete registrations such as `patchbay mcp install claude-desktop` instead of placeholder host names. It also shows the active write/fix routing profile and renders structured `actions[]` for safe setup, Skill, MCP probe, refresh, and economy-routing follow-ups. Local conversational replies render safe `command` actions as copyable command rows, so MCP/Skill registration commands are usable without opening diagnostics. Background job cards expose open-activity and refresh controls for long-running turns. The Overview tab surfaces economy routing and `economy_efficiency` health cards from `agent_activity.health_cards`, so drift from the intended cheaper write/fix route and actual token/cost/time evidence are visible without parsing logs.

Setup scope is inferred from the prompt: `install Codex Skill` installs the Skill without attempting MCP registration, `register MCP for Claude Desktop` skips Skill installation, and `patchbay setup without MCP` / `--skip-mcp` / `--no-mcp` / `--local-only` keeps setup local to project files and Skill installation. Conversational avoidance such as `please don't use MCP`, `no MCP`, or `不要用这个MCP` is treated as the same local-only setup scope instead of starting a model run. The same avoidance scope applies to `readiness` / `doctor` prompts, so `readiness without MCP` and `patchbay doctor --local-only` suppress MCP probe/register follow-up actions in both the top-level response and nested doctor payload.

After starting `patchbay web --port 8765`, open `http://127.0.0.1:8765`.

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

Use the equivalent MCP server registration command for other MCP hosts. Run `patchbay doctor --host <host>` for lightweight readiness checks with concrete structured registration actions for that host. Add `--probe-mcp` or run `patchbay mcp doctor` only when you specifically need stdio server reachability and tool-list evidence.

`patchbay doctor` is read-only and reports project initialization, phase config validity, CLI shim/installed command availability, bundled Skill source, whether the Codex Skill is installed, and MCP follow-up actions; it skips stdio MCP probing by default so routine readiness checks do not spawn the MCP server. Use `patchbay doctor --local-only` when the current host should not show MCP probe/register actions at all. It returns prose `next_actions`/`recommendations` plus structured `actions[]` for desktop/MCP clients. `patchbay doctor --probe-mcp` and `patchbay mcp doctor` start the stdio MCP server, send `initialize` and `tools/list`, and verify required tools including `patchbay_agent`, `patchbay_plan`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, `patchbay_install`, `patchbay_skill_install`, and `patchbay_skill_doctor`. For Codex, Claude Code, and Gemini, `mcp install` now tries to register automatically and falls back to the command text if the host CLI is unavailable; Claude Desktop writes its JSON config in place. Host names accept English and common Chinese aliases, such as `Claude Desktop`, `Claude 桌面`, `Claude Code`, `Claude 代码`, `Gemini CLI`, and `Gemini 命令行`.

After MCP registration, restart or reload the target host if it caches tool lists. Verify with `patchbay mcp doctor --json`, or from the host by checking that `patchbay_agent` is visible.

## Codex Skill Install

Patchbay also ships as a Codex Skill. The Skill teaches Codex when to invoke the gated workflow; the MCP server provides the tools.

```bash
patchbay skill install codex
patchbay skill doctor codex
patchbay skill print codex --json
```

By default the Skill installs to `$CODEX_HOME/skills` or `~/.codex/skills`. It triggers on phrases such as "走多模型流程" and "multi-agent workflow"; MCP tools still need MCP registration.
`patchbay skill doctor` / `patchbay_skill_doctor` also return safe structured `install_skill` and `refresh_skill_doctor` actions when the Skill is missing. With the default skills root, `install_skill` is a `local_agent` action with message `install Codex Skill` and a copyable `patchbay skill install codex` command fallback, so desktop and MCP hosts can install the Skill without invoking MCP registration. When a custom `--path` is supplied, the action remains a command so the selected destination is preserved.

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

User-defined CLI providers can be configured under `[providers.<id>]` with `roles`, `command`, `args`, `prompt_mode`, and `output_contract`. Use `patchbay config provider add-cli ...` to add them without hand-editing TOML; add `--activate-economy --economy-model <model> --economy-label <label>` to register a low-cost writer and immediately route write/fix work through it. The conversational Agent can do the same when the command is explicit: `patchbay agent message "configure DeepSeek provider to deepseek-writer" --json`; without a command, `configure DeepSeek provider` returns a safe copyable command template instead of mutating config. If the wrapper path changes later, send `configure economy provider command to <path>` or paste the returned `patchbay config --set-key providers.<id>.command --set-value <path>` action back into `patchbay_agent` to repair only the command. The current runtime supports CLI providers; [docs/custom-providers-plan.md](docs/custom-providers-plan.md) tracks the broader future design for HTTP/ACP modes and stricter provider-specific safety controls.

```bash
patchbay config provider add-cli cheap_writer --roles write fix --command deepseek-writer --output-contract writer_diff --activate-economy --economy-model deepseek-chat --economy-label "DeepSeek cheap writer"
```

## License

MIT
