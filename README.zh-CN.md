# ai-flow MCP

[English](README.md)

面向 Codex Desktop 的本地多模型开发编排器。

`ai-flow` 把一次代码任务拆成可审计的几个阶段：Claude Code 只读规划，Reasonix ACP 或 DeepSeek 兼容 API 负责实现，本地测试命令负责事实验证，Codex CLI 负责只读审查。同一套流程既可以通过 CLI 使用，也可以暴露成 MCP 工具给 Codex Desktop 调用。

## 功能概览

- CLI 流程：`plan`、`approve`、`write`、`test`、`review`、`fix`、`status`、`diff`、`apply`、`cleanup`。
- MCP 工具：`ai_flow_plan`、`ai_flow_approve`、`ai_flow_write`、`ai_flow_test`、`ai_flow_review`、`ai_flow_fix`、`ai_flow_status`、`ai_flow_diff`、`ai_flow_apply`。
- 默认使用隔离的 git worktree，避免直接污染当前工作区。
- 每次运行都会在 `.ai/runs/<run_id>/` 下落盘计划、diff、日志和状态。
- 实现前必须经过人工确认计划。
- 应用补丁前会做路径与安全检查。
- reviewer 默认只读，并检查审查阶段没有修改 worktree。

## 快速开始

```bash
python scripts/ai-flow init
cp .ai/ai-flow.example.toml .ai/ai-flow.toml
```

Windows 也可以使用：

```bat
scripts\ai-flow.cmd init
copy .ai\ai-flow.example.toml .ai\ai-flow.toml
```

然后编辑 `.ai/ai-flow.toml`，配置本机命令、模型名、writer provider 和测试命令 allowlist。

不要提交 `.ai/ai-flow.toml`。这个文件用于放你的本地 provider、命令路径和环境变量名，已经被 `.gitignore` 忽略。

## CLI 用法

典型流程：

```bash
python scripts/ai-flow plan --task "为 xxx 增加 yyy，并补测试"
python scripts/ai-flow approve <run_id>
python scripts/ai-flow write <run_id>
python scripts/ai-flow test <run_id>
python scripts/ai-flow review <run_id>
python scripts/ai-flow apply <run_id>
```

查看状态和 diff：

```bash
python scripts/ai-flow status <run_id>
python scripts/ai-flow diff <run_id>
```

如果 review 要求修改，最多按配置执行修复循环：

```bash
python scripts/ai-flow fix <run_id>
python scripts/ai-flow test <run_id>
python scripts/ai-flow review <run_id>
```

清理隔离 worktree：

```bash
python scripts/ai-flow cleanup <run_id>
```

## Mock 模式

没有模型凭据时，可以先用 mock 模式验证完整编排流程：

```bash
python scripts/ai-flow plan --task "mock smoke" --mock
python scripts/ai-flow approve <run_id>
python scripts/ai-flow write <run_id> --mock
python scripts/ai-flow test <run_id>
python scripts/ai-flow review <run_id> --mock
python scripts/ai-flow apply <run_id>
```

Mock 模式适合检查 CLI、状态流转、worktree、补丁应用和 MCP 封装是否正常。

## MCP 安装

在仓库根目录运行：

```bash
codex mcp add ai-flow -- python scripts/ai_flow/mcp_server.py
```

然后重启或刷新 Codex Desktop，让它重新加载 MCP servers。

安装后可用的 MCP 工具包括：

- `ai_flow_plan`
- `ai_flow_approve`
- `ai_flow_write`
- `ai_flow_test`
- `ai_flow_review`
- `ai_flow_fix`
- `ai_flow_status`
- `ai_flow_diff`
- `ai_flow_apply`

MCP 只是调用 `scripts.ai_flow.service` 中的同一套业务逻辑，不复制另一份流程。

## 配置

公开示例配置在 `.ai/ai-flow.example.toml`。

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
provider = "deepseek_api"

[deepseek]
base_url = "https://api.deepseek.com"
api_key_env = "DEEPSEEK_API_KEY"
```

`api_key_env` 是环境变量名，不是 API key 本身。请把真实 key 放在环境变量里，不要写进仓库。

## Writer Provider

当前支持两种 writer 入口：

- `reasonix_cli`：调用 `reasonix acp`，让 Reasonix 作为真正的 coding agent 在隔离 worktree 中改文件。ai-flow 负责审批权限、捕获最终 diff，并拒绝不安全操作。
- `deepseek_api`：直接调用 OpenAI-compatible Chat Completions API，让模型按约定返回 unified diff。这是 API fallback，不等同于 agent。

如果你要使用 Reasonix agent，请把配置改成：

```toml
[commands]
reasonix = "reasonix"

[writer]
provider = "reasonix_cli"
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

ai-flow 默认做了这些防护：

- `.ai/ai-flow.toml`、`.ai/runs/`、`.ai/logs/`、`.ai/worktrees/` 和 `.ai-flow-worktrees/` 被忽略。
- 拒绝修改 `.git`、`.env*`、secret-like 文件、绝对路径和路径穿越 patch。
- Reasonix ACP 的 execute 权限会被拒绝，未知权限请求按保守策略处理。
- reviewer 只读运行，并检查 review 过程中没有修改 worktree。
- 日志会遮蔽环境变量和 adapter 已知的 API key。
- 测试命令必须在 `.ai/ai-flow.toml` 的 `commands_allowlist.test` 中。

## 排障

- `claude` 找不到：检查 `[commands].claude`，或先用 `--mock` 验证流程。
- `codex` 找不到：检查 `[commands].codex`，或先用 `--mock` 验证 review 流程。
- DeepSeek key 缺失：设置 `DEEPSEEK_API_KEY`，或把 `api_key_env` 改成你的环境变量名。
- Reasonix 只能聊天、不改文件：确认 `[writer].provider = "reasonix_cli"`，并且 `[commands].reasonix` 指向 `reasonix` 或 `reasonix.cmd`。不要把 `deepseek_api` 当成 Reasonix agent。
- 上游没有收到请求：在带沙箱的环境中，真实模型阶段可能需要允许子进程访问网络。
- patch apply 失败：查看 `.ai/runs/<run_id>/FINAL.diff` 和对应日志。
- test command 不在 allowlist：把确认安全的测试命令加入 `.ai/ai-flow.toml` 的 `commands_allowlist.test`。
- Windows 拒绝执行 `.ps1`：优先使用 `.cmd` 入口，例如 `scripts\ai-flow.cmd`、`codex.cmd`、`reasonix.cmd`。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 开源说明

这个仓库不包含真实 API key、本地私有配置、运行日志或历史 `.ai/runs`。公开配置文件只保留环境变量名和示例值。

## License

MIT
