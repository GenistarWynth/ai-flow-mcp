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
patchbay install --host codex --json   # setup 的别名

# 交互式配置（无需手动编辑 TOML）
patchbay config                      # 交互式向导
patchbay config profile apply economy # write/fix 走 Reasonix + DeepSeek，适合大量简单实现/修复
patchbay agent message "apply economy profile" --json # 对话式 Agent 本地应用同一配置
patchbay agent message "configure reasonix command" --json # 配置 commands.reasonix；可追加 `to <path>`
patchbay config --set-key models.planner --set-value claude-opus-4-7   # 单键设置
patchbay doctor                      # 统一检查 config/Skill，就绪检查默认不启动 stdio MCP
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

Writer 实现入口：

- `reasonix_cli`：调用 Reasonix ACP coding agent（`reasonix acp`），由 Reasonix 自己的文件系统工具修改独立 worktree，Patchbay 只负责审批权限并捕获最终 `git diff`。

## 跨阶段可见性

任何 MCP host 都可以查看其他 agent/阶段做了什么或正在做什么：

```bash
# CLI
scripts/patchbay doctor --json            # 统一查看安装、配置、Skill 和 MCP 后续动作
scripts/patchbay doctor --probe-mcp --json # 需要时再验证 MCP initialize/tools-list
scripts/patchbay context <run_id>          # 推荐：一次性查看 handoff 摘要、门禁、下一步、产物和时间线
scripts/patchbay events <run_id>           # 展示完整事件日志
scripts/patchbay events <run_id> --phase plan  # 按阶段筛选
scripts/patchbay events <run_id> --since 5     # 从第 5 条事件开始
scripts/patchbay status <run_id>           # status 现在包含 latest_event 和 event_count
scripts/patchbay metrics <run_id>          # 只查看 run_metrics 效率证据
```

MCP 工具 `patchbay_agent` 是对话式入口，能启动、恢复和推进运行，但仍保留计划批准和 apply 确认门禁。`patchbay_setup` / `patchbay_install` 是一键初始化入口，能创建项目文件、局部配置、Skill，并尝试注册 MCP。`patchbay_agent` 的 `readiness`/`doctor`/`configure reasonix command` 本地响应、`patchbay_doctor` 和 setup/install 结果都会返回 `actions[]`：每项包含 `id`、`label`、`kind`、`safe`、`reason`，并按类型携带 `message`、`command`、`host` 或 `tab`，让桌面/MCP 客户端可以直接渲染安全的一键后续操作。`patchbay_doctor --host claude-desktop` 这类调用会把 `host` 规范化到响应顶层，并让 `install_mcp`、`run_setup`、`refresh_readiness` 等动作继承该 host，避免客户端再从自然语言里推断目标 MCP host。`patchbay_context` 是跨 host 恢复上下文的首选只读入口，并在顶层直接返回 `routing_evidence` 和 `efficiency_summary`；`patchbay_metrics` 可单独读取阶段耗时、`run_metrics.tier_usage` 里的 economy/write-fix、supervision/plan-review、execution/test-apply 聚合消耗、`run_metrics.efficiency_summary` 里的经济路由 token/cost/time 占比摘要、尝试次数、provider 使用轨迹、事件/trace 数、成本/token 上报状态，以及 `run_metrics.routing_evidence` 里的 write/fix 经济路由配置、Reasonix 命令可执行状态与实际 provider 事件证据。`routing_evidence.economy_health` 会把经济路由归一为 `healthy`、`pending_evidence`、`command_not_ready`、`drift` 或 `not_configured`，`agent_activity.health_cards` 会把同一信号作为桌面/MCP handoff 卡片暴露给客户端，并额外给出 `economy_efficiency` 和 `economy_load` 卡片，显示效率摘要以及 write/fix 的 token、成本和耗时占比。`patchbay_metrics` 还会把 `routing_evidence.actions[]` 镜像到顶层 `actions[]`；桌面/MCP 客户端应优先渲染这些 `safe: true` 的结构化动作，例如 `local_agent` 的 `apply economy profile`、`configure reasonix command`、`command` 的 `configure_economy_provider_command` 或 `diagnostic_tab` 的 Trace 跳转，而不是解析 `economy_health.next_action` 字符串。失败运行会在 `status`、`context` 和对话式 Agent 响应里暴露 `failure_recovery`，包含失败阶段、建议动作、安全检查动作和应优先查看的产物；`patchbay_events` 和 `patchbay_status` 仍可用于聚焦查看。每条事件记录包含 `phase`、`provider`、`model`、`action`、`status`、`timestamp`、`detail`、`artifact_paths`、`duration_ms` 和 `next_action`。

## 常用命令

```bash
scripts/patchbay plan --task "..."
scripts/patchbay agent message "..."
scripts/patchbay agent message "patchbay setup" --json
scripts/patchbay agent message "patchbay setup for Claude Desktop" --json
scripts/patchbay agent message status --json
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
scripts/patchbay status <run_id>
scripts/patchbay metrics <run_id>
scripts/patchbay events <run_id>
scripts/patchbay diff <run_id>
scripts/patchbay apply <run_id>
scripts/patchbay cleanup <run_id>
```

`--background` is intended for the conversational agent path: planning and approve/continue turns return a pollable `run_id`, write `JOB.json`, and surface progress through `patchbay_status`, `patchbay_context`, and `patchbay_events`. Background `JOB.json`, `status`, `context`, and immediate agent responses include safe follow-up actions for `open_background_run`, `open_trace`, `poll_status`, `poll_context`, and `poll_events`; desktop/MCP clients should prefer `poll_context` when they need the refreshed handoff payload and `poll_events` when they only need the event stream. Destructive apply remains foreground-only and still requires explicit confirmation. Explicit local setup/routing prompts such as `patchbay setup`, `patchbay setup for Claude Desktop`, `install patchbay for Gemini CLI`, `patchbay install`, `apply economy profile`, `configure DeepSeek provider`, `configure economy provider command to <path>`, `configure reasonix command`, or `configure reasonix command to <path>` run local setup/config updates or return safe setup command templates without creating a model run. These local setup/readiness/status/profile payloads include `actions[]` entries whose `kind` is currently `local_agent`, `command`, `diagnostic_tab`, `open_run`, or `focus_composer`; clients should render only entries with `safe: true` as direct actions. `status` or `runs` without a `run_id` can return an `open_run` action for the latest run, or `focus_composer` plus readiness diagnostics when no runs exist, but should not render `continue`, `approve`, or `apply` as stateless direct actions. If the user sends `continue`, `approve`, or `apply` without a `run_id`, Patchbay returns local guidance instead of choosing a run automatically. Read-only prompts such as `metrics`, `diff`, `events`, `logs`, `artifact`, or `查看失败原因` can inspect the latest run when one exists and include an `open_latest_run` action plus `requested_view` for desktop clients.

Web workbench 使用同一套对话式 Agent 流程。`patchbay_agent` 和 `scripts/patchbay agent message "patchbay setup" --json` / `status --json` / `readiness --json` / `"metrics" --json` / `"diff" --json` / `"apply economy profile" --json` / `"configure DeepSeek provider" --json` / `"configure economy provider command to <path>" --json` / `"configure reasonix command" --json` / `"configure reasonix command to <path>" --json` 可直接返回 setup 结果、最近运行、统一 doctor 报告、最近运行效率证据、最近运行只读视图、经济路由配置结果、自定义低成本 provider 注册命令、自定义 provider 命令修复或 Reasonix 命令配置结果，不创建模型 run；`continue`、`approve`、`apply` 这类没有 `run_id` 的消息会返回本地提示，不会自动推进最新运行。带 `run_id` 的“is writer using cheap model?”这类路由问题仍是只读 `profile_show`，但会同时返回该运行的 `metrics.efficiency_summary`，让客户端能按真实 provider/token/cost 证据回答。诊断抽屉里的“就绪”页也会调用统一 doctor 检查项目初始化、配置、CLI 入口、Skill 状态和 economy 路由命令状态，展示当前 write/fix 路由，并把 `actions[]` 渲染为安全操作按钮，例如运行 setup、安装 Skill、探测 MCP、刷新 readiness、应用 economy profile 或配置 Reasonix 命令；就绪页的 MCP host 选择器会把目标 host 传入 doctor/setup，setup、doctor 和 `mcp install` 会把 `Claude Desktop`、`claude desktop`、`claude-desktop`、`Claude Code`、`Gemini CLI` 等常见写法规范化为同一个 canonical host。本地对话回复也会把安全的 `command` action 渲染为可复制命令行，MCP/Skill 注册命令、custom economy provider 注册命令和 Reasonix 配置回退命令不必打开诊断页也能直接使用。Overview/效率区域会展示 `tier_usage`、`efficiency_summary`、`routing_evidence`、`economy_health` 和 `agent_activity.health_cards`，区分“write/fix 简单工作消耗占比”“已配置 economy”“Reasonix 命令不可执行”“本次运行已实际观察到 economy provider 事件”以及“write/fix 漂移到了非经济 provider”。运行失败时，线程里的失败恢复卡片会读取 `failure_recovery`，展示建议动作和应优先检查的产物，但不会自动执行任何阶段动作。Web 默认跳过 MCP stdio 探测，避免打开页面时启动额外子进程，需要完整 MCP 检查时再运行 `patchbay doctor --host <host> --probe-mcp --json` 或 `patchbay mcp doctor`。启动 `patchbay web --port 8765` 后打开 `http://127.0.0.1:8765`。

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

CLI 跑通后可以把同一套流程作为 MCP 工具暴露给任意 MCP host。Patchbay 提供注册辅助命令：

```bash
# 注册辅助
patchbay mcp install codex          # Codex CLI / Codex Desktop
patchbay mcp install claude         # Claude Code
patchbay mcp install claude-desktop # Claude Desktop（直接编辑配置文件）
patchbay mcp install gemini         # Gemini CLI
patchbay mcp doctor                 # 实际启动 server 并验证 tools/list
```

优先运行 `patchbay doctor --host <host> --json` 获取轻量只读诊断：项目初始化、配置解析、CLI 入口、Skill 源和 Codex Skill 安装状态都会汇总到一个结果里，并同时返回 `next_actions`、`recommendations` 和面向该 host 的结构化 `actions[]`，例如具体的 MCP 注册或探测命令。`<host>` 可使用常见自然名称或 canonical id，例如 `Claude Desktop`、`claude desktop`、`claude-desktop`、`Claude Code`、`Gemini CLI`。需要 stdio MCP tools/list 证据时再运行 `patchbay doctor --host <host> --probe-mcp --json` 或 `patchbay mcp doctor`。MCP 注册后如果 host 会缓存工具列表，请重启或 reload 该 host；随后运行 `patchbay mcp doctor --json`，或在 host 中确认 `patchbay_agent` 已可见。

Codex、Claude Code、Gemini 会先尝试自动执行注册命令，CLI 不可用时再返回可复制命令；Claude Desktop 会直接写配置。

手动注册：

```bash
# `patchbay mcp install codex|claude|gemini` 会先尝试自动执行这些命令；
# 如果 host CLI 不可用，会在结果里返回可复制的命令。

# Codex CLI / Codex Desktop
codex mcp add patchbay -- python scripts/patchbay_mcp_server.py

# Claude Code
claude mcp add patchbay -- python scripts/patchbay_mcp_server.py

# Claude Desktop: 编辑 claude_desktop_config.json，在 mcpServers 中添加
# Gemini CLI: 使用对应的 MCP server 注册方式
```

MCP 只调用已有服务函数，不复制业务逻辑。工具名使用 `patchbay_*`（包括 `patchbay_agent`、`patchbay_setup`、`patchbay_install`、`patchbay_skill_install`、`patchbay_skill_print`、`patchbay_skill_doctor`、`patchbay_context`、`patchbay_metrics`、`patchbay_doctor`、`patchbay_events`、`patchbay_runs`、`patchbay_artifact` 和 `patchbay_config_*` 配置工具），旧的 `ai_flow_*` 作为兼容别名保留。无论通过哪个 host 调用，流程和门禁保持一致。

## Codex Skill

Patchbay 同时提供 Codex Skill 分发形态：

```bash
patchbay skill install codex
patchbay skill doctor codex
patchbay skill print codex --json
```

Skill 默认安装到 `$CODEX_HOME/skills` 或 `~/.codex/skills`。它负责让 Codex 在“走多模型流程”/“multi-agent workflow”等场景自动遵守 Patchbay 流程；MCP server 负责提供工具调用，因此仍需要单独注册 MCP。

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

同一能力也可以走对话式 Agent：`patchbay agent message "configure DeepSeek provider to deepseek-writer" --json` 会注册 `cheap_writer` 并激活 write/fix economy 路由；如果只说 `configure DeepSeek provider`，Agent 只返回可复制命令模板，不会修改本地配置。Provider 已存在但命令路径需要修复时，可以发送 `configure economy provider command to <path>` 或直接粘贴 `patchbay config --set-key providers.cheap_writer.command --set-value <path>`，Agent 会只更新 `providers.<id>.command`，不创建 run。对于自定义 provider，readiness/profile/metrics 中的命令故障会指向实际来源，例如 `providers.cheap_writer.command`，而不是固定提示 `commands.reasonix`。

Patchbay 会为每次自定义 CLI 调用设置 `PATCHBAY_USAGE_FILE`，并合并 stdout、stderr 和该 JSON sidecar 中的 token/cost 字段；这些数据会进入 `patchbay metrics`、`run_metrics.provider_usage`、`run_metrics.tier_usage` 和 Web 效率面板，用来验证 write/fix 是否真的由低成本 provider 承担，以及 economy 层在 token、成本和耗时中的实际占比。当自定义 provider 被设为 `[profiles.economy]` 时，doctor、profile status、metrics 和 write/fix 执行前门禁都会检查 `providers.<id>.command` 是否可执行；缺失时返回 `command_not_ready`、`inspect_economy_provider_command` 和可复制的 `configure_economy_provider_command` 安全动作，并保持运行停在原状态而不是创建半成品 worktree。详见 [custom-providers-plan.md](custom-providers-plan.md) — 文档包含已实现的 CLI 基线，以及 HTTP/ACP 模式和更细安全约束的后续路线图。
