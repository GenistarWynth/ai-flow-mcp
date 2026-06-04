# Patchbay

Patchbay 是一个本地补丁编排器：任意支持 MCP 的客户端都可以作为入口（Claude Code、Claude Desktop、Codex CLI、Codex Desktop、Gemini CLI 等），默认把规划、实现、测试、审查和应用拆成可审计阶段。默认角色绑定是 Claude 规划、Reasonix (默认 Agent) 实现、Codex 审查；每个阶段都可以通过配置换成其他工具。

## 快速安装

```bash
# npx 风格（推荐）
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay doctor
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay web --port 8765
# 打开 http://127.0.0.1:8765

# 一条命令初始化本地项目、配置、Skill，并尝试注册 MCP
patchbay setup --host codex --json
patchbay setup --host codex --no-mcp --json # 本地配置 + Skill，不返回 MCP 注册/探测后续动作
patchbay install --host codex --json   # setup 的别名

# 交互式配置（无需手动编辑 TOML）
patchbay config                      # 交互式向导
patchbay config profile apply economy # write/fix 走 Reasonix + DeepSeek，适合大量简单实现/修复
patchbay agent message "apply economy profile" --json # 对话式 Agent 本地应用同一配置
patchbay agent message "configure reasonix command" --json # 配置 commands.reasonix；可追加 `to <path>`
patchbay config --set-key models.planner --set-value claude-opus-4-7   # 单键设置
patchbay doctor                      # 统一检查 config/Skill，就绪检查默认不启动 stdio MCP
patchbay doctor --local-only         # 不返回 MCP probe/register 后续动作
patchbay doctor --probe-mcp          # 需要 tools/list 证据时再探测 MCP
patchbay config --doctor             # 验证配置

# MCP 注册（可自动执行；失败时返回可复制命令）
patchbay mcp install codex           # Codex CLI / Codex Desktop
patchbay mcp install claude          # Claude Code
patchbay mcp install claude-desktop  # Claude Desktop
patchbay mcp install gemini          # Gemini CLI
patchbay mcp doctor                  # 只检查 stdio server 和核心工具

# Codex Skill
patchbay skill install codex
patchbay skill doctor codex
patchbay skill print codex --json

# 本地对话式 workbench
patchbay web --port 8765
# 打开 http://127.0.0.1:8765
patchbay agent message "..." --json
```

## 环境准备

- 确保所需 CLI 已登录并可调用（按你要用的 provider 准备）：
  - Planner：`claude`（Claude Code）、`codex`（Codex CLI）或 `gemini`（Gemini CLI）
  - Writer：Reasonix CLI（`reasonix` / `reasonix.cmd`，默认 Agent）
  - Reviewer：`codex`（Codex CLI）、`claude`（Claude Code）或 `gemini`（Gemini CLI）
- 使用 Reasonix CLI 时，确保 `reasonix acp` 可用。

## 配置

```bash
scripts/patchbay init
cp .ai/patchbay.example.toml .ai/patchbay.toml
```

按需编辑 `.ai/patchbay.toml`，尤其是 writer provider、命令路径和测试 allowlist。

### 按阶段绑定 provider

每个工作流阶段可以独立配置 provider 和模型：

```toml
[phases.plan]
provider = "claude_cli"      # claude_cli | codex_cli | gemini_cli | mock
model = "claude-opus-4-7"

[phases.write]
provider = "reasonix_cli"    # reasonix_cli | mock
model = "deepseek-v4-pro"

[phases.review]
provider = "codex_cli"       # codex_cli | claude_cli | gemini_cli | mock
model = "gpt-5.5"

[phases.test]
commands = ["python -m unittest discover -s tests -v"]
timeout = 900

[phases.fix]
# 默认跟随 phases.write 的 provider 和 model
```

旧配置节 `[models]`、`[commands]` 和 `[writer].provider` 继续有效，作为未设置 phase 时的默认值。

默认经济型分工是：规划/审查使用更强模型，写代码和修复这类大量重复工作走 Reasonix/DeepSeek writer。若本地配置偏离了这套分工，可运行 `patchbay config profile apply economy` 一键恢复。也可以用 `[profiles.economy]` 把 economy 目标改成任意低成本 provider/model；`apply economy profile`、doctor、metrics 和 Web workbench 都会按这个目标判断是否已走经济路由。

```toml
[profiles.economy]
provider = "reasonix_cli"
model = "deepseek-v4-pro"
command_key = "reasonix"
label = "Reasonix/DeepSeek"
```

`setup`、`doctor` / `readiness`、`show economy profile`、`apply economy profile` 和 start preview 会在 `routing.workload_policy` 返回同一份机器可读分工：`write`/`fix` 是 economy 阶段，适合大量简单实现和修复；`plan`/`review` 是 supervision 阶段，继续使用更强模型做规划和审查。setup/install JSON 还会把 doctor 的 `recommendations` 提升到顶层，并把可执行建议映射成 `apply economy profile`、`configure reasonix command` 或 `configure economy provider command` 这类短 `next_actions`。桌面端、MCP host 和 Skill 可以直接渲染 `setup.routing`、`doctor.routing` 或响应顶层 `routing` 里的 `summary`、`economy_phases`、`supervision_phases` 和 `phase_roles`，不用解析自然语言来解释“性价比”路由。

Writer 实现入口：

- `reasonix_cli`：调用 Reasonix ACP coding agent（`reasonix acp`），由 Reasonix 自己的文件系统工具修改独立 worktree，Patchbay 只负责审批权限并捕获最终 `git diff`。

## 跨阶段可见性

任何 MCP host 都可以查看其他 agent/阶段做了什么或正在做什么：

```bash
# CLI
scripts/patchbay doctor --json            # 统一查看安装、配置、Skill 和 MCP 后续动作
scripts/patchbay doctor --local-only --json # 隐藏 MCP probe/register 后续动作
scripts/patchbay doctor --probe-mcp --json # 需要时再验证 MCP initialize/tools-list
scripts/patchbay context <run_id>          # 推荐：一次性查看 handoff 摘要、门禁、下一步、产物和时间线
scripts/patchbay events <run_id>           # 展示完整事件日志
scripts/patchbay events <run_id> --phase plan  # 按阶段筛选
scripts/patchbay events <run_id> --since 5     # 从第 5 条事件开始
scripts/patchbay trace <run_id>            # 展示 trace 时间线
scripts/patchbay artifact <run_id> PLAN.md # 预览运行产物
scripts/patchbay status <run_id>           # status 现在包含 latest_event 和 event_count
scripts/patchbay metrics <run_id>          # 只查看 run_metrics 效率证据
```

MCP 工具 `patchbay_agent` 是对话式入口，能启动、恢复和推进运行，但仍保留计划批准和 apply 确认门禁。`patchbay_setup` / `patchbay_install` 是一键初始化入口，能创建项目文件、局部配置、Skill，并尝试注册 MCP，同时返回顶层 `routing`、`recommendations` 和推荐项派生的 `next_actions`。`patchbay_agent` 的 `readiness`/`doctor`/`configure reasonix command` 本地响应、`patchbay_doctor` 和 setup/install 结果都会返回 `actions[]`：每项包含 `id`、`label`、`kind`、`safe`、`reason`，并按类型携带 `message`、`command`、`host` 或 `tab`，让桌面/MCP 客户端可以直接渲染安全的一键后续操作；响应中有结构化动作时还可能返回 `action_groups[]`，用 `action_ids` 把按钮稳定分成 `background_polling`、`background_control`、`routing`、`setup`、`diagnostics`、`gate`、`new_task`、`commands` 等组，客户端不需要解析 action id 来排版。`patchbay_doctor --host claude-desktop` 这类调用会把 `host` 规范化到响应顶层，并让 `install_mcp`、`run_setup`、`refresh_readiness` 等动作继承该 host，避免客户端再从自然语言里推断目标 MCP host；若 Codex Skill 缺失或过期，顶层 `install_skill` 动作会复用 Skill doctor 的安全动作，默认路径用 `local_agent`，自定义 `skill_path` 保持 command。`patchbay_context` 是跨 host 恢复上下文的首选只读入口，并在顶层直接返回 `routing_evidence` 和 `efficiency_summary`；`patchbay_metrics` 可单独读取阶段耗时、`run_metrics.tier_usage` 里的 economy/write-fix、supervision/plan-review、execution/test-apply 聚合消耗、`run_metrics.efficiency_summary` 里的经济路由 token/cost/time 占比摘要、尝试次数、provider 使用轨迹、事件/trace 数、成本/token 上报状态，以及 `run_metrics.routing_evidence` 里的 write/fix 经济路由配置、Reasonix 命令可执行状态与实际 provider 事件证据。`routing_evidence.economy_health` 会把经济路由归一为 `healthy`、`pending_evidence`、`command_not_ready`、`drift` 或 `not_configured`，`agent_activity.health_cards` 会把同一信号作为桌面/MCP handoff 卡片暴露给客户端，并额外给出 `economy_efficiency` 和 `economy_load` 卡片，显示效率摘要以及 write/fix 的 token、成本和耗时占比。`patchbay_metrics` 还会把 `routing_evidence.actions[]` 镜像到顶层 `actions[]` 和 `action_groups[]`；桌面/MCP 客户端应优先渲染这些 `safe: true` 的结构化动作，例如 `local_agent` 的 `apply economy profile`、`configure reasonix command`、`command` 的 `configure_economy_provider_command` 或 `diagnostic_tab` 的 Trace 跳转，而不是解析 `economy_health.next_action` 字符串。失败运行会在 `status`、`context` 和对话式 Agent 响应里暴露 `failure_recovery`，包含失败阶段、建议动作、安全检查动作、`action_groups[]` 和应优先查看的产物；`patchbay_context` 会把这些安全恢复动作同步提升到 `next_actions` 和 `agent_activity.next_action`，方便桌面/MCP 客户端展示主诊断动作，但不会把失败恢复当作 `continue` 或 `apply`。`patchbay_events` 和 `patchbay_status` 仍可用于聚焦查看。每条事件记录包含 `phase`、`provider`、`model`、`action`、`status`、`timestamp`、`detail`、`artifact_paths`、`duration_ms` 和 `next_action`。

`patchbay_runs`、`scripts/patchbay runs --json` 和无 `run_id` 的 Agent `status` / `runs` 响应会返回同一份结构化 Agent inbox。顶层 `runs.inbox` 包含 `groups`、`focus_run_id`、`active_count`、`confirmation_required_count` 和摘要；每个 run 包含 `current_phase`、`next_commands`、`gate_state`、`background_job`、`inbox`、`actions[]` 和 `action_groups[]`。本地 CLI 的非 JSON 输出直接消费同一 payload：`scripts/patchbay runs` 打印摘要、分组、焦点和运行列表，`--inbox` 只显示队列视图，`--focus` 展开最高优先级 run 的详情、下一步动作和建议命令；非 JSON `scripts/patchbay agent message runs` / `status` 会先显示 Agent 回复，再渲染同一 inbox 和顶层安全动作。`inbox.key` 会把 run 归为 `running`、`needs_approval`、`ready_to_apply`、`failed`、`ready_to_continue`、`inspect` 或 `applied`，桌面/MCP/Skill 客户端可直接把它渲染成多任务工作队列。`inbox.next_action` 中的 `approve_and_run` 与 `apply` 始终带 `requires_confirmation` 且 `safe: false`；只读 `open_run`、诊断 tab、后台轮询和失败检查动作才应作为直接安全按钮。

本地非 JSON `scripts/patchbay status`、`scripts/patchbay context` 和带 run_id 的对应 Agent 消息会渲染 run 状态、门禁状态、失败恢复、Agent 活动、健康卡片、路由/效率证据、metrics、provider trail、产物和分组安全动作；非 JSON `scripts/patchbay events`、`scripts/patchbay trace`、`scripts/patchbay artifact` 和 Agent 诊断视图回复会渲染时间线、产物预览、请求的诊断 tab、恢复提示和分组安全动作；非 JSON `scripts/patchbay setup` / `install` 会把 setup payload 渲染为 dry-run/applied 状态、root/host、init/config/Skill/MCP 步骤、内嵌 readiness 摘要和按 `action_groups[]` 分组的安全动作；非 JSON `scripts/patchbay doctor`、`scripts/patchbay config profile show/apply`、`scripts/patchbay metrics`、`scripts/patchbay agent message readiness` 和 profile/routing/metrics Agent 消息会把同一份结构化 payload 渲染为就绪状态、检查项、write/fix 经济路由、效率证据、建议和安全动作；非 JSON `help`、本地/no-MCP、next-step 和 gate-status Agent 消息会渲染能力列表、选中/最近 run、门禁诊断、下一步和分组安全动作，避免 no-MCP/Skill-only 路径把嵌套 JSON 直接暴露给用户；加 `--json` 时仍返回完整结构化契约。

## 常用命令

```bash
scripts/patchbay plan --task "..."
scripts/patchbay agent message "..."
scripts/patchbay agent message "patchbay setup" --json
scripts/patchbay agent message "patchbay setup for Claude Desktop" --json
scripts/patchbay agent message status --json
scripts/patchbay agent message context --json
scripts/patchbay agent message readiness --json
scripts/patchbay agent message "configure reasonix command" --json
scripts/patchbay agent message "..." --background --json
scripts/patchbay agent message continue --run-id <run_id> --background --json
scripts/patchbay agent message metrics --json   # 无 run_id 时读取最近一次运行的效率证据
scripts/patchbay agent message diff --json      # 无 run_id 时读取最近一次运行的只读视图
scripts/patchbay web --port 8765
# 打开 http://127.0.0.1:8765
scripts/patchbay approve <run_id>
scripts/patchbay write <run_id>
scripts/patchbay test <run_id>
scripts/patchbay review <run_id>
scripts/patchbay fix <run_id>
scripts/patchbay cancel <run_id>
scripts/patchbay status <run_id>
scripts/patchbay metrics <run_id>
scripts/patchbay events <run_id>
scripts/patchbay trace <run_id>
scripts/patchbay artifact <run_id> PLAN.md
scripts/patchbay diff <run_id>
scripts/patchbay apply <run_id> --confirmation apply_approved
scripts/patchbay cleanup <run_id>
```

`--background` is intended for the conversational agent path: planning and approve/continue turns return a pollable `run_id`, write `JOB.json`, and surface progress through `patchbay_status`, `patchbay_context`, and `patchbay_events`. Background `JOB.json`, `status`, `context`, and immediate agent responses include safe follow-up actions for `open_background_run`, `open_trace`, `poll_status`, `poll_context`, `poll_events`, and `cancel_background_job`; `action_groups[]` marks polling buttons as `background_polling` and the cancel button as `background_control`, separately from routing/setup/diagnostic actions. Active background jobs also lift `poll_context`, `poll_status`, `poll_events`, and `cancel_background_job` into `patchbay_context.next_actions`, top-level `action_groups[]`, and `agent_activity.conversation_state.suggestions`, so Desktop/MCP clients can refresh or stop work from the handoff payload without parsing `JOB.json` or exposing gated actions. Desktop/MCP clients should prefer `poll_context` when they need the refreshed handoff payload, `poll_events` when they only need the event stream, and `cancel_background_job` when the selected run must stop without approving, applying, or advancing gates. The same cancellation is available through `scripts/patchbay cancel <run_id>`, `patchbay_cancel`, or selected-run Agent prompts such as `cancel background job` / `停止后台任务`; it terminates the recorded process, marks `JOB.json` canceled, releases background locks, and leaves apply confirmation untouched. If a client sends another background approve/continue while an Agent job is active, Patchbay returns the existing job with `already_running: true` and the same safe polling/cancel actions instead of spawning a duplicate worker. Destructive apply remains foreground-only and still requires explicit confirmation. Explicit local setup/routing prompts such as `patchbay setup`, `patchbay setup for Claude Desktop`, `patchbay setup without MCP`, `install patchbay for Gemini CLI`, `patchbay install`, `apply economy profile`, `configure DeepSeek provider`, `configure economy provider command to <path>`, `configure reasonix command`, or `configure reasonix command to <path>` run local setup/config updates or return safe setup command templates without creating a model run. Standalone MCP-avoidance prompts such as `please don't use MCP`, `no MCP`, `use Chrome Skill instead of MCP`, `少用这个MCP`, or `不要用这个MCP` return `action: "local_mode"` with safe local CLI/Skill/readiness actions instead of running setup. The same MCP-avoidance scope applies to `readiness` / `doctor` prompts, so `readiness without MCP`, `patchbay doctor --local-only`, and `patchbay_doctor(skip_mcp=true)` hide MCP probe/register actions from both the top-level response and nested doctor payload. These local setup/readiness/status/profile/local_mode/background_cancel payloads include `actions[]` entries whose `kind` is currently `local_agent`, `command`, `diagnostic_tab`, `open_run`, or `focus_composer`; clients should render only entries with `safe: true` as direct actions. `help` responses include `capabilities[]`; when a selected `run_id` is supplied, help also returns that run's `gate_diagnosis.next_action`, top-level `next_action`, status/context, and safe diagnostic/setup actions without advancing gates. `next_step` responses also include `next_action` for a selected run, or `run_reference.next_action` plus a safe top-level `open_run` action when no run is selected, so clients can display the gated action and its confirmation requirement without parsing prose. `status` or `runs` without a `run_id` can return an `open_run` action for the latest run, or `focus_composer` plus readiness diagnostics when no runs exist, but should not render `continue`, `approve`, or `apply` as stateless direct actions. If the user sends `continue`, `approve`, or `apply` without a `run_id`, Patchbay returns local guidance instead of choosing a run automatically. Read-only prompts such as `metrics`, `context`, `handoff context`, `diff`, `events`, `logs`, `artifact`, or `查看失败原因` can inspect the latest run when one exists and include an `open_latest_run` action plus `requested_view` for desktop clients.

Natural Chinese routing prompts such as `降本，让简单 writer/fix 走低价模型` and `优化成本，让写手工作走低价模型` apply the economy profile without creating a run; ordinary product tasks such as `优化成本仪表盘` still start a planned run.

Foreground planning/start responses remain at the plan approval gate, and background planning/start responses remain pollable. Both include a read-only `profile`, `routing`, safe `actions[]`, and `action_groups[]` preview so Desktop, MCP, and Skill clients can show before approval whether high-volume write/fix work is already routed to the cheaper economy provider, and can render safe local follow-ups such as `apply_economy_profile` or `configure_reasonix_command` without advancing the run.

Web workbench 使用同一套对话式 Agent 流程。`patchbay_agent` 和 `scripts/patchbay agent message "patchbay setup" --json` / `status --json` / `readiness --json` / `"metrics" --json` / `"diff" --json` / `"apply economy profile" --json` / `"configure DeepSeek provider" --json` / `"configure economy provider command to <path>" --json` / `"configure reasonix command" --json` / `"configure reasonix command to <path>" --json` 可直接返回 setup 结果、最近运行、统一 doctor 报告、最近运行效率证据、最近运行只读视图、经济路由配置结果、自定义低成本 provider 注册命令、自定义 provider 命令修复或 Reasonix 命令配置结果，不创建模型 run；带 `run_id` 的 `cancel background job` / `停止后台任务` 会取消后台 worker 而不推进门禁；`continue`、`approve`、`apply` 这类没有 `run_id` 的消息会返回本地提示，不会自动推进最新运行。带 `run_id` 的“is writer using cheap model?”这类路由问题仍是只读 `profile_show`，但会同时返回该运行的 `metrics.efficiency_summary`，让客户端能按真实 provider/token/cost 证据回答。选中运行的对话线程会先展示紧凑“运行概览”，汇总阶段/状态、门禁进度、经济路由健康和最近 provider 证据，再展示详细事件流；侧栏 run inbox 也会为每个 run 展示阶段、门禁、经济路由和最近 provider 的紧凑快速信号，方便打开详情前先分拣多任务队列；没有选中运行时，composer 上方会先展示紧凑“启动上下文”，汇总本地/no-MCP 模式、就绪状态、write/fix 经济路由和安全 setup/economy 动作，再创建新的计划 run；诊断抽屉里的“就绪”页也会调用统一 doctor 检查项目初始化、配置、CLI 入口、Skill 状态和 economy 路由命令状态，展示当前 write/fix 路由，并按 `action_groups[]` 把 `actions[]` 渲染为稳定分区的安全操作按钮，例如运行 setup、安装/更新 Skill、探测 MCP、刷新 readiness、应用 economy profile 或配置 Reasonix 命令；Trace/活动页会先把选中消息、运行时间线和 provider trace 汇总为可读卡片，原始 JSON 只保留为折叠调试明细；Diff/差异页会先按文件汇总变更、增删行和 hunk 数，原始 patch 文本保留在折叠调试明细中；Log/日志页和 Artifacts/产物页会把 `failure_recovery`、状态错误、优先产物和当前产物预览汇总成失败摘要、建议下一步、错误线索和产物索引，然后再展示原始预览；Config/配置页会把解析后的配置汇总为阶段路由、provider 命令、测试 allowlist、自定义 provider 和工作流安全开关，原始配置 JSON 仍保留在折叠调试明细中；Providers/提供方页会把已配置阶段路由、实际 provider usage、事件轨迹、economy 目标、覆盖率和健康状态汇总到同一诊断视图，方便检查 write/fix 是否实际走低价模型；运行 composer 会同样用 `patchbay_context.action_groups[]` 分组 `agent_activity.conversation_state.suggestions`，把后台轮询、后台控制、诊断、门禁和新任务控件稳定分区；当 Skill `status` 是 `outdated` 时，卡片会显示 `installed_matches_source=false` 对应的缺失/变更/多余安装文件。就绪页的 MCP host 选择器会把目标 host 传入 doctor/setup，setup、doctor 和 `mcp install` 会把 `Claude Desktop`、`claude desktop`、`claude-desktop`、`Claude Code`、`Gemini CLI` 等常见写法规范化为同一个 canonical host。本地对话回复也会把安全的 `command` action 渲染为带兜底复制路径的命令行，MCP/Skill 注册命令、custom economy provider 注册命令和 Reasonix 配置回退命令不必打开诊断页也能直接使用。后台任务卡片会展示打开活动、刷新和取消动作。Overview/效率区域会展示 `tier_usage`、`efficiency_summary`、`routing_evidence`、`economy_health` 和 `agent_activity.health_cards`，区分“write/fix 简单工作消耗占比”“已配置 economy”“Reasonix 命令不可执行”“本次运行已实际观察到 economy provider 事件”以及“write/fix 漂移到了非经济 provider”。运行失败时，线程里的失败恢复卡片会读取 `failure_recovery`，展示建议动作和应优先检查的产物，但不会自动执行任何阶段动作。Web 默认跳过 MCP stdio 探测，避免打开页面时启动额外子进程，需要完整 MCP 检查时再运行 `patchbay doctor --host <host> --probe-mcp --json` 或 `patchbay mcp doctor`。启动 `patchbay web --port 8765` 后打开 `http://127.0.0.1:8765`。

Workbench 会在刷新或重新打开后恢复当前显示的是选中 run 还是新任务视图、诊断抽屉开关状态、当前诊断 tab、按 run 记住的 Trace/活动页选中消息、侧栏搜索/状态/inbox 筛选，以及按 run 隔离的新任务/运行 composer 草稿；顶部刷新按钮在选中 run 时会一起刷新该 run 的 status、context、provider trace、diff 和产物预览，而不是只刷新侧栏列表；选中 run 的轮询会在窗口隐藏时暂停空闲增量 context 刷新，回到可见时立即补一次刷新，活跃后台 job 则继续轮询直到完成；阶段推进按钮会捕获 gated/autopilot 动作失败，显示命名失败动作的可访问顶部错误提示，并恢复按钮可用状态，同时不放宽 final apply 的单独确认门禁；同时会恢复轻量、有界的本地对话 transcript，包括最近的选中 run 本地备注、压缩后的本地 Agent 回复，以及最新的新任务 Agent 回复，但不会持久化体积大的 `context`、`status`、`runs`、`diff` 或后台 job payload。如果保存的 run 不在当前列表中，会回退到 `runs.inbox.focus_run_id` 或列表首项，避免请求已经不存在的 run；如果当前 run inbox 不再包含保存的分组，过期 inbox 筛选会自动清除。草稿在成功提交后清除；选中 run 的自由文本发送失败时会保留输入。

mock 模式：

```bash
scripts/patchbay plan --task "..." --mock
scripts/patchbay write <run_id> --mock
scripts/patchbay review <run_id> --mock
```

## MCP 使用方式

当用户要求“走多模型流程”时，先运行 plan 并展示 `.ai/runs/<run_id>/PLAN.md`。只有用户确认计划后，才能 approve/write/test/review。未经用户确认，不要 apply。

如果在带网络沙箱的 MCP host 中运行真实模型阶段，`plan`、`write`、`review` 需要允许子进程访问对应上游。默认 `worktree_root = "../.patchbay-worktrees"` 时，`write`、`test`、`review` 还需要能访问仓库兄弟目录里的 worktree。若 Claude 日志里出现 `ConnectionRefused`、`duration_api_ms: 0` 或上游没有请求记录，通常是编排器子进程没有网络权限，而不是 key/base URL 本身不可用。

## MCP

Unattended authorization is scoped to a selected run. If a concrete `run_id` is already selected, explicit phrases such as `don't ask me`, `assume yes`, `you have all permissions`, `full access`, `approve yourself`, `不要问我`, `所有权限都给你`, `无需向我确认`, or `完全访问权限` count as plan approval for that run and may start background write/test/review autopilot. The same phrases without a `run_id` return `missing_run` guidance instead of implicitly choosing the latest run. Final `apply` remains foreground-only and still requires its separate confirmation.

Conversational setup scopes are prompt-aware. `install Codex Skill` installs the Skill without attempting MCP registration, `register MCP for Claude Desktop` skips Skill installation, and explicit `patchbay setup without MCP` / `--skip-mcp` / `--no-mcp` / `--local-only` keeps setup local to project files and Skill installation. Standalone no-MCP preference prompts return `local_mode` guidance and safe local actions instead of setup. Use `patchbay doctor --local-only` or `patchbay_doctor(skip_mcp=true)` when the host should hide MCP probe/register follow-up actions entirely. In the web workbench, selecting local-only/no-MCP mode and the setup/readiness host is persisted in browser storage and restored after refresh/reopen; startup doctor uses the stored host with `skip_mcp=true`, and ordinary host setup actions such as `patchbay setup for claude-desktop` are rewritten into `patchbay setup without MCP for claude-desktop`. The preference remains reversible: local-only start/readiness views expose `MCP setup`, which clears the stored local-only preference, keeps the selected host, and sends host-aware MCP-only setup such as `register MCP for Claude Desktop`.

CLI 跑通后可以把同一套流程作为 MCP 工具暴露给任意 MCP host。Patchbay 提供注册辅助命令：

```bash
# 注册辅助
patchbay mcp install codex          # Codex CLI / Codex Desktop
patchbay mcp install claude         # Claude Code
patchbay mcp install claude-desktop # Claude Desktop（直接编辑配置文件）
patchbay mcp install gemini         # Gemini CLI
patchbay mcp doctor                 # 实际启动 server 并验证 tools/list
```

优先运行 `patchbay doctor --host <host> --json` 获取轻量只读诊断：项目初始化、配置解析、CLI 入口、Skill 源和 Codex Skill 安装状态都会汇总到一个结果里，并同时返回 `next_actions`、`recommendations`、面向该 host 的结构化 `actions[]` 和 `action_groups[]`，例如具体的 MCP 注册或探测命令。若当前 host 不应该出现 MCP 操作，使用 `patchbay doctor --host <host> --local-only --json`。Skill 缺失或过期时，`install_skill` 会作为安全动作返回；默认 skills root 下它是 `local_agent`，消息为 `install Codex Skill`，并带有 `patchbay skill install codex` 命令兜底，因此桌面端可以直接安装/更新 Skill 而不触发 MCP 注册；自定义 `skill_path` 下它保持 command 形态以保留目标目录。`<host>` 可使用常见自然名称或 canonical id，例如 `Claude Desktop`、`claude desktop`、`claude-desktop`、`Claude Code`、`Gemini CLI`。需要 stdio MCP tools/list 证据时再运行 `patchbay doctor --host <host> --probe-mcp --json` 或 `patchbay mcp doctor`。MCP 注册后如果 host 会缓存工具列表，请重启或 reload 该 host；随后运行 `patchbay mcp doctor --json`，或在 host 中确认 `patchbay_agent` 已可见。

Codex、Claude Code、Gemini 会先尝试自动执行注册命令，CLI 不可用时再返回可复制命令；Claude Desktop 会直接写配置。

手动注册：

```bash
# `patchbay mcp install codex|claude|gemini` 会先尝试自动执行这些命令；
# 如果 host CLI 不可用，会在结果里返回可复制的命令。

# Codex CLI / Codex Desktop
codex mcp add patchbay -- patchbay-mcp --root /path/to/repo

# Claude Code
claude mcp add patchbay -- patchbay-mcp --root /path/to/repo

# Claude Desktop: 编辑 claude_desktop_config.json，在 mcpServers 中添加
# Gemini CLI: 使用对应的 MCP server 注册方式
```

MCP 只调用已有服务函数，不复制业务逻辑。工具名使用 `patchbay_*`（包括 `patchbay_agent`、`patchbay_setup`、`patchbay_install`、`patchbay_skill_install`、`patchbay_skill_print`、`patchbay_skill_doctor`、`patchbay_context`、`patchbay_metrics`、`patchbay_doctor`、`patchbay_cancel`、`patchbay_events`、`patchbay_runs`、`patchbay_artifact` 和 `patchbay_config_*` 配置工具），旧的 `ai_flow_*` 作为兼容别名保留。无论通过哪个 host 调用，流程和门禁保持一致。

## Codex Skill

Patchbay 同时提供 Codex Skill 分发形态：

```bash
patchbay skill install codex
patchbay skill doctor codex
patchbay skill print codex --json
```

Skill host 参数接受 `codex` 以及 `Codex Desktop`、`Codex CLI`、`Codex 桌面` 等 Codex 别名；结果仍规范化为 `codex`。

Skill 默认安装到 `$CODEX_HOME/skills` 或 `~/.codex/skills`。它负责让 Codex 在“走多模型流程”/“multi-agent workflow”等场景自动遵守 Patchbay 流程。MCP server 可提供工具调用；当用户或 host 不想使用 MCP 时，Skill 也可以按本地 CLI 模式运行同一套门禁流程。

Skill 采用渐进披露结构，避免每次触发都加载完整 Agent 契约：`SKILL.md` 只保留入口选择、门禁、本地-only、经济路由和后台运行规则；`references/install.md` 保存安装与 doctor 细节；`references/agent-contract.md` 保存结构化 `actions[]`、`action_groups[]`、`failure_recovery`、经济路由、后台轮询/控制和桌面/MCP 渲染契约。`patchbay skill print codex --json` 会输出全部文件；`patchbay skill doctor` 会把这些 reference 作为必需源文件，并在安装副本缺失、过期或多出旧文件时返回 drift 和安全 reinstall 动作。

## 故障排查

- Claude CLI 不存在：检查 `[commands].claude`，或用 `--mock` 验证流程。
- Codex CLI 不存在：检查 `[commands].codex`，或用 `--mock` 验证审查流程。
- Reasonix 只聊天不改文件：确认 `[writer].provider = "reasonix_cli"`，且 `[commands].reasonix` 指向 `reasonix.cmd`/`reasonix`。Patchbay 会自动使用 `reasonix acp`。
- Claude 输出空 result 但其实已生成计划：Patchbay 会从 `stream-json` assistant event 和 Claude transcript 中恢复计划文本；查看 `claude-planner.log` 确认恢复路径。
- patch apply 失败：检查 `writer.log` 和 `FINAL.diff`。
- test command 不在 allowlist：把确认安全的命令加入 `.ai/patchbay.toml` 的 `commands_allowlist.test`。
- Windows PowerShell 拒绝运行 `.ps1` 脚本：优先使用 `codex.cmd` 与 `reasonix.cmd`（以及 `scripts/patchbay.cmd`）等 `.cmd` 入口，避免修改系统 ExecutionPolicy。

## 安全说明

Patchbay 拒绝修改 repo 外路径、`.git/`、`.env*`、secret-like 文件、绝对路径 patch、路径穿越 patch，并要求测试命令在 allowlist 中。
默认情况下没有测试命令会记录为 `tests_status = SKIPPED`，不会解锁 apply。只有显式设置 `workflow.allow_apply_without_tests = true` 时，跳过测试才会被视为允许 apply。

## 清理 worktree

```bash
scripts/patchbay cleanup <run_id>
```

## Phase Command Notes

CLI phases can use `command_key` to reference `[commands]` or `command` for an inline command. `[phases.test].commands` overrides selected test commands, with each command still checked against `commands_allowlist.test`; `[phases.test].timeout` controls the per-command timeout. `apply` has no model executor and only applies the reviewed `FINAL.diff` after tests and review pass.

## Provider Safety Notes

Claude and Codex CLI providers request their native read-only/plan execution modes. Gemini CLI does not expose the same sandbox control, so Patchbay enforces safety for Gemini plan/review phases by comparing repository/worktree state before and after the provider runs, including failure paths.

## Custom Providers

当前运行时已支持通过 `[providers.<id>]` 和 `patchbay config provider add-cli ...` 注册 CLI provider。若要让 DeepSeek 或其他便宜模型直接承担 write/fix，可一条命令注册并激活 economy 路由：

```bash
patchbay config provider add-cli cheap_writer --roles write fix --command deepseek-writer --output-contract writer_diff --activate-economy --economy-model deepseek-chat --economy-label "DeepSeek cheap writer"
```

同一能力也可以走 Web API 或对话式 Agent：`POST /api/providers` 可传 `activate_economy`、`economy_model`、`economy_label`，为桌面端一次完成 provider 注册和 write/fix economy 路由切换；`patchbay agent message "configure DeepSeek provider to deepseek-writer" --json` 会注册 `cheap_writer` 并激活 write/fix economy 路由。如果只说 `configure DeepSeek provider`，Agent 只返回可复制命令模板，不会修改本地配置。Provider 已存在但命令路径需要修复时，可以发送 `configure economy provider command to <path>` 或直接粘贴 `patchbay config --set-key providers.cheap_writer.command --set-value <path>`，Agent 会只更新 `providers.<id>.command`，不创建 run。对于自定义 provider，readiness/profile/metrics 中的命令故障会指向实际来源，例如 `providers.cheap_writer.command`，而不是固定提示 `commands.reasonix`。

Patchbay 会为每次自定义 CLI 调用设置 `PATCHBAY_USAGE_FILE`，并合并 stdout、stderr 和该 JSON sidecar 中的 token/cost 字段；这些数据会进入 `patchbay metrics`、`run_metrics.provider_usage`、`run_metrics.tier_usage` 和 Web 效率面板，用来验证 write/fix 是否真的由低成本 provider 承担，以及 economy 层在 token、成本和耗时中的实际占比。当自定义 provider 被设为 `[profiles.economy]` 时，doctor、profile status、metrics 和 write/fix 执行前门禁都会检查 `providers.<id>.command` 是否可执行；缺失时返回 `command_not_ready`，并优先提供可复制的 `configure_economy_provider_command` 安全动作，然后再提供 `inspect_economy_provider_command` 诊断动作，同时保持运行停在原状态而不是创建半成品 worktree。详见 [custom-providers-plan.md](custom-providers-plan.md) — 文档包含已实现的 CLI 基线，以及 HTTP/ACP 模式和更细安全约束的后续路线图。
