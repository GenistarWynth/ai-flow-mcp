# Patchbay MCP

[English](README.md)

Patchbay 是一个本地代码补丁编排器：任意支持 MCP 的客户端都可以作为交互入口，例如 Codex Desktop、Claude Desktop、Claude Code、Codex CLI、Gemini CLI，或者其他 MCP host。

默认流程是 Claude Code 只读规划，Reasonix ACP (默认 Agent writer) 负责实现，本地测试命令负责事实验证，Codex CLI 负责只读审查。但这些只是默认角色绑定，不是边界；后续可以把 plan/write/review/test 槽位接到不同工具上。

## 按阶段配置执行器

每个工作流阶段可以独立绑定 provider 和模型，写在 `.ai/patchbay.toml`：

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

[phases.test]
commands = ["python -m unittest discover -s tests -v"]
timeout = 900

[phases.fix]
# 默认跟随 write 的 provider 和 model
```

旧的 `[models]`、`[commands]` 和 `[writer].provider` 键仍然作为默认值保留。

默认的经济型路由会把大量实现/修复工作交给更便宜的 Reasonix/DeepSeek writer，而把规划和审查留给更强的模型。如果 Reasonix 命令还没配置，就绪检查会先返回 `configure_reasonix_command` 动作；运行 `patchbay agent message "配置 Reasonix 命令" --json` 可用默认 `reasonix` 可执行文件补齐配置，也可以用 `patchbay agent message "把 Reasonix 命令设为 <path>" --json` 写入完整本机路径，两者都不会创建模型 run。同一个就绪响应也会暴露 `configure_deepseek_provider`，桌面端/MCP/Skill 客户端可以直接给出自定义 DeepSeek CLI writer 模板，作为低成本写手的替代配置路径。英文 `configure reasonix command` / `configure reasonix command to <path>` 仍然可用。需要恢复这套路由时，直接运行 `patchbay config profile apply economy`。

## 功能概览

- CLI 流程：`setup`/`install`、`doctor`、`agent message`、`web`、`plan`、`approve`、`write`、`test`、`review`、`fix`、`status`、`context`、`metrics`、`trace`、`diff`、`apply`、`cleanup`。
- MCP 工具：`patchbay_agent`、`patchbay_setup`、`patchbay_install`、`patchbay_plan`、`patchbay_approve`、`patchbay_write`、`patchbay_test`、`patchbay_review`、`patchbay_fix`、`patchbay_cancel`、`patchbay_status`、`patchbay_context`、`patchbay_metrics`、`patchbay_doctor`、`patchbay_skill_install`、`patchbay_skill_print`、`patchbay_skill_doctor`、`patchbay_events`、`patchbay_trace`、`patchbay_runs`、`patchbay_artifact`、`patchbay_config_show`、`patchbay_config_phase_set`、`patchbay_config_command_set`、`patchbay_config_test_add`、`patchbay_config_profile_apply`、`patchbay_config_profile_show`、`patchbay_config_provider_add_cli`、`patchbay_diff`、`patchbay_apply`。
- 兼容旧 MCP 工具名：`ai_flow_*`。
- 默认使用隔离 git worktree，避免直接污染当前工作区。
- 每次运行都会在 `.ai/runs/<run_id>/` 下落盘计划、diff、日志和状态。
- 实现前必须经过人工确认计划。
- 应用补丁前会做路径与安全检查；默认情况下“没有测试命令”不算测试通过，除非显式设置 `workflow.allow_apply_without_tests = true`。
- reviewer 默认只读，并检查审查阶段没有修改 worktree。
- `doctor`、`setup` 和对话式 `readiness` 响应会返回顶层 `routing`、`recommendations`、由推荐项派生的 `next_actions` 和结构化 `actions[]`，桌面端/MCP host 可以直接渲染安全的一键后续操作，而不需要解析自然语言；带结构化动作的响应还会返回 `action_groups[]`，用 `action_ids` 把按钮分成 `background_polling`、`background_control`、`routing`、`setup`、`diagnostics`、`gate`、`new_task`、`commands` 等稳定分组；`help` 还会暴露本地-only setup 以及 Codex、Claude Code、Claude Desktop、Gemini CLI 的 host-specific setup/readiness 快捷动作；`patchbay doctor --host <host>` 会让 MCP 注册、setup、refresh 动作都携带具体 host。
- `patchbay runs` 默认输出人类可读的 Agent inbox；`patchbay runs --inbox` 只显示队列摘要/分组/焦点运行，`patchbay runs --focus` 会展开最高优先级 run 的详情和下一步动作。`patchbay runs --json`、`patchbay_runs` 以及无 `run_id` 的 Agent `status` / `runs` 响应仍返回结构化 `runs.inbox`：顶层包含 `groups`、`focus_run_id`、活跃/需确认计数，每个 run 也包含 `inbox`、`actions[]`、`action_groups[]`。客户端可以直接看出哪些任务正在运行、等待计划批准、可 apply、失败待诊断、可继续、仅需查看或已应用；`approve_and_run` / `apply` 等门禁动作始终是 `safe: false` 并带 `requires_confirmation`，而 `open_run`、诊断和轮询动作保持安全。
- `patchbay agent message "help" --json` 和 `patchbay_agent` 的 help 提示会返回 `capabilities[]` 摘要，并同时保留安全的 `actions[]` / `action_groups[]`，桌面端/MCP/Skill 客户端可以直接渲染 Agent 能力面板而不解析说明文本；如果传入具体 `run_id`，help 还会返回该 run 的 `gate_diagnosis.next_action`、`next_action`、status/context 和安全诊断/setup 动作，但不会推进门禁。

## 快速开始

### npx 风格（推荐）

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay doctor
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay web --port 8765
```

然后打开 `http://127.0.0.1:8765`。只有当 MCP host 要求填写原始 stdio server 命令时，才使用 `patchbay-mcp --root /path/to/repo`。

### 本地检出

```bash
python scripts/patchbay setup --host codex
python scripts/patchbay doctor
python scripts/patchbay web --port 8765
```

然后打开 `http://127.0.0.1:8765`。

Windows 也可以使用：

```bat
scripts\patchbay.cmd setup --host codex
```

### 交互式配置

```bash
patchbay setup --host codex     # 初始化项目、本地配置、Codex Skill、MCP 注册尝试和 doctor 摘要/推荐项
patchbay setup --host codex --no-mcp  # 只做本地配置 + Codex Skill，不返回 MCP 注册/探测后续动作
patchbay install --host codex   # setup 的别名
patchbay config     # 交互式向导，无需手动编辑
patchbay config profile apply economy   # 保持 write/fix 走 Reasonix + DeepSeek
patchbay agent message "apply economy profile" --json  # 通过对话式 Agent 做同样的路由调整
patchbay agent message "配置 Reasonix 命令" --json  # 配置 commands.reasonix；可用 `把 Reasonix 命令设为 <path>`
patchbay agent message "configure DeepSeek provider" --json  # 添加自定义 DeepSeek CLI provider 模板
patchbay agent message "configure DeepSeek provider to <command>" --json  # 添加模板并写入 providers.<id>.command
patchbay agent message "configure economy provider command to <path>" --json  # 修复当前 economy writer/fix provider 命令
patchbay doctor     # 统一检查 config/Skill 是否就绪；默认不启动 stdio MCP 探测
patchbay doctor --local-only     # 就绪检查不返回 MCP probe/register 后续动作
patchbay doctor --probe-mcp     # 需要时再验证 stdio MCP initialize/tools-list
patchbay config --doctor     # 验证解析后的阶段配置
patchbay config --set-key models.planner --set-value claude-opus-4-7
```

然后编辑 `.ai/patchbay.toml`，配置本机命令、模型名、writer provider 和测试命令 allowlist。

不要提交 `.ai/patchbay.toml`。这个文件用于放你的本地 provider、命令路径和环境变量名，已经被 `.gitignore` 忽略。

旧的 `scripts/ai-flow` 命令和 `.ai/ai-flow.toml` 配置仍然可用，作为兼容入口保留。

## CLI 用法

典型流程：

```bash
python scripts/patchbay setup --host codex --json
python scripts/patchbay plan --task "为 xxx 增加 yyy，并补测试"
python scripts/patchbay agent message "为 xxx 增加 yyy，并补测试" --json
python scripts/patchbay agent message "patchbay setup" --json
python scripts/patchbay agent message status --json
python scripts/patchbay agent message context --json
python scripts/patchbay agent message readiness --json
python scripts/patchbay agent message "readiness for Claude Desktop" --json
python scripts/patchbay agent message "configure reasonix command" --json
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
python scripts/patchbay apply <run_id> --confirmation apply_approved
```

耗时较长的对话式推进可以加 `--background`，调用方立即返回，然后轮询 status/context/events：

```bash
python scripts/patchbay agent message "为 xxx 增加 yyy，并补测试" --background --json
python scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
python scripts/patchbay agent message continue --run-id <run_id> --background --json
```

后台 Agent 会写入 `JOB.json` 并追加 `agent` 事件，同时保留计划批准和 apply 确认门禁。`apply` 仍然只支持前台确认，必须在测试和审查通过后显式执行。后台响应会提供安全的打开运行、打开 Trace、轮询 status/context/events 和取消当前 worker 动作；取消动作归入 `background_control`，会终止后台进程、把 `JOB.json` 标记为 canceled、释放后台锁，并且不会批准、应用或推进门禁。可用 `patchbay cancel <run_id>`、`patchbay_cancel`，或 `patchbay agent message "cancel background job" --run-id <run_id> --json` / `停止后台任务` 执行。若客户端在已有后台 Agent job 活跃时再次发送后台 `approve`/`continue`，Patchbay 会返回原 job、`already_running: true` 和同一组安全轮询/取消动作，而不会重复启动 worker。已经选中具体 `run_id` 时，`don't ask me`、`assume yes`、`you have all permissions`、`不要问我`、`所有权限都给你` 这类无人值守授权会被视为该 run 的计划批准，并可直接启动后台 write/test/review 自动推进；没有 `run_id` 时同样的话只会返回 `missing_run` 指引，不会自动选择最近 run，最终 `apply` 仍然需要单独确认。`patchbay setup`、`patchbay setup for Claude Desktop`、`install patchbay for Gemini CLI`、`install Codex Skill`、`register MCP for Claude Desktop`、`安装 Codex Skill`、`注册 MCP 到 Gemini 命令行`、`帮我配置 Patchbay`、`帮助我配置 Patchbay 到 Claude 桌面`、`help`、`Patchbay 怎么用`、`使用说明`、`status`、`runs`、`查看最近运行`、`任务列表`、`what should I do next`、`下一步是什么`、`why can't I apply`、`what is blocking apply`、`门禁状态`、`为什么不能应用`、`readiness`、`readiness for Claude Desktop`、`diagnose`、`patchbay doctor`、`检查环境`、`环境自检`、`检查 Gemini 命令行环境`、`show economy profile`、`apply economy profile`、`configure DeepSeek provider`、`configure DeepSeek provider to <command>`、`configure economy provider command to <path>`、`configure reasonix command`、`configure reasonix command to <path>`、`配置 Reasonix 命令`、`把 Reasonix 命令设为 <path>`、`cancel background job` 或 `停止后台任务` 这类本地查询和配置消息会直接返回 setup 结果、使用提示、最近运行、统一 doctor 报告、路由调整结果、门禁诊断、provider 模板、本地命令配置或后台取消结果，不会创建模型 run。带 host 的 readiness 提问会返回 `setup_host` 和 `doctor.host`，桌面端可以直接切换“就绪”页的 host，并展示具体 MCP 探测/setup 命令，不需要解析自然语言。询问下一步会返回 `action: "next_step"`、最近 run 交接、`next_action` / `run_reference.next_action`、确认要求和安全 `actions[]`；它不会直接执行 `continue`、`approve` 或 `apply`，除非已经打开具体 run 且提供了所需确认。询问 apply 为什么被阻塞会返回 `action: "gate_status"`、`gate_diagnosis`、`gate_diagnosis.next_action`、未通过的检查项和安全诊断/打开 run 动作；如果用户直接对未就绪 run 发送 `apply`，也会返回同样的 `gate_diagnosis.next_action` 和安全诊断动作，而不是索要 apply 确认。它不会批准计划、跑测试、审查或应用补丁。“让大量简单写手工作用便宜模型/DeepSeek 去干”或“降本，让简单 writer/fix 走低价模型”这类自然语言性价比路由请求也会直接应用经济路由，而不是误开新的任务 run；“优化成本仪表盘”这类产品任务仍会正常进入计划门禁。help/setup/readiness/status/profile/next_step/gate_status/background_cancel 结果里的 `actions[]` 条目包含 `id`、`label`、`kind`、`safe`、`reason`，以及 `message`、`command`、`host`、`run_id` 或 `tab`；本地运行交接还可能使用 `next_action`、`open_run` 和 `focus_composer`。`continue`、`approve`、`apply`、`diff`、`artifact` 或 `查看失败原因` 这类依赖现有 run 的消息在没有 `run_id` 时也只会给出本地提示，不会误开新 run；`diff`、`events`、`logs`、`artifact` 或 `查看失败原因` 这类视图请求会携带 `requested_view`，在已有 `run_id` 时还会返回安全的 `diagnostic_tab` 动作，方便桌面端直接打开日志、差异或产物诊断。

无人值守 selected-run 批准也接受 `full access`、`approve yourself`、`无需向我确认`、`完全访问权限`、`自己允许` 等自然表达；如果没有选中 `run_id`，这些话仍只返回本地指引，不会创建或推进运行。

`简单 writer/fix 用 DeepSeek 省钱` 或 `降本，让简单 writer/fix 走低价模型` 这类中英混合提示也会被识别为经济路由意图：它会应用 write/fix 的 economy profile，而不是创建新的任务 run。

`context`、`handoff context`、`events`、`poll context` 和 `poll events` 是只读 Agent 消息：带 `run_id` 时直接返回当前运行的 Overview/Trace 诊断动作；不带 `run_id` 且存在最近运行时返回最新运行的 handoff 视图，不会推进阶段或绕过门禁。活跃后台任务会把 `poll_context`、`poll_status`、`poll_events` 和 `cancel_background_job` 提升到 `patchbay_context.next_actions`、顶层 `action_groups[]` 和 `agent_activity.conversation_state.suggestions`，桌面端/MCP host/Skill 可以直接用这些安全建议刷新或停止后台工作，不需要解析 `JOB.json`，也不会把 `continue`、`approve` 或 `apply` 暴露成后台直达动作。

带结构化动作的 Agent、setup、doctor、profile、metrics 和后台 job 响应还会提供 `action_groups[]`：每组包含 `id`、`label`、`reason`、`action_ids` 和 `count`，用于把按钮稳定分成后台轮询、后台控制、经济路由、就绪设置、诊断、门禁、新任务或可复制命令，桌面端/MCP host/Skill 不需要再从 action id 或自然语言里猜 UI 分组。

setup 会根据提示词自动收窄范围：`install Codex Skill` 只安装 Skill、不尝试 MCP 注册；`register MCP for Claude Desktop` 会跳过 Skill 安装；显式 `patchbay setup without MCP`、`--skip-mcp`、`--no-mcp` 或 `--local-only` 只做项目文件和 Skill 的本地 setup。`please don't use MCP`、`no MCP`、`use Chrome Skill instead of MCP`、`少用这个MCP`、`不要用这个MCP` 这类单独的对话式避让表达会返回 `local_mode`，给出安全的本地 CLI / Skill / readiness 动作，而不是误开一个模型 run。同样的避让语义也适用于 `readiness` / `doctor`，因此 `readiness without MCP`、`patchbay doctor --local-only` 和 `patchbay_doctor(skip_mcp=true)` 会在顶层响应和嵌套 doctor payload 中都隐藏 MCP 探测/注册后续动作。

`不走 MCP`、`走本地模式`、`只用本地工具` 这类中文本地-only 表达也走同一条路径：Agent 只返回本地 CLI/Skill/readiness 动作，并避免 MCP probe/register 后续操作。

`what model will write/fix use`、`is writer using cheap model`、`现在写手是不是走便宜模型` 这类路由问题是只读的 `profile_show`，只报告当前写/修复模型与 provider；如果调用时带了 run id，还会附带该运行的 `metrics.efficiency_summary`，区分“已配置便宜模型”和“本次运行实际观察到的 provider/token/cost 证据”。setup、doctor/readiness 与 profile/routing 响应都会返回同一份 `routing.workload_policy`，明确 `write`/`fix` 是适合大量简单实现和修复的 economy 阶段，`plan`/`review` 是 supervision 阶段，方便桌面端、MCP host 和 Skill 直接解释性价比分工；setup/install JSON 还会把 doctor 的 `recommendations` 提升到顶层，并把可执行建议映射成 `apply economy profile`、`configure reasonix command` 或 `configure economy provider command` 这类短 `next_actions`；当自定义 economy provider 的命令未就绪时，客户端应优先渲染 `configure_economy_provider_command` 复制命令，再显示 inspect 动作，让用户直接修复 `providers.<id>.command`。就绪页可以直接渲染 `doctor.routing`，setup 回复可以直接渲染顶层 `routing`，不用等用户额外询问路由。显式 `command_key` 缺失或不一致都会被视为路由漂移，不会被当作已验证的经济路由证据。`apply economy profile`、“让大量简单写手工作用便宜模型/DeepSeek 去干”或“优化成本，让写手工作走低价模型”这类明确配置意图才会修改本地路由。

Web workbench 使用同一套对话式流程，并在诊断抽屉里提供“就绪”页。该页面调用统一 doctor 检查但默认不做 MCP stdio 探测，因此可以在桌面 UI 中看到安装与配置缺口，同时避免打开页面时额外启动子进程。就绪页的 MCP host 选择器会把目标 host 传给 doctor/setup，`Claude Desktop`、`claude desktop`、`claude-desktop` 这类常见写法会统一规范化为具体注册命令。该页面还会显示当前 write/fix 路由画像，并按 `action_groups[]` 把结构化 `actions[]` 分成稳定分区，用来执行安全的 setup、Skill、MCP 探测、刷新、经济路由和 Reasonix 命令配置后续操作。运行 composer 也会用 `patchbay_context.action_groups[]` 分组 `agent_activity.conversation_state.suggestions`，让后台轮询、后台控制、诊断和门禁动作分成独立控制区，而不是平铺按钮；后台任务卡片也会直接展示打开活动、刷新和取消控制。如果已安装的 Codex Skill 过期，就绪检查卡会直接显示 `status: outdated`、缺失/变更/多余的安装文件，以及安全的更新动作。Overview 会展示 `efficiency_summary`、`routing_evidence.economy_health` 与 `agent_activity.health_cards`，包括 `economy_efficiency` 和 `economy_load` 卡片，让桌面端直接看到经济路由是健康、待观测、`command_not_ready`、漂移，还是未配置，并看到简单 write/fix 工作的实际 token/cost/time 占比。

当 doctor 返回结构化 `configure_deepseek_provider` 动作时，就绪页可以渲染受保护的 economy provider 表单，用于创建自定义 DeepSeek CLI writer/fix provider 并激活经济路由。健康就绪状态下不应展示这个可变更配置的表单，避免用户没有 setup 缺口时意外修改 provider 配置。

启动 `patchbay web --port 8765` 后，打开 `http://127.0.0.1:8765`。

查看状态和 diff：

```bash
python scripts/patchbay status <run_id>
python scripts/patchbay metrics <run_id>
python scripts/patchbay diff <run_id>
```

如果 review 要求修改，最多按配置执行修复循环：

```bash
python scripts/patchbay fix <run_id>
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id>
```

清理隔离 worktree：

```bash
python scripts/patchbay cleanup <run_id>
```

## Mock 模式

没有模型凭据时，可以先用 mock 模式验证完整编排流程：

```bash
python scripts/patchbay plan --task "mock smoke" --mock
python scripts/patchbay approve <run_id>
python scripts/patchbay write <run_id> --mock
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id> --mock
python scripts/patchbay apply <run_id> --confirmation apply_approved
```

Mock 模式适合检查 CLI、状态流转、worktree、补丁应用和 MCP 封装是否正常。

## MCP 安装

在仓库根目录运行：

```bash
# 自动化 — 无需手动编辑 JSON/TOML
patchbay mcp install codex          # Codex CLI / Codex Desktop
patchbay mcp install claude         # Claude Code
patchbay mcp install claude-desktop # Claude Desktop（直接编辑配置文件）
patchbay mcp install gemini         # Gemini CLI

# 或手动注册
codex mcp add patchbay -- patchbay-mcp --root /path/to/repo
```

Claude Desktop、Claude Code、Gemini CLI 或其他 MCP host 使用各自等价的 MCP server 注册方式即可；如果 `/path/to/repo` 含空格，请加引号。运行 `patchbay doctor --host <host>` 做轻量就绪检查并生成该 host 的结构化后续动作；如果当前 host 不应该出现 MCP 动作，用 `patchbay doctor --host <host> --local-only --json`。只有需要 stdio server 和 tools/list 证据时，才运行 `patchbay doctor --host <host> --probe-mcp --json` 或 `patchbay mcp doctor`。setup、doctor 和 `mcp install` 会接受常见 host 别名，例如 `Claude Desktop`、`Claude 桌面`、`Claude Code`、`Claude 代码`、`Gemini CLI`、`Gemini 命令行`、`Codex Desktop`、`Codex 桌面`。

`patchbay doctor` 是只读检查，会汇总项目初始化、阶段配置、CLI shim/已安装命令、内置 Skill 源、Codex Skill 是否已安装且与内置源一致、MCP 后续动作，以及 economy 路由的 Reasonix 命令可执行状态；默认不启动 stdio MCP server，避免常规就绪检查额外拉起子进程。需要完全隐藏 MCP 探测/注册动作时使用 `patchbay doctor --local-only`。它会同时返回文字版 `next_actions`/`recommendations`、结构化 `actions[]` 与 `action_groups[]`；当已安装 Skill 与内置源不一致时，会返回 `Update Codex Skill` 安全动作。`patchbay doctor --probe-mcp` 和 `patchbay mcp doctor` 会真正启动 stdio MCP server，发送 `initialize` 和 `tools/list`，并检查 `patchbay_agent`、`patchbay_plan`、`patchbay_context`、`patchbay_metrics`、`patchbay_doctor`、`patchbay_install`、`patchbay_skill_install`、`patchbay_skill_doctor` 等核心工具是否存在。Codex、Claude Code、Gemini 的 install 命令会先尝试自动注册，若 host CLI 不可用则回退为可复制的注册命令；Claude Desktop 会直接写入 JSON 配置。

MCP 注册后，如果目标 host 会缓存工具列表，请重启或 reload 对应 host。可以运行 `patchbay mcp doctor --json` 验证 stdio server，也可以在 host 中确认 `patchbay_agent` 已可见。`patchbay skill doctor` / `patchbay_skill_doctor` 在 Skill 未安装时也会返回安全的结构化 `install_skill` 与 `refresh_skill_doctor` 动作以及 `action_groups[]`；使用默认 skills root 时，`install_skill` 是 `local_agent` 动作，消息为 `install Codex Skill`，并保留 `patchbay skill install codex` 命令兜底，因此桌面端和 MCP host 可以直接安装 Skill 而不触发 MCP 注册。若传入自定义 `--path`，该动作保持 command 形态，以保留目标安装路径。

安装后可用的 MCP 工具包括：

- `patchbay_agent`
- `patchbay_setup`
- `patchbay_install`
- `patchbay_plan`
- `patchbay_approve`
- `patchbay_write`
- `patchbay_test`
- `patchbay_review`
- `patchbay_fix`
- `patchbay_status`
- `patchbay_context`
- `patchbay_metrics`
- `patchbay_doctor`
- `patchbay_events`
- `patchbay_trace`
- `patchbay_runs`
- `patchbay_artifact`
- `patchbay_config_show`
- `patchbay_config_phase_set`
- `patchbay_config_command_set`
- `patchbay_config_test_add`
- `patchbay_config_profile_apply`
- `patchbay_config_profile_show`
- `patchbay_config_provider_add_cli`
- `patchbay_diff`
- `patchbay_apply`

## Codex Skill 安装

Patchbay 同时提供 Codex Skill。Skill 负责让 Codex 在合适场景遵守 Patchbay 的门禁流程；MCP server 负责提供实际工具。

```bash
patchbay skill install codex
patchbay skill doctor codex
patchbay skill print codex --json
```

Skill host 参数也接受 `Codex Desktop`、`Codex CLI`、`Codex 桌面` 等 Codex 别名；返回结果仍使用 canonical `codex`。

`patchbay skill doctor` 会同时检查内置 Skill 源和已安装副本是否一致。如果已安装 Skill 过旧、缺文件或残留多余旧文件，会返回 `status: "outdated"`、`installed_matches_source: false`、`missing_installed_files`、`changed_installed_files`、`extra_installed_files`，并给出安全的重新安装动作。

Skill 本体刻意保持精简，降低触发后的上下文成本。`SKILL.md` 只保留触发、入口选择、门禁、本地-only、经济路由和后台运行规则；安装细节放在 `references/install.md`，结构化 Agent/桌面/MCP 响应契约放在 `references/agent-contract.md`。`patchbay skill print codex --json` 会返回全部 bundled 文件；`patchbay skill doctor` 会把这两个 reference 都当成必需源文件，并在已安装副本缺失或过期时报 drift。

默认安装位置是 `$CODEX_HOME/skills` 或 `~/.codex/skills`。触发语包括“走多模型流程”、“multi-agent workflow”、Patchbay setup/install、Codex Skill 安装，以及不走 MCP / 本地-only 的 Patchbay 工作；如果 host 要使用工具调用，MCP 工具仍需要单独注册。

MCP 只是调用 `scripts.ai_flow.service` 中的同一套业务逻辑，不复制另一份流程。

## 配置

公开示例配置在 `.ai/patchbay.example.toml`。

常见字段：

```toml
[models]
planner = "claude-opus-4-7"
writer = "deepseek-v4-pro"
reviewer = "gpt-5.5"

[commands]
claude = "claude"
codex = "codex"
reasonix = ""

[writer]
provider = "reasonix_cli" # 默认 Agent writer
```

Reasonix agent 是默认 writer。确保 `[commands].reasonix` 指向你的 Reasonix 可执行文件：

```toml
[commands]
reasonix = "reasonix"
```

Windows 上如果 `reasonix` 是 `.cmd` 入口，可以写成：

```toml
[commands]
reasonix = "reasonix.cmd"
```

## 流程门禁

推荐的人机协作顺序：

1. 运行 `plan`。
2. 阅读 `.ai/runs/<run_id>/PLAN.md`。
3. 明确确认后运行 `approve`。
4. 运行 `write`、`test`、`review`。
5. 只有测试通过且 review PASS 后，才运行 `apply`。

这也是 MCP 模式下建议遵守的流程：不要跳过计划确认，也不要在 review 失败时直接 apply。

## 安全边界

Patchbay 默认做了这些防护：

- `.ai/patchbay.toml`、`.ai/runs/`、`.ai/logs/`、`.ai/worktrees/` 和 `.patchbay-worktrees/` 被忽略。
- 拒绝修改 `.git`、`.env*`、secret-like 文件、绝对路径和路径穿越 patch。
- Reasonix ACP 的 execute 权限会被拒绝，未知权限请求按保守策略处理。
- reviewer 只读运行，并检查 review 过程中没有修改 worktree。
- 日志会遮蔽环境变量和 adapter 已知的 API key。
- 测试命令必须在 `.ai/patchbay.toml` 的 `commands_allowlist.test` 中。

## 排障

- `claude` 找不到：检查 `[commands].claude`，或先用 `--mock` 验证流程。
- `codex` 找不到：检查 `[commands].codex`，或先用 `--mock` 验证 review 流程。
- Reasonix 只能聊天、不改文件：确认 `[writer].provider = "reasonix_cli"`，并为 `[commands].reasonix` 指向 `reasonix` 或 `reasonix.cmd`。
- 上游没有收到请求：在带沙箱的环境中，真实模型阶段可能需要允许子进程访问网络。
- patch apply 失败：查看 `.ai/runs/<run_id>/FINAL.diff` 和对应日志。
- test command 不在 allowlist：把确认安全的测试命令加入 `.ai/patchbay.toml` 的 `commands_allowlist.test`。
- Windows 拒绝执行 `.ps1`：优先使用 `.cmd` 入口，例如 `scripts\patchbay.cmd`、`codex.cmd`、`reasonix.cmd`。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 开源说明

这个仓库不包含真实 API key、本地私有配置、运行日志或历史 `.ai/runs`。公开配置文件只保留环境变量名和示例值。

## 自定义 Provider 支持

当前运行时已支持通过 `[providers.<id>]` 和 `patchbay config provider add-cli ...` 注册 CLI provider。Web API 的 `POST /api/providers` 也支持同一能力，可传 `activate_economy`、`economy_model`、`economy_label`，让桌面端一次添加低成本 provider 并把 write/fix 切到 economy 路由。对话式 Agent 也能用 `configure DeepSeek provider` 添加 DeepSeek CLI provider 模板，或用 `configure DeepSeek provider to <command>` 一步写入本机命令。若当前 economy writer/fix provider 缺少命令，doctor/readiness/setup 会返回 `configure_economy_provider_command` 动作，并可用 `configure economy provider command to <path>` 直接修复 `providers.<id>.command`。详见 [docs/custom-providers-plan.md](docs/custom-providers-plan.md) — 文档包含已实现的 CLI 基线，以及 HTTP/ACP 模式和更细安全约束的后续路线图。

桌面端和 Web 客户端应只在结构化 `configure_deepseek_provider` 就绪动作存在时展示 economy provider 配置入口。这样缺配置时能引导用户接入低成本 writer，环境健康时则不会暴露意外写配置的按钮。

## License

MIT

## Phase Command Notes

CLI phases can use `command_key` to reference `[commands]` or `command` for an inline command. `[phases.test].commands` overrides selected test commands, with each command still checked against `commands_allowlist.test`; `[phases.test].timeout` controls the per-command timeout. `apply` has no model executor and only applies the reviewed `FINAL.diff` after tests and review pass.
