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

默认的经济型路由会把大量实现/修复工作交给更便宜的 Reasonix/DeepSeek writer，而把规划和审查留给更强的模型。如果 Reasonix 命令还没配置，就绪检查会先返回 `configure_reasonix_command` 动作；运行 `patchbay agent message "配置 Reasonix 命令" --json` 可用默认 `reasonix` 可执行文件补齐配置，也可以用 `patchbay agent message "把 Reasonix 命令设为 <path>" --json` 写入完整本机路径，两者都不会创建模型 run。英文 `configure reasonix command` / `configure reasonix command to <path>` 仍然可用。需要恢复这套路由时，直接运行 `patchbay config profile apply economy`。

## 功能概览

- CLI 流程：`setup`/`install`、`doctor`、`agent message`、`web`、`plan`、`approve`、`write`、`test`、`review`、`fix`、`status`、`context`、`metrics`、`trace`、`diff`、`apply`、`cleanup`。
- MCP 工具：`patchbay_agent`、`patchbay_setup`、`patchbay_install`、`patchbay_plan`、`patchbay_approve`、`patchbay_write`、`patchbay_test`、`patchbay_review`、`patchbay_fix`、`patchbay_status`、`patchbay_context`、`patchbay_metrics`、`patchbay_doctor`、`patchbay_skill_install`、`patchbay_skill_print`、`patchbay_skill_doctor`、`patchbay_events`、`patchbay_trace`、`patchbay_runs`、`patchbay_artifact`、`patchbay_config_show`、`patchbay_config_phase_set`、`patchbay_config_command_set`、`patchbay_config_test_add`、`patchbay_config_profile_apply`、`patchbay_config_profile_show`、`patchbay_config_provider_add_cli`、`patchbay_diff`、`patchbay_apply`。
- 兼容旧 MCP 工具名：`ai_flow_*`。
- 默认使用隔离 git worktree，避免直接污染当前工作区。
- 每次运行都会在 `.ai/runs/<run_id>/` 下落盘计划、diff、日志和状态。
- 实现前必须经过人工确认计划。
- 应用补丁前会做路径与安全检查；默认情况下“没有测试命令”不算测试通过，除非显式设置 `workflow.allow_apply_without_tests = true`。
- reviewer 默认只读，并检查审查阶段没有修改 worktree。
- `doctor`、`setup` 和对话式 `readiness` 响应会返回结构化 `actions[]`，桌面端/MCP host 可以直接渲染安全的一键后续操作，而不需要解析自然语言；`help` 还会暴露本地-only setup 以及 Codex、Claude Code、Claude Desktop、Gemini CLI 的 host-specific setup/readiness 快捷动作；`patchbay doctor --host <host>` 会让 MCP 注册、setup、refresh 动作都携带具体 host。

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
patchbay setup --host codex     # 初始化项目、本地配置、Codex Skill、MCP 注册尝试和 doctor 摘要
patchbay setup --host codex --no-mcp  # 只做本地配置 + Codex Skill，不返回 MCP 注册/探测后续动作
patchbay install --host codex   # setup 的别名
patchbay config     # 交互式向导，无需手动编辑
patchbay config profile apply economy   # 保持 write/fix 走 Reasonix + DeepSeek
patchbay agent message "apply economy profile" --json  # 通过对话式 Agent 做同样的路由调整
patchbay agent message "配置 Reasonix 命令" --json  # 配置 commands.reasonix；可用 `把 Reasonix 命令设为 <path>`
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
python scripts/patchbay web --port 8765
python scripts/patchbay approve <run_id>
python scripts/patchbay write <run_id>
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id>
python scripts/patchbay apply <run_id>
```

耗时较长的对话式推进可以加 `--background`，调用方立即返回，然后轮询 status/context/events：

```bash
python scripts/patchbay agent message "为 xxx 增加 yyy，并补测试" --background --json
python scripts/patchbay agent message approve --run-id <run_id> --confirmation plan_approved --background --json
python scripts/patchbay agent message continue --run-id <run_id> --background --json
```

后台 Agent 会写入 `JOB.json` 并追加 `agent` 事件，同时保留计划批准和 apply 确认门禁。`apply` 仍然只支持前台确认，必须在测试和审查通过后显式执行。若客户端在已有后台 Agent job 活跃时再次发送后台 `approve`/`continue`，Patchbay 会返回原 job、`already_running: true` 和同一组安全轮询动作，而不会重复启动 worker。`patchbay setup`、`patchbay setup for Claude Desktop`、`install patchbay for Gemini CLI`、`install Codex Skill`、`register MCP for Claude Desktop`、`安装 Codex Skill`、`注册 MCP 到 Gemini 命令行`、`帮我配置 Patchbay`、`帮助我配置 Patchbay 到 Claude 桌面`、`help`、`Patchbay 怎么用`、`使用说明`、`status`、`runs`、`查看最近运行`、`任务列表`、`what should I do next`、`下一步是什么`、`why can't I apply`、`what is blocking apply`、`门禁状态`、`为什么不能应用`、`readiness`、`readiness for Claude Desktop`、`diagnose`、`patchbay doctor`、`检查环境`、`环境自检`、`检查 Gemini 命令行环境`、`show economy profile`、`apply economy profile`、`configure reasonix command`、`configure reasonix command to <path>`、`配置 Reasonix 命令` 或 `把 Reasonix 命令设为 <path>` 这类本地查询和配置消息会直接返回 setup 结果、使用提示、最近运行、统一 doctor 报告、路由调整结果、门禁诊断或本地命令配置，不会创建模型 run。带 host 的 readiness 提问会返回 `setup_host` 和 `doctor.host`，桌面端可以直接切换“就绪”页的 host，并展示具体 MCP 探测/setup 命令，不需要解析自然语言。询问下一步会返回 `action: "next_step"`、最近 run 交接、确认要求和安全 `actions[]`；它不会直接执行 `continue`、`approve` 或 `apply`，除非已经打开具体 run 且提供了所需确认。询问 apply 为什么被阻塞会返回 `action: "gate_status"`、`gate_diagnosis`、`gate_diagnosis.next_action`、未通过的检查项和安全诊断/打开 run 动作；如果用户直接对未就绪 run 发送 `apply`，也会返回同样的 `gate_diagnosis.next_action` 和安全诊断动作，而不是索要 apply 确认。它不会批准计划、跑测试、审查或应用补丁。“让大量简单写手工作用便宜模型/DeepSeek 去干”这类自然语言性价比路由请求也会直接应用经济路由，而不是误开新的任务 run。help/setup/readiness/status/profile/next_step/gate_status 结果里的 `actions[]` 条目包含 `id`、`label`、`kind`、`safe`、`reason`，以及 `message`、`command`、`host`、`run_id` 或 `tab`；本地运行交接还可能使用 `open_run` 和 `focus_composer`。`continue`、`approve`、`apply`、`diff`、`artifact` 或 `查看失败原因` 这类依赖现有 run 的消息在没有 `run_id` 时也只会给出本地提示，不会误开新 run；`diff`、`events`、`logs`、`artifact` 或 `查看失败原因` 这类视图请求会携带 `requested_view`，在已有 `run_id` 时还会返回安全的 `diagnostic_tab` 动作，方便桌面端直接打开日志、差异或产物诊断。

`context`、`handoff context`、`events`、`poll context` 和 `poll events` 是只读 Agent 消息：带 `run_id` 时直接返回当前运行的 Overview/Trace 诊断动作；不带 `run_id` 且存在最近运行时返回最新运行的 handoff 视图，不会推进阶段或绕过门禁。

setup 会根据提示词自动收窄范围：`install Codex Skill` 只安装 Skill、不尝试 MCP 注册；`register MCP for Claude Desktop` 会跳过 Skill 安装；`patchbay setup without MCP`、`--skip-mcp`、`--no-mcp` 或 `--local-only` 只做项目文件和 Skill 的本地 setup。`please don't use MCP`、`no MCP`、`不要用这个MCP` 这类对话式避让表达也会按本地-only setup 处理，而不是误开一个模型 run。同样的避让语义也适用于 `readiness` / `doctor`，因此 `readiness without MCP`、`patchbay doctor --local-only` 和 `patchbay_doctor(skip_mcp=true)` 会在顶层响应和嵌套 doctor payload 中都隐藏 MCP 探测/注册后续动作。

`what model will write/fix use`、`is writer using cheap model`、`现在写手是不是走便宜模型` 这类路由问题是只读的 `profile_show`，只报告当前写/修复模型与 provider；如果调用时带了 run id，还会附带该运行的 `metrics.efficiency_summary`，区分“已配置便宜模型”和“本次运行实际观察到的 provider/token/cost 证据”。显式 `command_key` 缺失或不一致都会被视为路由漂移，不会被当作已验证的经济路由证据。`apply economy profile` 或“让大量简单写手工作用便宜模型/DeepSeek 去干”这类明确配置意图才会修改本地路由。

Web workbench 使用同一套对话式流程，并在诊断抽屉里提供“就绪”页。该页面调用统一 doctor 检查但默认不做 MCP stdio 探测，因此可以在桌面 UI 中看到安装与配置缺口，同时避免打开页面时额外启动子进程。就绪页的 MCP host 选择器会把目标 host 传给 doctor/setup，`Claude Desktop`、`claude desktop`、`claude-desktop` 这类常见写法会统一规范化为具体注册命令。该页面还会显示当前 write/fix 路由画像，并渲染结构化 `actions[]` 来执行安全的 setup、Skill、MCP 探测、刷新、经济路由和 Reasonix 命令配置后续操作。Overview 会展示 `efficiency_summary`、`routing_evidence.economy_health` 与 `agent_activity.health_cards`，包括 `economy_efficiency` 和 `economy_load` 卡片，让桌面端直接看到经济路由是健康、待观测、`command_not_ready`、漂移，还是未配置，并看到简单 write/fix 工作的实际 token/cost/time 占比。

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
python scripts/patchbay apply <run_id>
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
codex mcp add patchbay -- python scripts/patchbay_mcp_server.py
```

Claude Desktop、Claude Code、Gemini CLI 或其他 MCP host 使用各自等价的 MCP server 注册方式即可。运行 `patchbay doctor --host <host>` 做轻量就绪检查并生成该 host 的结构化后续动作；如果当前 host 不应该出现 MCP 动作，用 `patchbay doctor --host <host> --local-only --json`。只有需要 stdio server 和 tools/list 证据时，才运行 `patchbay doctor --host <host> --probe-mcp --json` 或 `patchbay mcp doctor`。setup、doctor 和 `mcp install` 会接受常见 host 别名，例如 `Claude Desktop`、`Claude 桌面`、`Claude Code`、`Claude 代码`、`Gemini CLI`、`Gemini 命令行`、`Codex Desktop`、`Codex 桌面`。

`patchbay doctor` 是只读检查，会汇总项目初始化、阶段配置、CLI shim/已安装命令、内置 Skill 源、Codex Skill 安装状态、MCP 后续动作，以及 economy 路由的 Reasonix 命令可执行状态；默认不启动 stdio MCP server，避免常规就绪检查额外拉起子进程。需要完全隐藏 MCP 探测/注册动作时使用 `patchbay doctor --local-only`。它会同时返回文字版 `next_actions`/`recommendations` 与结构化 `actions[]`。`patchbay doctor --probe-mcp` 和 `patchbay mcp doctor` 会真正启动 stdio MCP server，发送 `initialize` 和 `tools/list`，并检查 `patchbay_agent`、`patchbay_plan`、`patchbay_context`、`patchbay_metrics`、`patchbay_doctor`、`patchbay_install`、`patchbay_skill_install`、`patchbay_skill_doctor` 等核心工具是否存在。Codex、Claude Code、Gemini 的 install 命令会先尝试自动注册，若 host CLI 不可用则回退为可复制的注册命令；Claude Desktop 会直接写入 JSON 配置。

MCP 注册后，如果目标 host 会缓存工具列表，请重启或 reload 对应 host。可以运行 `patchbay mcp doctor --json` 验证 stdio server，也可以在 host 中确认 `patchbay_agent` 已可见。`patchbay skill doctor` / `patchbay_skill_doctor` 在 Skill 未安装时也会返回安全的结构化 `install_skill` 与 `refresh_skill_doctor` 动作；使用默认 skills root 时，`install_skill` 是 `local_agent` 动作，消息为 `install Codex Skill`，并保留 `patchbay skill install codex` 命令兜底，因此桌面端和 MCP host 可以直接安装 Skill 而不触发 MCP 注册。若传入自定义 `--path`，该动作保持 command 形态，以保留目标安装路径。

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

默认安装位置是 `$CODEX_HOME/skills` 或 `~/.codex/skills`。触发语包括“走多模型流程”和“multi-agent workflow”；MCP 工具仍需要单独注册。

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

当前运行时已支持通过 `[providers.<id>]` 和 `patchbay config provider add-cli ...` 注册 CLI provider。详见 [docs/custom-providers-plan.md](docs/custom-providers-plan.md) — 文档包含已实现的 CLI 基线，以及 HTTP/ACP 模式和更细安全约束的后续路线图。

## License

MIT

## Phase Command Notes

CLI phases can use `command_key` to reference `[commands]` or `command` for an inline command. `[phases.test].commands` overrides selected test commands, with each command still checked against `commands_allowlist.test`; `[phases.test].timeout` controls the per-command timeout. `apply` has no model executor and only applies the reviewed `FINAL.diff` after tests and review pass.
