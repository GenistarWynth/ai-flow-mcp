# Patchbay Agent Contract

Read this reference when a host, desktop UI, or Skill-only workflow needs to handle structured Patchbay Agent responses. Prefer structured fields over prose.

## Core Fields

- `actions[]`: safe follow-ups with `id`, `label`, `kind`, `safe`, `reason`, and one of `message`, `command`, `host`, `run_id`, or `tab`.
- `action_groups[]`: stable UI grouping via `action_ids`. Use these groups instead of inferring sections from ids.
- `routing` / `routing_evidence` / `efficiency_summary`: cost-routing state and observed write/fix economy evidence.
- `gate_diagnosis`: apply blockers and the next safe diagnostic or gated action.
- `failure_recovery`: failed stage, suggested next action, priority artifacts, safe diagnostic/replacement actions, and grouped recovery controls.
- `requested_view`: read-only prompts such as diff, events, logs, artifact, or 查看失败原因 may request a diagnostic tab.

## Action Kinds

- `local_agent`: send `message` back through `patchbay_agent` or `scripts/patchbay agent message`.
- `diagnostic_tab`: open the named UI tab such as `Trace`, `Log`, `Diff`, `Artifacts`, `Config`, or `Providers`.
- `open_run`: open the given `run_id` before taking any gated action.
- `focus_composer`: start or focus a replacement-task composer.
- `command`: render the exact `command` as a copyable local CLI fallback, or run it only when the surrounding host deliberately supports local commands.

Never treat safe diagnostic or setup actions as `continue`, `approve`, or `apply`.

## Action Groups

Use `action_groups[]` as section hints for the already returned `actions[]`; do not infer sections from ids or prose. Known group ids are:

- `gate`: confirmation-sensitive run actions.
- `background_polling`: safe polling actions for active background jobs.
- `routing`: economy routing inspection or repair.
- `setup`: setup, readiness, Skill, or MCP follow-ups.
- `diagnostics`: read-only run views and diagnostic tabs.
- `new_task`: composer/new-run controls.
- `commands`: copy-first CLI commands that do not have a stronger semantic section.
- `local`: safe local Agent follow-ups.

The group does not override the action kind. A `kind: "command"` action should still render as a copyable command row even when its group is `setup` or `routing`; use the `commands` group for copy-first actions such as provider command repair templates (`configure_economy_provider_command`) when clients should surface them apart from routing/setup controls.

## Conversational Prompts

`patchbay_agent` handles setup, start, resume, advance, readiness, routing, help, status, next-step, and gate-status prompts without requiring the host to parse natural language. Examples include:

- Setup/help: `patchbay setup`, `patchbay setup for Claude Desktop`, `install patchbay for Gemini CLI`, `install Codex Skill`, `register MCP for Claude Desktop`, `安装 Codex Skill`, `注册 MCP 到 Gemini 命令行`, `帮我配置 Patchbay`, `Patchbay 怎么用`, `使用说明`.
- Run visibility: `status`, `runs`, `查看最近运行`, `任务列表`, `context`, `handoff context`, `events`, `poll context`, `poll events`.
- Next-step and gates: `what should I do next`, `下一步是什么`, `why can't I apply`, `what is blocking apply`, `门禁状态`, `为什么不能应用`.
- Readiness: `readiness`, `readiness for Claude Desktop`, `diagnose`, `patchbay doctor`, `检查环境`, `环境自检`, `检查 Gemini 命令行环境`.
- Economy routing: `show economy profile`, `apply economy profile`, `configure DeepSeek provider`, `configure DeepSeek provider to <command>`, `configure economy provider command to <path>`, `configure reasonix command`, `configure reasonix command to <path>`, `配置 Reasonix 命令`, `把 Reasonix 命令设为 <path>`, `what model will write/fix use`, `is writer using cheap model`, `现在写手是不是走便宜模型`.

## Local-Only Scope

If the user explicitly asks not to use MCP, says an MCP host keeps asking for confirmation, asks for Chrome/browser Skill instead of MCP, or says `please don't use MCP`, `no MCP`, `use Chrome Skill instead of MCP`, `少用这个MCP`, `不要用这个MCP`, `不走 MCP`, `走本地模式`, or `只用本地工具`, do not call MCP tools. Use local commands such as:

```bash
scripts/patchbay setup --no-mcp --json
scripts/patchbay doctor --local-only --json
scripts/patchbay agent message "patchbay setup without MCP" --json
scripts/patchbay agent message "readiness without MCP" --json
scripts/patchbay agent message "走本地模式，不走 MCP" --json
```

`readiness without MCP`, `patchbay doctor --local-only`, and `patchbay_doctor(skip_mcp=true)` suppress MCP probe/register follow-up actions in both top-level and nested doctor payloads.

## Setup And Skill Actions

- `patchbay_setup` / `patchbay_install` initialize project files, local config, bundled Codex Skill installation, optional MCP registration, doctor summary, top-level `routing`, `recommendations`, `next_actions`, `actions[]`, and `action_groups[]`.
- `patchbay_plan`, `scripts/patchbay plan --json`, and Web `POST /api/runs` foreground planning responses include the same read-only `profile`, `routing`, safe `actions[]`, and `action_groups[]` start preview as `patchbay_agent`, so clients can show economy-route state before plan approval.
- Setup scope is prompt-aware: `install Codex Skill` installs only the Skill, `register MCP for Claude Desktop` skips Skill installation, and `patchbay setup without MCP` keeps setup local.
- `patchbay_doctor` is read-only and skips stdio MCP probing unless `include_mcp: true` is explicitly passed. Use `skip_mcp: true` for local-only readiness.
- `patchbay_skill_install`, `patchbay_skill_doctor`, and `patchbay_skill_print` support standalone Codex Skill installation, validation, and inspection. Codex aliases such as `Codex Desktop`, `Codex CLI`, and `Codex 桌面` normalize to `codex`.
- `patchbay_skill_doctor` reports drift through `status: "outdated"`, `installed_matches_source`, `missing_installed_files`, `changed_installed_files`, and `extra_installed_files`, then returns safe `install_skill` / `refresh_skill_doctor` actions.

Help responses may include `capabilities[]` summaries plus local-only setup and host-specific setup/readiness shortcut actions for Codex, Claude Code, Claude Desktop, and Gemini CLI. Render capability summaries as the Agent help surface and render structured actions as buttons instead of asking users to type setup or doctor prompts.

## Next-Step And Gate Status

Next-step prompts return `action: "next_step"` plus the latest run handoff, `next_action` or `run_reference.next_action`, confirmation requirements, and safe `actions[]`. Do not treat a next-step response as `continue`, `approve`, or `apply` until the user chooses a concrete gated action.

Gate-status prompts return `action: "gate_status"` plus `gate_diagnosis`, `gate_diagnosis.next_action`, blocker checks, and safe diagnostic/open-run `actions[]`. Do not treat a gate-status response as `approve`, `test`, `review`, or `apply`.

Stateless `status` or `runs` responses may expose `open_run`, `focus_composer`, or readiness actions. Open the concrete run before taking gated actions.

Direct `patchbay_apply`, `scripts/patchbay apply <run_id>`, and Web `POST /api/runs/<run_id>/actions/apply` also require explicit final confirmation (`confirmation: "apply_approved"` or `--confirmation apply_approved`) after reviewing `FINAL.diff`; missing confirmation must not call `service.apply`.

## Background Mode

For long model work, prefer:

```bash
scripts/patchbay agent message "<user task>" --background --json
scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
scripts/patchbay agent message continue --run-id <run_id> --background --json
scripts/patchbay context <run_id>
scripts/patchbay events <run_id>
```

Background responses write `JOB.json`, append agent events, and return safe polling actions: `poll_context`, `poll_status`, and `poll_events`. These are grouped under `background_polling`. If a job is already active, Patchbay returns `already_running: true` with the same polling actions instead of starting another worker.

If a concrete `run_id` is already selected, explicit unattended phrases such as `don't ask me`, `assume yes`, `you have all permissions`, `full access`, `approve yourself`, `不要问我`, `所有权限都给你`, `无需向我确认`, or `完全访问权限` count as plan approval for that run and may start background write/test/review autopilot. Without a `run_id`, they must return `missing_run` guidance. They never authorize final apply.

## Failure Recovery

On failed runs, inspect `failure_recovery` from `patchbay_context`, `patchbay_status`, or `patchbay_agent` before retrying. It lists:

- Failed `stage` and `error`.
- `suggested_next_action`.
- Priority `artifacts`.
- Safe `actions[]` such as `diagnostic_tab`, `open_run`, or `focus_composer`.
- `action_groups[]` for diagnostics and replacement-task controls.

Render these as safe inspection or replacement actions. Do not expose them as phase retry, approval, or apply controls unless Patchbay separately returns a gated action after diagnostics.

## Economy Routing

Use `patchbay_config_profile_show` / `patchbay_config_profile_apply` with `profile: "economy"` to inspect or apply the cost profile. The economy profile labels `write` and `fix` as high-volume economy phases and `plan` and `review` as supervision phases.

Routing questions such as `what model will write/fix use`, `is writer using cheap model`, or `现在写手是不是走便宜模型` are read-only `profile_show` prompts. When a run id is available, expect observed `metrics.efficiency_summary`; answer from actual provider/token/cost evidence, not config alone.

Only imperative prompts such as `apply economy profile`, `configure DeepSeek provider to <command>`, `简单 writer/fix 用 DeepSeek 省钱`, `降本，让简单 writer/fix 走低价模型`, or `让大量简单写手工作用便宜模型/DeepSeek 去干` should mutate routing.

For the built-in Reasonix route, use `configure reasonix command` or `配置 Reasonix 命令` when readiness reports `economy_health.status = "command_not_ready"` or surfaces `configure_reasonix_command`.

For custom low-cost writers:

- `configure DeepSeek provider` returns a copyable `patchbay config provider add-cli ... --activate-economy` template.
- `configure DeepSeek provider to <command>` registers `cheap_writer`, activates write/fix economy routing, and keeps plan/review on stronger providers.
- `configure economy provider command to <path>` repairs the active custom provider command in place.
- Custom provider command failures should point to `providers.<id>.command`, not `commands.reasonix`, and expose `configure_economy_provider_command`.

Desktop/Web Readiness UIs may render a guarded economy-provider form only when the structured `configure_deepseek_provider` action is present.
