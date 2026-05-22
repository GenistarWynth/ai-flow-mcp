# Patchbay

Patchbay 是一个本地补丁编排器：任意支持 MCP 的客户端都可以作为入口（Claude Code、Claude Desktop、Codex CLI、Codex Desktop、Gemini CLI 等），默认把规划、实现、测试、审查和应用拆成可审计阶段。默认角色绑定是 Claude 规划、Reasonix (默认 Agent) 实现、Codex 审查，DeepSeek API 作为显式 fallback；每个阶段都可以通过配置换成其他工具。

## 环境准备

- 确保所需 CLI 已登录并可调用（按你要用的 provider 准备）：
  - Planner：`claude`（Claude Code）、`codex`（Codex CLI）或 `gemini`（Gemini CLI）
  - Writer：Reasonix CLI（`reasonix` / `reasonix.cmd`，默认 Agent）；DeepSeek API 作为显式 API fallback
  - Reviewer：`codex`（Codex CLI）、`claude`（Claude Code）或 `gemini`（Gemini CLI）
- 使用 DeepSeek API 时，设置 `DEEPSEEK_API_KEY`。
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
provider = "reasonix_cli"    # reasonix_cli | deepseek_api | mock
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

Writer 有两种实现入口：

- `reasonix_cli`：调用 Reasonix ACP coding agent（`reasonix acp`），由 Reasonix 自己的文件系统工具修改独立 worktree，Patchbay 只负责审批权限并捕获最终 `git diff`。
- `deepseek_api`：直接调用 OpenAI-compatible Chat Completions API，要求模型按 sentinel 返回 unified diff；这是 API fallback，不等同于 Agent。

## 常用命令

```bash
scripts/patchbay plan --task "..."
scripts/patchbay approve <run_id>
scripts/patchbay write <run_id>
scripts/patchbay test <run_id>
scripts/patchbay review <run_id>
scripts/patchbay fix <run_id>
scripts/patchbay status <run_id>
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

## MCP 使用方式

当用户要求“走多模型流程”时，先运行 plan 并展示 `.ai/runs/<run_id>/PLAN.md`。只有用户确认计划后，才能 approve/write/test/review。未经用户确认，不要 apply。

如果在带网络沙箱的 MCP host 中运行真实模型阶段，`plan`、`write`、`review` 需要允许子进程访问对应上游。默认 `worktree_root = "../.patchbay-worktrees"` 时，`write`、`test`、`review` 还需要能访问仓库兄弟目录里的 worktree。若 Claude 日志里出现 `ConnectionRefused`、`duration_api_ms: 0` 或上游没有请求记录，通常是编排器子进程没有网络权限，而不是 key/base URL 本身不可用。

## MCP

CLI 跑通后可以把同一套流程作为 MCP 工具暴露给任意 MCP host。以下为常见 host 的注册命令：

```bash
# Codex CLI / Codex Desktop
codex mcp add patchbay -- python scripts/patchbay_mcp_server.py

# Claude Code
claude mcp add patchbay -- python scripts/patchbay_mcp_server.py

# Claude Desktop: 编辑 claude_desktop_config.json，在 mcpServers 中添加
# Gemini CLI: 使用对应的 MCP server 注册方式
```

MCP 只调用 `scripts.ai_flow.service` 中已有函数，不复制业务逻辑。新工具名使用 `patchbay_*`，旧的 `ai_flow_*` 作为兼容别名保留。无论通过哪个 host 调用，流程和门禁保持一致。

## 故障排查

- Claude CLI 不存在：检查 `[commands].claude`，或用 `--mock` 验证流程。
- Codex CLI 不存在：检查 `[commands].codex`，或用 `--mock` 验证审查流程。
- DeepSeek API key 缺失：设置 `DEEPSEEK_API_KEY` 或切换 writer provider。
- Reasonix 只聊天不改文件：确认 `[writer].provider = "reasonix_cli"`，且 `[commands].reasonix` 指向 `reasonix.cmd`/`reasonix`。Patchbay 会自动使用 `reasonix acp`，不要把 `deepseek_api` 当作 Reasonix Agent。
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
