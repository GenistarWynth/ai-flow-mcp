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

## 功能概览

- CLI 流程：`agent message`、`web`、`plan`、`approve`、`write`、`test`、`review`、`fix`、`status`、`context`、`trace`、`diff`、`apply`、`cleanup`。
- MCP 工具：`patchbay_agent`、`patchbay_plan`、`patchbay_approve`、`patchbay_write`、`patchbay_test`、`patchbay_review`、`patchbay_fix`、`patchbay_status`、`patchbay_context`、`patchbay_events`、`patchbay_trace`、`patchbay_runs`、`patchbay_artifact`、`patchbay_config_show`、`patchbay_config_phase_set`、`patchbay_config_command_set`、`patchbay_config_test_add`、`patchbay_config_provider_add_cli`、`patchbay_diff`、`patchbay_apply`。
- 兼容旧 MCP 工具名：`ai_flow_*`。
- 默认使用隔离 git worktree，避免直接污染当前工作区。
- 每次运行都会在 `.ai/runs/<run_id>/` 下落盘计划、diff、日志和状态。
- 实现前必须经过人工确认计划。
- 应用补丁前会做路径与安全检查；默认情况下“没有测试命令”不算测试通过，除非显式设置 `workflow.allow_apply_without_tests = true`。
- reviewer 默认只读，并检查审查阶段没有修改 worktree。

## 快速开始

### npx 风格（推荐）

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay init
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay-mcp --root /path/to/repo
```

### 本地检出

```bash
python scripts/patchbay init
cp .ai/patchbay.example.toml .ai/patchbay.toml
```

Windows 也可以使用：

```bat
scripts\patchbay.cmd init
copy .ai\patchbay.example.toml .ai\patchbay.toml
```

### 交互式配置

```bash
patchbay config     # 交互式向导，无需手动编辑
patchbay config --doctor     # 验证解析后的阶段配置
patchbay config --set-key models.planner --set-value claude-opus-4-7
```

然后编辑 `.ai/patchbay.toml`，配置本机命令、模型名、writer provider 和测试命令 allowlist。

不要提交 `.ai/patchbay.toml`。这个文件用于放你的本地 provider、命令路径和环境变量名，已经被 `.gitignore` 忽略。

旧的 `scripts/ai-flow` 命令和 `.ai/ai-flow.toml` 配置仍然可用，作为兼容入口保留。

## CLI 用法

典型流程：

```bash
python scripts/patchbay plan --task "为 xxx 增加 yyy，并补测试"
python scripts/patchbay agent message "为 xxx 增加 yyy，并补测试" --json
python scripts/patchbay web --port 8765
python scripts/patchbay approve <run_id>
python scripts/patchbay write <run_id>
python scripts/patchbay test <run_id>
python scripts/patchbay review <run_id>
python scripts/patchbay apply <run_id>
```

查看状态和 diff：

```bash
python scripts/patchbay status <run_id>
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

Claude Desktop、Claude Code、Gemini CLI 或其他 MCP host 使用各自等价的 MCP server 注册方式即可。运行 `patchbay mcp doctor` 验证服务器是否可达。

`patchbay mcp doctor` 会真正启动 stdio MCP server，发送 `initialize` 和 `tools/list`，并检查 `patchbay_agent`、`patchbay_plan`、`patchbay_context` 等核心工具是否存在。Codex、Claude Code、Gemini 的 install 命令当前会打印 host 注册命令；Claude Desktop 会直接写入 JSON 配置。

安装后可用的 MCP 工具包括：

- `patchbay_agent`
- `patchbay_plan`
- `patchbay_approve`
- `patchbay_write`
- `patchbay_test`
- `patchbay_review`
- `patchbay_fix`
- `patchbay_status`
- `patchbay_context`
- `patchbay_events`
- `patchbay_trace`
- `patchbay_runs`
- `patchbay_artifact`
- `patchbay_config_show`
- `patchbay_config_phase_set`
- `patchbay_config_command_set`
- `patchbay_config_test_add`
- `patchbay_config_provider_add_cli`
- `patchbay_diff`
- `patchbay_apply`

## Codex Skill 安装

Patchbay 同时提供 Codex Skill。Skill 负责让 Codex 在合适场景遵守 Patchbay 的门禁流程；MCP server 负责提供实际工具。

```bash
patchbay skill install codex
patchbay skill print codex --json
```

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
