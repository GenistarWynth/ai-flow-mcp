# Patchbay

Patchbay 是一个本地补丁编排器：任意支持 MCP 的客户端都可以作为入口（Claude Code、Claude Desktop、Codex CLI、Codex Desktop、Gemini CLI 等），默认把规划、实现、测试、审查和应用拆成可审计阶段。默认角色绑定是 Claude 规划、Reasonix (默认 Agent) 实现、Codex 审查；每个阶段都可以通过配置换成其他工具。

## 快速安装

```bash
# npx 风格（推荐）
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay-mcp --root /path/to/repo

# 一条命令初始化本地项目、配置、Skill，并尝试注册 MCP
patchbay setup --host codex --json
patchbay install --host codex --json   # setup 的别名

# 交互式配置（无需手动编辑 TOML）
patchbay config                      # 交互式向导
patchbay config --set-key models.planner --set-value claude-opus-4-7   # 单键设置
patchbay doctor                      # 统一检查 config/MCP/Skill 就绪状态
patchbay config --doctor             # 验证配置

# MCP 注册（可自动执行；失败时返回可复制命令）
patchbay mcp install codex           # Codex CLI / Codex Desktop
patchbay mcp install claude          # Claude Code
patchbay mcp install claude-desktop  # Claude Desktop
patchbay mcp install gemini          # Gemini CLI
patchbay mcp doctor                  # 只检查 stdio server 和核心工具

# Codex Skill
patchbay skill install codex

# 本地对话式 workbench
patchbay web --port 8765
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

Writer 实现入口：

- `reasonix_cli`：调用 Reasonix ACP coding agent（`reasonix acp`），由 Reasonix 自己的文件系统工具修改独立 worktree，Patchbay 只负责审批权限并捕获最终 `git diff`。

## 跨阶段可见性

任何 MCP host 都可以查看其他 agent/阶段做了什么或正在做什么：

```bash
# CLI
scripts/patchbay doctor --json            # 统一查看安装、配置、MCP、Skill 是否就绪
scripts/patchbay context <run_id>          # 推荐：一次性查看 handoff 摘要、门禁、下一步、产物和时间线
scripts/patchbay events <run_id>           # 展示完整事件日志
scripts/patchbay events <run_id> --phase plan  # 按阶段筛选
scripts/patchbay events <run_id> --since 5     # 从第 5 条事件开始
scripts/patchbay status <run_id>           # status 现在包含 latest_event 和 event_count
scripts/patchbay metrics <run_id>          # 只查看 run_metrics 效率证据
```

MCP 工具 `patchbay_agent` 是对话式入口，能启动、恢复和推进运行，但仍保留计划批准和 apply 确认门禁。`patchbay_context` 是跨 host 恢复上下文的首选只读入口；`patchbay_metrics` 可单独读取阶段耗时、尝试次数、provider 使用轨迹、事件/trace 数和成本/token 上报状态；`patchbay_events` 和 `patchbay_status` 仍可用于聚焦查看。每条事件记录包含 `phase`、`provider`、`model`、`action`、`status`、`timestamp`、`detail`、`artifact_paths`、`duration_ms` 和 `next_action`。

## 常用命令

```bash
scripts/patchbay plan --task "..."
scripts/patchbay agent message "..."
scripts/patchbay agent message "patchbay setup" --json
scripts/patchbay agent message status --json
scripts/patchbay agent message readiness --json
scripts/patchbay agent message "..." --background --json
scripts/patchbay agent message continue --run-id <run_id> --background --json
scripts/patchbay web --port 8765
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

`--background` is intended for the conversational agent path: planning and approve/continue turns return a pollable `run_id`, write `JOB.json`, and surface progress through `patchbay_status`, `patchbay_context`, and `patchbay_events`. Destructive apply remains foreground-only and still requires explicit confirmation. Explicit local setup prompts such as `patchbay setup` or `install patchbay` run the one-command setup flow without creating a model run. If the user sends `continue`, `approve`, `apply`, `diff`, or `artifact` without a `run_id`, Patchbay returns local guidance instead of starting a new run.

Web workbench 使用同一套对话式 Agent 流程。`patchbay_agent` 和 `scripts/patchbay agent message "patchbay setup" --json` / `status --json` / `readiness --json` 可直接返回 setup 结果、最近运行或统一 doctor 报告，不创建模型 run；`continue`、`approve`、`apply`、`diff`、`artifact` 这类没有 `run_id` 的消息会返回本地提示。诊断抽屉里的“就绪”页也会调用统一 doctor 检查项目初始化、配置、CLI 入口和 Skill 状态。Web 默认跳过 MCP stdio 探测，避免打开页面时启动额外子进程，需要完整 MCP 检查时再运行 `patchbay doctor --json` 或 `patchbay mcp doctor`。

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

优先运行 `patchbay doctor --json` 获取完整只读诊断：项目初始化、配置解析、CLI 入口、MCP tools/list、Skill 源和 Codex Skill 安装状态都会汇总到一个结果里。需要聚焦 MCP 时再运行 `patchbay mcp doctor`。

Codex、Claude Code、Gemini 当前会打印注册命令；Claude Desktop 会直接写配置。

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

MCP 只调用已有服务函数，不复制业务逻辑。工具名使用 `patchbay_*`（包括 `patchbay_agent`、`patchbay_context`、`patchbay_metrics`、`patchbay_doctor`、`patchbay_events`、`patchbay_runs`、`patchbay_artifact` 和 `patchbay_config_*` 配置工具），旧的 `ai_flow_*` 作为兼容别名保留。无论通过哪个 host 调用，流程和门禁保持一致。

## Codex Skill

Patchbay 同时提供 Codex Skill 分发形态：

```bash
patchbay skill install codex
patchbay skill print codex --json
```

Skill 负责让 Codex 在“走多模型流程”/“multi-agent workflow”等场景自动遵守 Patchbay 流程；MCP server 负责提供工具调用。

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

当前运行时已支持通过 `[providers.<id>]` 和 `patchbay config provider add-cli ...` 注册 CLI provider。详见 [custom-providers-plan.md](custom-providers-plan.md) — 文档包含已实现的 CLI 基线，以及 HTTP/ACP 模式和更细安全约束的后续路线图。
