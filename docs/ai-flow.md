# ai-flow

`ai-flow` 是 Codex Desktop 驱动的本地多模型编排器：Claude 只读规划，Reasonix/DeepSeek 实现，Codex 审查。

## 环境准备

- 登录 Claude Code，并确保 `claude` CLI 可用。
- 登录 Codex CLI，并确保 `codex` CLI 可用。
- 使用 DeepSeek API 时，设置 `DEEPSEEK_API_KEY`。

## 配置

```bash
scripts/ai-flow init
cp .ai/ai-flow.example.toml .ai/ai-flow.toml
```

按需编辑 `.ai/ai-flow.toml`，尤其是 writer provider、命令路径和测试 allowlist。

Writer 有两种实现入口：

- `reasonix_cli`：调用 Reasonix ACP coding agent（`reasonix acp`），由 Reasonix 自己的文件系统工具修改独立 worktree，ai-flow 只负责审批权限并捕获最终 `git diff`。
- `deepseek_api`：直接调用 OpenAI-compatible Chat Completions API，要求模型按 sentinel 返回 unified diff；这是 API fallback，不等同于 Agent。

## 常用命令

```bash
scripts/ai-flow plan --task "..."
scripts/ai-flow approve <run_id>
scripts/ai-flow write <run_id>
scripts/ai-flow test <run_id>
scripts/ai-flow review <run_id>
scripts/ai-flow fix <run_id>
scripts/ai-flow status <run_id>
scripts/ai-flow diff <run_id>
scripts/ai-flow apply <run_id>
scripts/ai-flow cleanup <run_id>
```

mock 模式：

```bash
scripts/ai-flow plan --task "..." --mock
scripts/ai-flow write <run_id> --mock
scripts/ai-flow review <run_id> --mock
```

## Codex Desktop 使用方式

当用户要求“走多模型流程”时，先运行 plan 并展示 `.ai/runs/<run_id>/PLAN.md`。只有用户确认计划后，才能 approve/write/test/review。未经用户确认，不要 apply。

如果在带网络沙箱的 Codex Desktop 中运行真实模型阶段，`plan`、`write`、`review` 需要允许子进程访问对应上游。默认 `worktree_root = "../.ai-flow-worktrees"` 时，`write`、`test`、`review` 还需要能访问仓库兄弟目录里的 worktree。若 Claude 日志里出现 `ConnectionRefused`、`duration_api_ms: 0` 或上游没有请求记录，通常是编排器子进程没有网络权限，而不是 key/base URL 本身不可用。

## MCP

CLI 跑通后可以把同一套流程作为 MCP 工具暴露给 Codex：

```bash
codex mcp add ai-flow -- python scripts/ai_flow/mcp_server.py
```

MCP 只调用 `scripts.ai_flow.service` 中已有函数，不复制业务逻辑。若当前 Codex Desktop 暂不可用 MCP，继续使用 CLI 命令即可。

## 故障排查

- Claude CLI 不存在：检查 `[commands].claude`，或用 `--mock` 验证流程。
- Codex CLI 不存在：检查 `[commands].codex`，或用 `--mock` 验证审查流程。
- DeepSeek API key 缺失：设置 `DEEPSEEK_API_KEY` 或切换 writer provider。
- Reasonix 只聊天不改文件：确认 `[writer].provider = "reasonix_cli"`，且 `[commands].reasonix` 指向 `reasonix.cmd`/`reasonix`。ai-flow 会自动使用 `reasonix acp`，不要把 `deepseek_api` 当作 Reasonix Agent。
- Claude 输出空 result 但其实已生成计划：ai-flow 会从 `stream-json` assistant event 和 Claude transcript 中恢复计划文本；查看 `claude-planner.log` 确认恢复路径。
- patch apply 失败：检查 `writer.log` 和 `FINAL.diff`。
- test command 不在 allowlist：把确认安全的命令加入 `.ai/ai-flow.toml` 的 `commands_allowlist.test`。
- Windows PowerShell 拒绝运行 `.ps1` 脚本：优先使用 `codex.cmd` 与 `reasonix.cmd`（以及 `scripts/ai-flow.cmd`）等 `.cmd` 入口，避免修改系统 ExecutionPolicy。

## 安全说明

ai-flow 拒绝修改 repo 外路径、`.git/`、`.env*`、secret-like 文件、绝对路径 patch、路径穿越 patch，并要求测试命令在 allowlist 中。

## 清理 worktree

```bash
scripts/ai-flow cleanup <run_id>
```
