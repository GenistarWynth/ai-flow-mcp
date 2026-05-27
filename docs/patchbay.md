# Patchbay

Patchbay 是一个本地补丁编排器：任意支持 MCP 的客户端都可以作为入口（Claude Code、Claude Desktop、Codex CLI、Codex Desktop、Gemini CLI 等），默认把规划、实现、测试、审查和应用拆成可审计阶段。默认角色绑定是 Claude 规划、Reasonix (默认 Agent) 实现、Codex 审查；每个阶段都可以通过配置换成其他工具。

## 快速安装

```bash
# npx 风格（推荐）
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay init
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay-mcp --root /path/to/repo

# 交互式配置（无需手动编辑 TOML）
patchbay config                      # 交互式向导
patchbay config set models.planner claude-opus-4-7   # 单键设置
patchbay doctor                      # 验证配置

# MCP 注册（无需手动编辑 JSON）
patchbay mcp install codex           # Codex CLI / Codex Desktop
patchbay mcp install claude          # Claude Code
patchbay mcp install claude-desktop  # Claude Desktop
patchbay mcp install gemini          # Gemini CLI
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
scripts/patchbay events <run_id>           # 展示完整事件日志
scripts/patchbay events <run_id> --phase plan  # 按阶段筛选
scripts/patchbay events <run_id> --since 5     # 从第 5 条事件开始
scripts/patchbay status <run_id>           # status 现在包含 latest_event 和 event_count
```

MCP 工具 `patchbay_events` 和 `patchbay_status` 提供相同数据。每条事件记录包含 `phase`、`provider`、`model`、`action`、`status`、`timestamp`、`detail`、`artifact_paths`、`duration_ms` 和 `next_action`。

## 常用命令

```bash
scripts/patchbay plan --task "..."
scripts/patchbay approve <run_id>
scripts/patchbay write <run_id>
scripts/patchbay test <run_id>
scripts/patchbay review <run_id>
scripts/patchbay fix <run_id>
scripts/patchbay status <run_id>
scripts/patchbay events <run_id>
scripts/patchbay diff <run_id>
scripts/patchbay apply <run_id>
scripts/patchbay cleanup <run_id>
```

mock 模式：

```bash
scripts/patchbay plan --task "..." --mock
scripts/patchbay write <run_id> --mock
scripts/patchbay review <run_id> --mock
```

## Conversational Agent UI

```bash
scripts/patchbay agent serve --host 127.0.0.1 --port 8765 --open
```

The local Agent UI is the recommended human-facing workflow. It keeps one chat
surface for the task, run timeline, status, artifacts, and final diff. It uses
the same `plan -> approve -> write -> test -> review -> fix -> apply` services
underneath, and it preserves both approval gates:

- implementation starts only after explicit plan approval;
- apply runs only after tests pass, review passes, and the user explicitly
  approves applying the diff.

For MCP hosts, prefer `patchbay_agent` as the conversational entry point. The
lower-level `patchbay_plan`, `patchbay_write`, `patchbay_review`, and related
tools remain stable expert/debug APIs. Legacy `ai_flow_*` names remain aliases
for compatibility.

## MCP 使用方式

当用户要求“走多模型流程”时，先运行 plan 并展示 `.ai/runs/<run_id>/PLAN.md`。只有用户确认计划后，才能 approve/write/test/review。未经用户确认，不要 apply。

如果在带网络沙箱的 MCP host 中运行真实模型阶段，`plan`、`write`、`review` 需要允许子进程访问对应上游。默认 `worktree_root = "../.patchbay-worktrees"` 时，`write`、`test`、`review` 还需要能访问仓库兄弟目录里的 worktree。若 Claude 日志里出现 `ConnectionRefused`、`duration_api_ms: 0` 或上游没有请求记录，通常是编排器子进程没有网络权限，而不是 key/base URL 本身不可用。

## MCP

CLI 跑通后可以把同一套流程作为 MCP 工具暴露给任意 MCP host。Patchbay 提供了自动化注册命令：

```bash
# 自动化 — 无需手动编辑 JSON/TOML
patchbay mcp install codex          # Codex CLI / Codex Desktop
patchbay mcp install claude         # Claude Code
patchbay mcp install claude-desktop # Claude Desktop（直接编辑配置文件）
patchbay mcp install gemini         # Gemini CLI
patchbay mcp doctor                 # 验证服务器可达
```

手动注册：

```bash
# Codex CLI / Codex Desktop
codex mcp add patchbay -- python scripts/patchbay_mcp_server.py

# Claude Code
claude mcp add patchbay -- python scripts/patchbay_mcp_server.py

# Claude Desktop: 编辑 claude_desktop_config.json，在 mcpServers 中添加
# Gemini CLI: 使用对应的 MCP server 注册方式
```

MCP 只调用已有服务函数，不复制业务逻辑。工具名使用 `patchbay_*`（包括 `patchbay_events`、`patchbay_runs`、`patchbay_artifact` 和 `patchbay_config_*` 配置工具），旧的 `ai_flow_*` 作为兼容别名保留。无论通过哪个 host 调用，流程和门禁保持一致。

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

## 清理 worktree

```bash
scripts/patchbay cleanup <run_id>
```

## Phase Command Notes

CLI phases can use `command_key` to reference `[commands]` or `command` for an inline command. `[phases.test].commands` overrides selected test commands, with each command still checked against `commands_allowlist.test`; `[phases.test].timeout` controls the per-command timeout. `apply` has no model executor and only applies the reviewed `FINAL.diff` after tests and review pass.

## Provider Safety Notes

Claude and Codex CLI providers request their native read-only/plan execution modes. Gemini CLI does not expose the same sandbox control, so Patchbay enforces safety for Gemini plan/review phases by comparing repository/worktree state before and after the provider runs, including failure paths.

## Custom Providers（规划中）

用户自定义 provider 配置（`[providers.<id>]`）计划在后续版本实现。详见 [custom-providers-plan.md](custom-providers-plan.md) — TOML 模式、输出解析约定、安全约束和测试范围已列出，但尚未实现。
