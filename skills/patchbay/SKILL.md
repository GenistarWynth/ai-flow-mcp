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

If `patchbay_*` MCP tools are available, prefer them over shell commands unless the user or host has selected local-only work. The local CLI path is a first-class fallback for Skill-only usage.

If the user explicitly asks not to use MCP, says an MCP host keeps asking for confirmation, or asks for local-only work, do not call `patchbay_*` MCP tools. Use the local CLI/Skill path instead, such as `scripts/patchbay agent message "please don't use MCP" --json`, `scripts/patchbay setup --no-mcp --json`, `scripts/patchbay doctor --local-only --json`, `scripts/patchbay agent message "patchbay setup without MCP" --json`, `scripts/patchbay agent message "readiness without MCP" --json`, or `scripts/patchbay agent message "install Codex Skill" --json`.

- `patchbay_setup` / `patchbay_install` for one-call local setup: project files, local config, Codex Skill installation, MCP registration attempt, doctor summary, and structured `actions[]` for safe follow-ups.
- `patchbay_agent` for conversational setup/start/resume/advance while preserving gates. It also answers explicit local prompts such as `patchbay setup`, `patchbay setup for Claude Desktop`, `install patchbay for Gemini CLI`, `install Codex Skill`, `register MCP for Claude Desktop`, `安装 Codex Skill`, `注册 MCP 到 Gemini 命令行`, `帮我配置 Patchbay`, `帮助我配置 Patchbay 到 Claude 桌面`, `help`, `Patchbay 怎么用`, `使用说明`, `status`, `runs`, `查看最近运行`, `任务列表`, `what should I do next`, `下一步是什么`, `why can't I apply`, `what is blocking apply`, `门禁状态`, `为什么不能应用`, `readiness`, `readiness for Claude Desktop`, `diagnose`, `patchbay doctor`, `检查环境`, `环境自检`, `检查 Gemini 命令行环境`, `show economy profile`, `apply economy profile`, `configure economy provider command to <path>`, `configure reasonix command`, `configure reasonix command to <path>`, `配置 Reasonix 命令`, or `把 Reasonix 命令设为 <path>` with setup results, guidance, recent runs, unified doctor reports, routing updates, gate diagnostics, or local command configuration without creating a model run. Next-step prompts return `action: "next_step"` plus the latest run handoff, `next_action` / `run_reference.next_action`, confirmation requirements, and safe `actions[]`; they must not be treated as `continue`, `approve`, or `apply`. Gate-status prompts return `action: "gate_status"` plus `gate_diagnosis`, `gate_diagnosis.next_action`, blocker checks, and safe diagnostic/open-run `actions[]`; they must not be treated as `approve`, `test`, `review`, or `apply`. Host-targeted readiness prompts populate `setup_host` and `doctor.host`, so desktop clients can switch the Readiness host and show concrete MCP probe/setup commands without parsing prose. Natural-language cost routing prompts such as "use DeepSeek for simple writer work" or "大量简单写手工作让便宜模型/DeepSeek 去干" also apply the economy profile instead of starting a new run. Help/setup/readiness/status/profile/next_step/gate_status responses may include `actions[]` entries with `id`, `label`, `kind`, `safe`, `reason`, and either `message`, `command`, `host`, `run_id`, or `tab`; prefer these over parsing `next_actions` prose when rendering UI controls. A stateless `status`/`runs` response may expose `open_run`, `focus_composer`, or readiness actions, but clients must not treat `continue`, `approve`, or `apply` as direct actions until a concrete run is open. Run-bound prompts like `continue`, `approve`, `apply`, `diff`, `artifact`, or `查看失败原因` without a `run_id` should stay local and point back to an existing run with a latest-run handoff when available; use the `open_run` action to open that run before taking any gated action. View-only prompts such as `diff`, `events`, `logs`, `artifact`, or `查看失败原因` include `requested_view`, and run-bound responses may also include safe `diagnostic_tab` actions so desktop clients can switch tabs directly. Use `background: true` for long planning or implementation turns, then poll `patchbay_context` or `patchbay_events`.
- Foreground start responses stay gated at `PLANNED`, background start responses stay pollable, and both include a read-only `profile`, `routing`, and safe `actions[]` preview. Render this before approval to show whether write/fix are on the cheaper economy route, or to offer safe local follow-ups such as `apply_economy_profile` and `configure_reasonix_command`.
- Setup scope is prompt-aware: `install Codex Skill` installs the Skill without attempting MCP registration, `register MCP for Claude Desktop` skips Skill installation, and explicit `patchbay setup without MCP` / `--skip-mcp` / `--no-mcp` / `--local-only` keeps setup local to project files and Skill installation. Standalone no-MCP preference prompts such as `please don't use MCP`, `no MCP`, or `不要用这个MCP` return `action: "local_mode"` with safe local CLI/Skill/readiness actions instead of running setup or starting a model run. For readiness/doctor prompts, `readiness without MCP`, `patchbay doctor --local-only`, and `patchbay_doctor(skip_mcp=true)` should suppress MCP probe/register follow-up actions in both top-level and nested doctor payloads.
- View-only Agent prompts such as `context`, `handoff context`, `events`, `poll context`, and `poll events` are read-only diagnostics. `context` returns `action: "context"` and an Overview `diagnostic_tab`; `events` returns `action: "events"` and a Trace `diagnostic_tab`, both with a selected `run_id` and when inspecting the latest run without one. These prompts never advance gates.
- Help responses include local-only setup plus host-specific setup and readiness shortcut actions for Codex, Claude Code, Claude Desktop, and Gemini CLI; render those structured `actions[]` buttons instead of asking users to type setup or doctor prompts.
- `patchbay_plan`, `patchbay_approve`, `patchbay_write`, `patchbay_test`, `patchbay_review`, `patchbay_fix`, `patchbay_apply` for explicit phase control.
- `patchbay_context` for cross-host handoff status, next safe action, timeline, gate state, artifacts, provider trail, top-level `routing_evidence` / `efficiency_summary`, `run_metrics` efficiency evidence, and `agent_activity.health_cards` for desktop-ready health signals.
- `patchbay_metrics` when only phase durations, attempts, event/trace counts, provider usage, cost/token availability, `efficiency_summary`, and write/fix `routing_evidence` are needed. Inspect `efficiency_summary.status` for the verified economy token/cost/time share and `routing_evidence.economy_health.status` for `healthy`, `pending_evidence`, `command_not_ready`, `drift`, or `not_configured` before assuming high-volume write/fix work is using the cheaper Reasonix/DeepSeek route; missing or mismatched explicit `command_key` evidence counts as drift, not verified economy evidence. Prefer the returned top-level `actions[]` or `routing_evidence.actions[]` for UI buttons and follow-ups; they are structured as safe `local_agent` or `diagnostic_tab` actions, with a `command` field when a host wants to show the exact CLI fallback, so hosts do not need to parse `economy_health.next_action`.
- On failed runs, inspect `failure_recovery` from `patchbay_context`, `patchbay_status`, or `patchbay_agent` before retrying; it lists the failed stage, suggested next action, priority artifacts, and structured `actions[]` for safe inspection or replacement-task follow-ups. `patchbay_context.next_actions` / `agent_activity.next_action` may mirror these safe diagnostic actions for UI convenience, but failed-run recovery must not be treated as `continue`, `approve`, or `apply`.
- `patchbay_config_profile_show` / `patchbay_config_profile_apply` with `profile: "economy"` to inspect or apply the economy route for high-volume write/fix work while leaving plan/review choices intact. These return structured `actions[]`; use them for safe readiness/start/apply follow-ups instead of parsing `next_actions` prose. If `commands.reasonix` is missing, readiness will first surface `configure_reasonix_command`; prefer sending `configure reasonix command`, `configure reasonix command to <path>`, `配置 Reasonix 命令`, or `把 Reasonix 命令设为 <path>` through `patchbay_agent` so the cheaper write/fix route can actually execute.
- For custom low-cost writers, send `configure DeepSeek provider` to get a safe copyable `patchbay config provider add-cli ... --activate-economy` command template, send `configure DeepSeek provider to <command>` when the local DeepSeek wrapper command is explicit and should be registered immediately as the `cheap_writer` write/fix economy provider, or send `configure economy provider command to <path>` to repair the active custom provider command in place. Custom provider command failures should point to `providers.<id>.command`, not `commands.reasonix`, and expose a copyable `configure_economy_provider_command` action.
- Routing questions such as `what model will write/fix use`, `is writer using cheap model`, or `现在写手是不是走便宜模型` are read-only `profile_show` prompts. When a run id is available, expect the response to include `metrics.efficiency_summary` so the host can answer from observed provider/token/cost evidence, not config alone. Only imperative prompts such as `apply economy profile`, `configure DeepSeek provider to <command>`, or `让大量简单写手工作用便宜模型/DeepSeek 去干` should mutate the routing profile.
- `patchbay_doctor` for read-only setup diagnostics across config, CLI entry points, and Skill installation; it skips stdio MCP probing unless `include_mcp: true` is explicitly passed. Pass `host` when targeting a specific MCP host; use `skip_mcp: true` for local-only readiness that hides MCP probe/register follow-ups. Use its `actions[]` for safe setup, Skill, MCP probe, refresh, economy-profile, and Reasonix-command actions with concrete host-aware commands.
- `patchbay_skill_install`, `patchbay_skill_doctor`, and `patchbay_skill_print` for standalone Codex Skill installation, validation, and inspection. `patchbay_skill_doctor` returns safe `install_skill` / `refresh_skill_doctor` actions when the Skill is not installed; with the default skills root, `install_skill` is a `local_agent` action with message `install Codex Skill` plus the `patchbay skill install codex` command fallback, so hosts should render it instead of parsing `next_actions`. With a custom `skill_path`, render the command action so the selected destination is preserved.
- `patchbay_events` and `patchbay_trace` for focused diagnostics.

Legacy `ai_flow_*` aliases are compatible, but use `patchbay_*` names for new work.

## Conversational Background Mode

For MCP hosts or desktop UIs that should not block while models write, prefer the conversational background path after the plan gate is satisfied:

```bash
scripts/patchbay agent message "<user task>" --background --json
scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
scripts/patchbay agent message continue --run-id <run_id> --background --json
scripts/patchbay context <run_id>
scripts/patchbay events <run_id>
```

Background turns write `JOB.json` and append `agent` events. They return safe structured `actions[]` for opening the run, opening Trace, polling status, polling context, and polling events. Prefer `poll_context` when a host needs the refreshed handoff payload, and `poll_events` when it only needs the event stream. If a host sends another background `approve`/`continue` while an Agent job is active, Patchbay returns the existing job with `already_running: true` and the same polling actions instead of starting another worker. If a concrete `run_id` is already selected, explicit unattended phrases such as `don't ask me`, `assume yes`, `you have all permissions`, `不要问我`, or `所有权限都给你` count as plan approval for that run and may start background write/test/review autopilot; the same phrases without a `run_id` must still return `missing_run` guidance. They do not change the safety model: apply remains foreground-only after tests and review pass, and final apply still needs explicit confirmation. Do not treat background follow-up actions as approval, continue, or apply controls.

## Installation Reference

For setup details, read `references/install.md` only when installing or debugging setup.
