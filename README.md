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

The default cost profile keeps expensive reasoning in plan/review and sends high-volume implementation and repair work to the lower-cost Reasonix/DeepSeek writer. If the Reasonix command is not configured yet, readiness will surface a `configure_reasonix_command` action before it offers `start_new_task`; send `patchbay agent message "configure reasonix command" --json` to set the default executable, or `patchbay agent message "configure reasonix command to <path>" --json` for a full local path, without starting a model run. The same readiness payload also exposes `configure_deepseek_provider` so a desktop/MCP/Skill client can offer the custom DeepSeek CLI writer template as a low-cost alternative. Localized conversational prompts such as `配置 Reasonix 命令` and `把 Reasonix 命令设为 <path>` are accepted through the same Agent and MCP entry points. Reapply the routing profile at any time with `patchbay config profile apply economy`.

Legacy `[models]`, `[commands]`, and `[writer].provider` keys remain supported as defaults. Each CLI phase may use either `command_key` to reference `[commands]` or `command` for an inline command. `apply` has no model executor; it applies the reviewed `FINAL.diff` only after tests and review pass.

## What It Provides

- CLI workflow: `setup`/`install`, `doctor`, `agent message`, `web`, `plan`, `approve`, `write`, `test`, `review`, `fix`, `cancel`, `status`, `context`, `metrics`, `trace`, `diff`, `apply`, `cleanup`.
- MCP tools: `patchbay_agent`, `patchbay_setup`, `patchbay_install`, `patchbay_plan`, `patchbay_approve`, `patchbay_write`, `patchbay_test`, `patchbay_review`, `patchbay_fix`, `patchbay_cancel`, `patchbay_status`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, `patchbay_skill_install`, `patchbay_skill_print`, `patchbay_skill_doctor`, `patchbay_events`, `patchbay_trace`, `patchbay_runs`, `patchbay_artifact`, `patchbay_config_show`, `patchbay_config_phase_set`, `patchbay_config_command_set`, `patchbay_config_test_add`, `patchbay_config_profile_apply`, `patchbay_config_profile_show`, `patchbay_config_provider_add_cli`, `patchbay_diff`, `patchbay_apply`.
- Legacy MCP aliases: `ai_flow_*`.
- Isolated git worktrees by default.
- File-backed run artifacts under `.ai/runs/<run_id>/`.
- Human approval gate before implementation.
- Patch safety checks, read-only reviewer verification, and a default apply gate that treats skipped tests as not passed unless `workflow.allow_apply_without_tests = true`.
- **Cross-host visibility**: `patchbay context <run_id>` / `patchbay_context` is the preferred resume call. It returns the current gate state, next safe action, provider trail, artifacts, timeline, top-level `routing_evidence` / `efficiency_summary`, and `run_metrics` efficiency evidence in one handoff digest. `run_metrics.routing_evidence` shows whether write/fix are configured for the Reasonix/DeepSeek economy route, whether the Reasonix command can execute, and whether provider events have actually observed it; missing or mismatched explicit `command_key` evidence is treated as routing drift instead of verified economy evidence. `routing_evidence.economy_health` and `agent_activity.health_cards` expose the same signal as machine-readable `healthy`, `pending_evidence`, `command_not_ready`, `drift`, or `not_configured` states, plus an `economy_efficiency` card summarizing `efficiency_summary` for desktop and MCP clients. `patchbay_metrics` also returns top-level `actions[]` and `action_groups[]` mirrored from `routing_evidence.actions[]`, so clients can render safe routing follow-ups such as applying the economy profile, configuring Reasonix, or opening the Trace tab without parsing `economy_health.next_action`. Readiness and setup responses include top-level `routing`, `recommendations`, recommendation-derived `next_actions`, and the same structured action contract; `help` also exposes local-only setup plus host-specific setup/readiness shortcut actions for Codex, Claude Code, Claude Desktop, and Gemini CLI. `patchbay events <run_id>` and `patchbay_status` remain available for focused inspection.
- **Run inbox**: `patchbay runs` now prints a human-readable Agent inbox, while `patchbay runs --inbox` shows only the queue summary and `patchbay runs --focus` expands the highest-priority run with its next action. `patchbay runs --json`, `patchbay_runs`, and stateless Agent `status` / `runs` replies still return `runs.inbox` plus per-run `inbox`, `actions[]`, and `action_groups[]`. The inbox groups runs as running, needing plan approval, ready to apply, failed, ready to continue, inspect, or applied; `focus_run_id` points clients to the highest-priority run. Gated next actions such as `approve_and_run` and `apply` are marked `safe: false` and include `requires_confirmation`, while `open_run`, diagnostics, and polling remain safe local controls.
- **Agent help surface**: `patchbay agent message "help" --json` and `patchbay_agent` help prompts return `capabilities[]` summaries alongside safe `actions[]` and `action_groups[]`, so desktop/MCP/Skill clients can render what the Agent can do without parsing prose. When a concrete `run_id` is supplied, help also returns selected-run `gate_diagnosis.next_action`, `next_action`, status/context, and safe diagnostic/setup actions without advancing gates.
- **Failure recovery**: failed runs expose `failure_recovery` through `status`, `context`, and the conversational Agent, including the failed stage, suggested next action, priority artifacts, structured `actions[]`, and `action_groups[]` for safe inspection or replacement-task follow-ups. `patchbay_context` also lifts those safe recovery choices into `next_actions` / `agent_activity.next_action`, so desktop and MCP clients can show a primary diagnostic action without treating failure recovery as `continue` or `apply`.

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
patchbay setup --host codex     # init + local config + Codex Skill + MCP registration attempt + doctor summary/recommendations
patchbay setup --host codex --no-mcp  # local config + Codex Skill only; no MCP registration/probe follow-ups
patchbay install --host codex    # alias for setup
patchbay config     # Interactive wizard — no hand-editing required
patchbay config profile apply economy  # keep write/fix on Reasonix + DeepSeek
patchbay agent message "apply economy profile" --json  # same routing change through the conversational Agent
patchbay agent message "configure reasonix command" --json  # set commands.reasonix; append `to <path>` or use `把 Reasonix 命令设为 <path>`
patchbay agent message "configure DeepSeek provider" --json  # add a custom DeepSeek CLI provider template
patchbay agent message "configure DeepSeek provider to <command>" --json  # add the template and set providers.<id>.command
patchbay agent message "configure economy provider command to <path>" --json  # repair the active economy writer/fix provider command
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
python scripts/patchbay agent message "configure DeepSeek provider" --json
python scripts/patchbay agent message "configure DeepSeek provider to <command>" --json
python scripts/patchbay agent message "configure economy provider command to <path>" --json
python scripts/patchbay web --port 8765
python scripts/patchbay runs
python scripts/patchbay runs --inbox
python scripts/patchbay runs --focus
python scripts/patchbay approve <run_id>
python scripts/patchbay write <run_id>
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id>
python scripts/patchbay cancel <run_id>
python scripts/patchbay context <run_id>
python scripts/patchbay metrics <run_id>
python scripts/patchbay apply <run_id> --confirmation apply_approved
```

`metrics` includes phase duration/attempt counts, provider usage, token/cost availability, `efficiency_summary` for the verified economy token/cost/time share, and `routing_evidence` with `economy_health` for the write/fix economy route. `runs` includes an Agent inbox: the default text view shows the summary, groups, focus run, and run list; `--inbox` keeps the output to the summary/groups/focus; `--focus` prints the selected run's details and next command hints. Non-JSON `patchbay agent message runs` and `patchbay agent message status` use the same readable inbox renderer instead of dumping the structured payload. Non-JSON `patchbay status`, `patchbay context`, and their run-bound Agent equivalents render run state, gate state, failure recovery, Agent activity, health cards, routing/efficiency evidence, metrics, provider trail, artifacts, and grouped safe actions. Non-JSON `patchbay events`, `patchbay trace`, `patchbay artifact`, and Agent diagnostic view replies render timelines, artifact previews, requested diagnostic tabs, recovery hints, and grouped safe actions instead of raw nested payloads. Non-JSON `patchbay setup` / `install`, `patchbay doctor`, `patchbay config profile show/apply`, `patchbay metrics`, and their Agent equivalents render local summaries for setup steps, readiness checks, write/fix economy routing, efficiency evidence, recommendations, and grouped safe actions. Non-JSON Agent guidance replies such as `help`, local-only/no-MCP prompts, `next step`, and gate-status questions render capabilities, selected/latest run references, gate diagnostics, next actions, and grouped safe actions instead of raw structured payloads. The JSON contract remains top-level `inbox.groups`, `inbox.focus_run_id`, active/confirmation counts, and per-run `inbox.next_action`, `actions[]`, and `action_groups[]` for safe opening/diagnostics plus explicit gated follow-ups. Setup, doctor/readiness, and profile/routing responses also include `routing.workload_policy`, a machine-readable split that labels `write`/`fix` as economy work for simple high-volume implementation and repair, while `plan`/`review` stay on supervision models. Setup/install JSON also lifts doctor `recommendations` to the top level and maps actionable recommendations into short `next_actions` such as `apply economy profile`, `configure reasonix command`, or `configure economy provider command`. For desktop and MCP clients, prefer the returned `actions[]` or `routing_evidence.actions[]` over deriving UI controls from `economy_health.next_action`; those actions are already typed as safe `local_agent`, `command`, or `diagnostic_tab` follow-ups and may include a `command` field for exact CLI fallback display. Responses that include structured actions may also include `action_groups[]`, whose `action_ids` split buttons into stable categories such as `background_polling`, `background_control`, `routing`, `setup`, `diagnostics`, `gate`, `new_task`, and `commands`; clients can use these groups for UI sections without parsing action ids. When `command_not_ready` comes from a custom economy provider, render the `configure_economy_provider_command` copy command before the inspect action so users can fix `providers.<id>.command` directly.

Use `--background` for long conversational turns so the caller can return immediately and poll status/events:

```bash
python scripts/patchbay agent message "..." --background --json
python scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
python scripts/patchbay agent message continue --run-id <run_id> --background --json
```

Background agent turns write `JOB.json`, append `agent` events, and preserve the plan/apply confirmation gates. `apply` remains foreground-only and requires explicit confirmation after tests and review pass. Background responses include safe structured `actions[]` for opening the run, opening Trace, polling status, polling context, polling events, and canceling the active worker; `action_groups[]` marks polling controls as `background_polling` and the cancel control as `background_control`, while keeping simultaneous economy/profile repair actions in the separate `routing` group. Active background jobs also lift `poll_context`, `poll_status`, `poll_events`, and `cancel_background_job` into `patchbay_context.next_actions`, top-level `action_groups[]`, and `agent_activity.conversation_state.suggestions`, so clients can refresh or stop work from the handoff payload without parsing `JOB.json` or exposing gated actions. They never expose `continue`, `approve`, or `apply` as direct background follow-ups. Use `patchbay cancel <run_id>`, `patchbay_cancel`, or `patchbay agent message "cancel background job" --run-id <run_id> --json` to terminate the active background process, mark `JOB.json` as canceled, release background locks, and leave apply gates untouched. If a client sends another background `approve`/`continue` while an Agent job is already active, Patchbay returns the existing job with `already_running: true` and the same safe polling/cancel actions instead of spawning a duplicate worker. When a concrete `run_id` is already selected, explicit unattended phrases such as `don't ask me`, `assume yes`, `you have all permissions`, or `不要问我 / 别找我 / 所有权限全都给你 / 自己允许 / 我根本不在身边` count as plan approval for that run and can start the background write/test/review autopilot; the same phrases without a `run_id` return `missing_run` guidance instead of choosing a run implicitly, and final `apply` still requires its separate confirmation. Local prompts such as `patchbay setup`, `patchbay setup for Claude Desktop`, `install patchbay for Gemini CLI`, `install Codex Skill`, `register MCP for Claude Desktop`, `安装 Codex Skill`, `注册 MCP 到 Gemini 命令行`, `帮我配置 Patchbay`, `帮助我配置 Patchbay 到 Claude 桌面`, `help`, `Patchbay 怎么用`, `使用说明`, `status`, `runs`, `查看最近运行`, `任务列表`, `what should I do next`, `下一步是什么`, `why can't I apply`, `what is blocking apply`, `门禁状态`, `为什么不能应用`, `readiness`, `readiness for Claude Desktop`, `diagnose`, `patchbay doctor`, `检查环境`, `环境自检`, `检查 Gemini 命令行环境`, `show economy profile`, `apply economy profile`, `configure DeepSeek provider`, `configure economy provider command to <path>`, `configure reasonix command`, `configure reasonix command to <path>`, `配置 Reasonix 命令`, `把 Reasonix 命令设为 <path>`, `cancel background job`, `stop background job`, `取消后台任务`, or `停止后台任务` return setup results, guidance, recent runs, readiness, routing changes, gate diagnostics, command templates, command configuration, or background cancellation directly without creating a model run. Host-targeted readiness prompts populate `setup_host` and `doctor.host`, so desktop clients can switch the Readiness host and show concrete MCP probe/setup commands without parsing prose. Foreground start stays at the `PLANNED` gate and background start stays pollable, but both now include a read-only `profile`, `routing`, and safe `actions[]` preview so clients can show whether write/fix are already on the cheaper economy route, or render `apply_economy_profile` / `configure_reasonix_command` before approval. Next-step questions return `action: "next_step"` with the latest run handoff, `next_action` / `run_reference.next_action`, confirmation requirements, and safe `actions[]`; they do not execute `continue`, `approve`, or `apply` until a concrete run is open and the required confirmation is supplied. Gate-status questions return `action: "gate_status"` with `gate_diagnosis`, `gate_diagnosis.next_action`, blocker checks, and safe diagnostic/open-run actions; blocked direct `apply` on a selected run returns the same `gate_diagnosis.next_action` and safe diagnostic actions instead of asking for apply confirmation. These paths do not approve plans, run tests, review, or apply patches. Natural-language cost routing prompts such as "use DeepSeek for simple writer work", "大量简单写手工作让便宜模型/DeepSeek 去干", or "降本，让简单 writer/fix 走低价模型" also apply the economy profile instead of starting a new run. Help/setup/readiness/status/profile/next_step/gate_status/background_cancel payloads include machine-readable `actions[]` with `id`, `label`, `kind`, `safe`, `reason`, and either `message`, `command`, `host`, `run_id`, or `tab`; local run handoffs can also use `next_action`, `open_run`, and `focus_composer`. `patchbay_config_profile_show` / `patchbay_config_profile_apply` expose the same structured action contract for MCP and CLI clients. `status`/`runs` without a `run_id` only expose safe local actions such as opening the latest run, focusing the composer, or readiness diagnostics; gated actions like `continue`, `approve`, and `apply` are chosen only after a run is opened. Run-bound prompts such as `continue`, `approve`, `apply`, `context`, `events`, `diff`, `artifact`, or `查看失败原因` without a `run_id` also stay local; when a recent run exists, the response includes a latest-run handoff plus structured `actions[]` to open it before any gated action is chosen. View prompts such as `context`, `handoff context`, `diff`, `events`, `logs`, `artifact`, or `查看失败原因` include `requested_view`; when a run is already selected, they also return safe `diagnostic_tab` actions so clients can open the matching diagnostics tab without running a phase.

Unattended selected-run approval also accepts natural variants such as `full access`, `approve yourself`, `别找我`, `所有权限全都给你`, `无需向我确认`, `完全访问权限`, `自己允许`, and `我根本不在身边`; without a selected `run_id`, those phrases still stay local and do not create or advance a run.

Mixed Chinese/English cost prompts such as `简单 writer/fix 用 DeepSeek 省钱` or `降本，让简单 writer/fix 走低价模型` are treated as economy-routing intent and apply the write/fix economy profile instead of opening a new task run.

Routing questions such as `what model will write/fix use`, `is writer using cheap model`, or `现在写手是不是走便宜模型` are read-only `profile_show` prompts. When a run id is provided, the reply also includes that run's `metrics.efficiency_summary` evidence so clients can distinguish configured routing from observed provider/token/cost behavior. Readiness views can render the top-level `doctor.routing` immediately, and routing/profile replies can render top-level `routing`; use `routing.workload_policy.summary` when the user asks why simple writer/fix work should use the cheaper route. Imperative routing prompts such as `apply economy profile` or “use DeepSeek for simple writer work” are the ones that mutate local routing configuration.

The web workbench exposes the same conversational flow and has a diagnostics drawer. Its Readiness tab calls the unified doctor checks without MCP stdio probing, so setup gaps are visible from the desktop UI without starting extra child processes. The Readiness host selector passes the target host into doctor/setup, persists the selected setup/readiness host across refresh/reopen, and uses concrete registrations such as `patchbay mcp install claude-desktop` instead of placeholder host names. It also shows the active write/fix routing profile and renders structured `actions[]` for safe setup, Skill, MCP probe, refresh, and economy-routing follow-ups, grouped by `action_groups[]` into stable sections such as routing and setup. When no run is selected, the composer shows a compact start context card with local/no-MCP mode, readiness state, write/fix economy routing, and safe setup/economy actions before a new plan is created. The run composer also groups `agent_activity.conversation_state.suggestions` with `patchbay_context.action_groups[]`, so background polling, background control, diagnostics, and gated actions appear as separate controls instead of a flat button list. If an installed Codex Skill is outdated, the check card shows `status: outdated`, missing/changed/extra installed files, and the safe update action. Local conversational replies render safe `command` actions as copyable command rows with a fallback copy path, and failed Clipboard/fallback copy attempts show a visible unavailable state, so MCP/Skill registration commands are usable without opening diagnostics even when Clipboard API access is unavailable. Background job cards expose open-activity, refresh, and cancel controls for long-running turns. The selected-run conversation shows a compact run snapshot with phase/status, gate progress, economy routing health, and latest provider evidence before the detailed event stream. The sidebar run inbox also renders compact per-run quick signals for phase, gates, economy routing, and latest provider evidence, so operators can triage multiple tasks before opening a run. The Overview tab surfaces economy routing and `economy_efficiency` health cards from `agent_activity.health_cards`, so drift from the intended cheaper write/fix route and actual token/cost/time evidence are visible without parsing logs. The Trace tab renders selected-message, run-timeline, and provider-trace summaries as readable cards first, while keeping raw JSON collapsed for exact debugging. The Diff tab summarizes changed files, additions, deletions, and hunks before keeping raw patch text collapsed. The Log and Artifacts tabs reuse `failure_recovery`, status errors, priority artifacts, and the loaded artifact preview to show a failure summary, suggested next step, highlighted error lines, and an artifact index before the raw preview. The Config tab summarizes phase routes, provider commands, test allowlists, custom providers, and workflow safeguards before keeping raw config JSON behind a detail affordance. The Providers tab summarizes configured phase routes, observed provider usage, event trail, economy target, coverage, and health so writer/fix economy routing can be checked without reading raw events.

Command rows show the exact command text visible inline before the copy button, so provider repair commands remain inspectable in screenshots and when clipboard access fails.

The workbench also persists whether it is showing the selected run or the new-task view, diagnostics drawer open state, active diagnostics tab, selected Trace message per run, sidebar search/status/inbox filters, and composer drafts for each run plus the new-task composer across refresh/reopen. Its topbar refresh reloads the selected run's status, context, provider trace, diff, and artifact preview together instead of only refreshing the sidebar run list, and failed refreshes show a named accessible error while re-enabling the control. Initial run-list loading, startup readiness loading, selected-run detail loading, and selected-run polling failures also show named accessible errors instead of raw exception strings. Selected-run polling now pauses idle incremental context refreshes while the document is hidden, resumes with one immediate refresh when it becomes visible, and keeps active background jobs polling while hidden so long-running work still completes. Phase-advance controls catch failed gated/autopilot actions, show an accessible top-level error naming the failed action, and re-enable the controls without relaxing the final apply confirmation gate. Safe diagnostic controls such as open-run, poll context/status/events, readiness actions, and local Agent reply actions such as opening the latest run use the same visible error path when their refresh calls fail, including `open-latest-run` replies that lack a run reference. Setup/readiness/economy/provider configuration failures also name the failed action or selected host and re-enable the triggering setup/profile/readiness controls. It now preserves a lightweight, bounded local conversation transcript too: recent selected-run local notes, compact local Agent replies, and the latest new-task Agent reply survive refresh/reopen, while bulky `context`, `status`, `runs`, `diff`, and background job payloads are deliberately omitted. If the stored run is no longer present, it falls back to the current inbox focus instead of requesting a stale run. Stale inbox filters are cleared when the current run inbox no longer exposes that group. Drafts are cleared after successful submit; selected-run free-text send failures show a named accessible error and preserve the draft.

Copyable command controls reset their copied/unavailable state whenever readiness or Agent responses replace the underlying command, so stale feedback is not carried across provider repair commands.

When doctor returns the structured `configure_deepseek_provider` action, the Readiness tab may render a guarded economy-provider form that creates a custom DeepSeek CLI writer/fix provider and activates economy routing. Healthy readiness alone should keep that form hidden, so clients do not expose mutating provider setup when there is no setup gap.

Setup scope is inferred from the prompt: `install Codex Skill` installs the Skill without attempting MCP registration, `register MCP for Claude Desktop` skips Skill installation, and explicit `patchbay setup without MCP` / `--skip-mcp` / `--no-mcp` / `--local-only` keeps setup local to project files and Skill installation. Standalone conversational avoidance such as `please don't use MCP`, `no MCP`, `use Chrome Skill instead of MCP`, `少用这个MCP`, or `不要用这个MCP` returns `action: "local_mode"` with safe local CLI/Skill/readiness actions instead of running setup or starting a model run. The same avoidance scope applies to `readiness` / `doctor` prompts, so `readiness without MCP` and `patchbay doctor --local-only` suppress MCP probe/register follow-up actions in both the top-level response and nested doctor payload. The web doctor endpoint accepts `skip_mcp=true`, and local-mode readiness actions force-refresh doctor with that flag so the desktop workbench does not reuse MCP-oriented follow-ups; once selected, the workbench stores local-only mode and the selected setup/readiness host in browser storage, restores them after refresh/reopen, starts doctor with that host plus `skip_mcp=true`, and rewrites ordinary host setup buttons such as `patchbay setup for claude-desktop` to `patchbay setup without MCP for claude-desktop`. The persisted preference is reversible: the start context and Readiness panel show an explicit `MCP setup` action in local-only mode, which clears the local-only preference while keeping the selected host and sends host-aware MCP-only setup such as `register MCP for Claude Desktop`.

Chinese local-only phrases such as `不走 MCP`, `走本地模式`, and `只用本地工具` are handled the same way: the Agent returns local CLI/Skill/readiness actions and avoids MCP probe/register follow-ups.

Implicit local browser preferences such as `use Chrome Skill`, `use browser skill`, `use your built-in browser`, or `用你自带的浏览器功能` also select `local_mode` even when the message does not explicitly mention MCP, so they do not create a model run.

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
codex mcp add patchbay -- patchbay-mcp --root /path/to/repo
```

Use the equivalent MCP server registration command for other MCP hosts, quoting `/path/to/repo` if it contains spaces. Run `patchbay doctor --host <host>` for lightweight readiness checks with concrete structured registration actions for that host. Add `--probe-mcp` or run `patchbay mcp doctor` only when you specifically need stdio server reachability and tool-list evidence.

`patchbay doctor` is read-only and reports project initialization, phase config validity, CLI shim/installed command availability, bundled Skill source, whether the Codex Skill is installed and current, and MCP follow-up actions; it skips stdio MCP probing by default so routine readiness checks do not spawn the MCP server. Use `patchbay doctor --local-only` when the current host should not show MCP probe/register actions at all. It returns prose `next_actions`/`recommendations` plus structured `actions[]` for desktop/MCP clients, including `Update Codex Skill` when the installed Skill no longer matches the bundled source. `patchbay doctor --probe-mcp` and `patchbay mcp doctor` start the stdio MCP server, send `initialize` and `tools/list`, and verify required tools including `patchbay_agent`, `patchbay_plan`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, `patchbay_install`, `patchbay_skill_install`, and `patchbay_skill_doctor`. For Codex, Claude Code, and Gemini, `mcp install` now tries to register automatically and falls back to the command text if the host CLI is unavailable; Claude Desktop writes its JSON config in place. Host names accept English and common Chinese aliases, such as `Claude Desktop`, `Claude 桌面`, `Claude Code`, `Claude 代码`, `Gemini CLI`, and `Gemini 命令行`.

After MCP registration, restart or reload the target host if it caches tool lists. Verify with `patchbay mcp doctor --json`, or from the host by checking that `patchbay_agent` is visible.

## Codex Skill Install

Patchbay also ships as a Codex Skill. The Skill teaches Codex when to invoke the gated workflow; the MCP server provides the tools.

```bash
patchbay skill install codex
patchbay skill doctor codex
patchbay skill print codex --json
```

The Skill host argument accepts Codex aliases such as `Codex Desktop`, `Codex CLI`, and `Codex 桌面`; responses still use the canonical `codex` host.

`patchbay skill doctor` validates both the bundled Skill source and the installed copy. If the installed Skill is stale, missing files, or contains old extra files, it reports `status: "outdated"`, `installed_matches_source: false`, `missing_installed_files`, `changed_installed_files`, and `extra_installed_files`, then returns a safe reinstall action.

The Skill is intentionally compact for lower context cost. `SKILL.md` keeps only the trigger, entry-choice, gate, local-only, economy, and background rules. Detailed setup guidance lives in `references/install.md`, and structured Agent/Desktop/MCP response handling lives in `references/agent-contract.md`. `patchbay skill print codex --json` returns all bundled files, while `patchbay skill doctor` treats both references as required source files and reports drift if the installed copy is missing or stale.

By default the Skill installs to `$CODEX_HOME/skills` or `~/.codex/skills`. It triggers on phrases such as "走多模型流程", "multi-agent workflow", Patchbay setup/install, Codex Skill installation, and no-MCP/local-only Patchbay work; MCP tools still need MCP registration when the host wants tool calls.
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

User-defined CLI providers can be configured under `[providers.<id>]` with `roles`, `command`, `args`, `prompt_mode`, and `output_contract`. Use `patchbay config provider add-cli ...` to add them without hand-editing TOML; add `--activate-economy --economy-model <model> --economy-label <label>` to register a low-cost writer and immediately route write/fix work through it. The Web API exposes the same path through `POST /api/providers` with `activate_economy`, `economy_model`, and `economy_label`, returning the same routing status and safe actions for desktop clients. The conversational Agent can do the same when the command is explicit: `patchbay agent message "configure DeepSeek provider to deepseek-writer" --json`; without a command, `configure DeepSeek provider` returns a safe copyable command template instead of mutating config. If the wrapper path changes later, send `configure economy provider command to <path>` or paste the returned `patchbay config --set-key providers.<id>.command --set-value <path>` action back into `patchbay_agent` to repair only the command. The current runtime supports CLI providers; [docs/custom-providers-plan.md](docs/custom-providers-plan.md) tracks the broader future design for HTTP/ACP modes and stricter provider-specific safety controls.

Desktop and Web clients should render the economy provider setup UI only from the structured `configure_deepseek_provider` readiness action. That keeps custom low-cost writer setup discoverable when needed while avoiding surprise config mutation in healthy environments.

```bash
patchbay config provider add-cli cheap_writer --roles write fix --command deepseek-writer --output-contract writer_diff --activate-economy --economy-model deepseek-chat --economy-label "DeepSeek cheap writer"
```

## License

MIT
