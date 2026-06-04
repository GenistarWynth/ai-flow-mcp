# Patchbay Agent Contract

Read this reference when a host, desktop UI, or Skill-only workflow needs to handle structured Patchbay Agent responses. Prefer structured fields over prose.

## Core Fields

- `actions[]`: safe follow-ups with `id`, `label`, `kind`, `safe`, `reason`, and one of `message`, `command`, `host`, `run_id`, or `tab`.
- `action_groups[]`: stable UI grouping via `action_ids`. Use these groups instead of inferring sections from ids.
- `routing` / `routing_evidence` / `efficiency_summary`: cost-routing state and observed write/fix economy evidence.
- `gate_diagnosis`: apply blockers and the next safe diagnostic or gated action.
- `failure_recovery`: failed stage, suggested next action, priority artifacts, safe diagnostic/replacement actions, and grouped recovery controls.
- `background_job`: active or completed background worker state, including safe polling/cancel actions and cancel metadata when present.
- `runs.inbox`: structured multi-run work queue for stateless `status` / `runs`, `patchbay_runs`, and `scripts/patchbay runs --json`.
- `requested_view`: read-only prompts such as diff, events, logs, artifact, or 查看失败原因 may request a diagnostic tab.

## Action Kinds

- `local_agent`: send `message` back through `patchbay_agent` or `scripts/patchbay agent message`.
- `diagnostic_tab`: open the named UI tab such as `Trace`, `Log`, `Diff`, `Artifacts`, `Config`, or `Providers`.
- `open_run`: open the given `run_id` before taking any gated action.
- `focus_composer`: start or focus a replacement-task composer.
- `command`: render the exact `command` as a copyable local CLI fallback, or run it only when the surrounding host deliberately supports local commands. Desktop/Web copy controls should use a fallback copy path when the Clipboard API is unavailable or rejects writes.

Never treat safe diagnostic or setup actions as `continue`, `approve`, or `apply`.

## Action Groups

Use `action_groups[]` as section hints for the already returned `actions[]`; do not infer sections from ids or prose. Known group ids are:

- `gate`: confirmation-sensitive run actions.
- `background_polling`: safe polling actions for active background jobs.
- `background_control`: safe stop/manage actions such as `cancel_background_job` for active background jobs.
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
- Run visibility: `status`, `runs`, `查看最近运行`, `任务列表`, `context`, `handoff context`, `events`, `trace`, `logs`, `artifact`, `diff`, `poll context`, `poll events`.
- Background control: `cancel background job`, `stop background job`, `取消后台任务`, `停止后台任务`.
- Next-step and gates: `what should I do next`, `下一步是什么`, `why can't I apply`, `what is blocking apply`, `门禁状态`, `为什么不能应用`.
- Readiness: `readiness`, `readiness for Claude Desktop`, `diagnose`, `patchbay doctor`, `检查环境`, `环境自检`, `检查 Gemini 命令行环境`.
- Economy routing: `show economy profile`, `apply economy profile`, `configure DeepSeek provider`, `configure DeepSeek provider to <command>`, `configure economy provider command to <path>`, `configure reasonix command`, `configure reasonix command to <path>`, `配置 Reasonix 命令`, `把 Reasonix 命令设为 <path>`, `what model will write/fix use`, `is writer using cheap model`, `现在写手是不是走便宜模型`.

## Local-Only Scope

If the user explicitly asks not to use MCP, says an MCP host keeps asking for confirmation, asks for Chrome/browser Skill instead of MCP, or says `please don't use MCP`, `no MCP`, `use Chrome Skill instead of MCP`, `少用这个MCP`, `不要用这个MCP`, `不走 MCP`, `走本地模式`, or `只用本地工具`, do not call MCP tools. Use local commands such as:

```bash
scripts/patchbay setup --no-mcp --json
scripts/patchbay doctor --local-only --json
scripts/patchbay runs --inbox
scripts/patchbay runs --focus
scripts/patchbay agent message "patchbay setup without MCP" --json
scripts/patchbay agent message "readiness without MCP" --json
scripts/patchbay agent message "走本地模式，不走 MCP" --json
```

`readiness without MCP`, `patchbay doctor --local-only`, and `patchbay_doctor(skip_mcp=true)` suppress MCP probe/register follow-up actions in both top-level and nested doctor payloads. Desktop/Web clients should persist the selected setup/readiness host plus a selected local-only/no-MCP preference, restore both after refresh/reopen, start doctor with the stored host plus `skip_mcp=true`, and rewrite ordinary host setup actions such as `patchbay setup for claude-desktop` into `patchbay setup without MCP for claude-desktop`. In local-only mode, expose an explicit `MCP setup` escape hatch that clears the stored local-only preference, keeps the selected host, and sends host-aware MCP-only setup such as `register MCP for Claude Desktop`.

For local no-MCP CLI use, non-JSON `scripts/patchbay doctor` and `scripts/patchbay agent message readiness` should render the readiness summary, checks, routing summary, recommendations, and grouped safe actions. Use `--json` when a host needs the full structured payload.

Non-JSON `scripts/patchbay setup` / `install` and Agent setup replies should render setup step summaries, then the same readiness/action summary. Use `--json` for automation.

Non-JSON `scripts/patchbay config profile show/apply` and Agent profile/routing replies should render profile status, write/fix economy routing, command readiness, next actions, and grouped safe actions. Use `--json` when a host needs the full structured payload.

Non-JSON `scripts/patchbay metrics <run_id>` and Agent metrics replies should render efficiency summary, tier usage, provider usage, routing health, and grouped safe actions. Use `--json` for automation and exact evidence.

Non-JSON Agent guidance replies (`help`, local/no-MCP mode, `next step`, and gate-status prompts) should render capabilities, selected/latest run references, gate diagnostics, next actions, and grouped safe actions instead of dumping nested payloads. Use `--json` for hosts that need every structured field.

Non-JSON `scripts/patchbay status <run_id>`, `scripts/patchbay context <run_id>`, and run-bound Agent status/context replies should render run state, gate state, failure recovery, Agent activity, health cards, routing/efficiency evidence, metrics, provider trail, artifacts, and grouped safe actions. Use `--json` for exact handoff payloads.

Non-JSON `scripts/patchbay events <run_id>`, `scripts/patchbay trace <run_id>`, `scripts/patchbay artifact <run_id> <path>`, and Agent diagnostic view replies should render timelines, artifact previews, requested diagnostic tabs, recovery hints, and grouped safe actions instead of dumping nested payloads. Use `--json` for automation or exact event/artifact data.

Desktop/Web selected-run conversation views should show a compact run snapshot before the event stream, using the handoff/status payload to summarize phase/status, gate progress, economy routing health, and latest provider evidence.

Desktop/Web run inbox lists should render compact per-run quick signals for phase, gate progress, economy routing health, and latest provider evidence when those fields are present on `RunSummary`, so operators can triage multiple runs before opening details.

Desktop/Web clients should persist whether the surface is showing the selected run or the new-task view, diagnostics drawer open state, active diagnostics tab, selected Trace message keyed by run id, sidebar search/status/inbox filters, composer drafts keyed by run id plus a dedicated new-task draft, and a lightweight local conversation transcript across refresh/reopen. The transcript should keep recent selected-run local notes, compact local Agent replies, and the latest new-task Agent reply, while remaining bounded and omitting bulky `context`, `status`, `runs`, `diff`, and background job payloads. If the stored run is no longer present, restore the current `runs.inbox.focus_run_id` or first visible run instead of requesting a stale run. Clear stale inbox filters when the current `runs.inbox.groups` and run summaries no longer expose that group. Clear only the submitted draft after a successful submit; preserve selected-run free-text drafts if send fails.

Desktop/Web topbar refresh controls should refresh the selected run's status, context, provider trace, diff, and artifact preview together. When no run is selected, refresh should remain a run-list refresh.

Desktop/Web selected-run polling should pause idle incremental context refreshes while the document/window is hidden, resume with one immediate refresh when it becomes visible again, and continue polling active background jobs even while hidden so long-running work can still complete and update the run inbox.

Desktop/Web phase-advance controls should catch failed gated/autopilot actions, show an accessible top-level error naming the failed action, and re-enable the controls without relaxing the separate final apply confirmation gate.

Desktop/Web safe diagnostic controls such as `open_run`, `poll_context`, `poll_status`, `poll_events`, and readiness refresh should use the same accessible top-level error path when their read/refresh calls fail.

Desktop/Web local Agent reply action buttons, including `open-latest-run`, setup/readiness, routing, and runs/status follow-ups, should also surface asynchronous failures through the same named accessible error path.

Desktop/Web Trace views should present selected-message, run-timeline, and provider-trace summaries before raw JSON. Keep raw JSON available behind an explicit debug/detail affordance for exact troubleshooting.

Desktop/Web Log and Artifacts views should use `failure_recovery`, status errors, priority artifacts, and the loaded artifact preview to present a failure summary, suggested next step, highlighted error lines, and an artifact index before the raw preview.

Desktop/Web Diff views should summarize changed files, additions, deletions, and hunks before raw patch text. Keep the raw diff available behind an explicit debug/detail affordance.

Desktop/Web Config views should summarize resolved phase routes, provider commands, test allowlists, custom providers, and workflow safeguards before raw config JSON. Keep the raw JSON available behind an explicit debug/detail affordance.

Desktop/Web Providers views should summarize configured phase routes, observed provider usage, provider event trail, economy target, coverage, and economy health before any raw event inspection. Make write/fix economy routing evidence visible without requiring users to read trace JSON.

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

Stateless `status` or `runs` responses may expose `runs.inbox`, per-run `inbox`, `open_run`, `focus_composer`, or readiness actions. Open the concrete run before taking gated actions.

## Runs Inbox

`patchbay_runs`, `scripts/patchbay runs --json`, and stateless Agent `status` / `runs` replies return a structured Agent inbox for multi-run clients. The local non-JSON CLI consumes the same payload: `scripts/patchbay runs` prints the summary, groups, focus, and run list; `scripts/patchbay runs --inbox` prints only the queue view; `scripts/patchbay runs --focus` expands the highest-priority run with next-action and command hints. Non-JSON `scripts/patchbay agent message runs` and `scripts/patchbay agent message status` print the Agent reply, then render the same inbox plus top-level safe actions.

- Top-level `runs.inbox.total`, `groups`, `focus_run_id`, `active_count`, `confirmation_required_count`, `safe_action_count`, and `summary`.
- Per-run `current_phase`, `next_commands`, `gate_state`, `background_job`, `inbox`, `actions[]`, and `action_groups[]`.
- `inbox.key` is one of `running`, `needs_approval`, `ready_to_apply`, `failed`, `ready_to_continue`, `inspect`, or `applied`.
- `inbox.next_action` names the primary next action for that run.
- Gated `approve_and_run` and `apply` actions must be rendered as confirmation-required controls because they carry `requires_confirmation` and `safe: false`.
- Safe direct controls are limited to actions such as `open_run`, diagnostic tabs, polling, and failure inspection.

Use `runs.inbox.focus_run_id` to highlight the most urgent run, but never auto-run its gated `next_action` from a stateless response.

Direct `patchbay_apply`, `scripts/patchbay apply <run_id>`, and Web `POST /api/runs/<run_id>/actions/apply` also require explicit final confirmation (`confirmation: "apply_approved"` or `--confirmation apply_approved`) after reviewing `FINAL.diff`; missing confirmation must not call `service.apply`.

## Background Mode

For long model work, prefer:

```bash
scripts/patchbay agent message "<user task>" --background --json
scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
scripts/patchbay agent message continue --run-id <run_id> --background --json
scripts/patchbay cancel <run_id>
scripts/patchbay context <run_id>
scripts/patchbay events <run_id>
```

Background responses write `JOB.json`, append agent events, and return safe polling actions: `poll_context`, `poll_status`, and `poll_events`, plus `cancel_background_job` when there is an active worker. Polling actions are grouped under `background_polling`; cancellation is grouped under `background_control`. If a job is already active, Patchbay returns `already_running: true` with the same polling/cancel actions instead of starting another worker.

Use `scripts/patchbay cancel <run_id>`, `patchbay_cancel`, or selected-run Agent prompts such as `cancel background job` / `停止后台任务` only to stop the active worker. Cancellation marks `JOB.json` as canceled, releases background locks, appends a cancel event, and leaves plan/apply gates untouched. Do not treat cancellation as approval, retry, or apply.

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
