# Multi-Agent Workflow

当用户明确说：
- “走多模型流程”
- “multi-agent workflow”

你必须使用 `scripts/patchbay`，不要直接改代码。旧入口 `scripts/ai-flow` 仍可兼容使用，但新文档优先使用 Patchbay 名称。

Patchbay 支持任意 MCP host 作为交互入口（Claude Code、Claude Desktop、Codex CLI、Codex Desktop、Gemini CLI 等），流程和门禁完全一致。如果当前 MCP host 已配置 `patchbay_*` MCP 工具，可以用 MCP 调用同一套 Patchbay 编排器；旧的 `ai_flow_*` 工具名也保留为兼容别名。每个阶段（plan/write/review/fix）的 provider 和模型可以通过 `.ai/patchbay.toml` 的 `[phases.<phase>]` 独立配置。

跨 host 可见性：使用 `patchbay_events <run_id>` 和 `patchbay_status <run_id>` 可以在任何 host 中查看其他 agent/阶段做了什么（provider、model、action、status、timestamp）。无论入口是什么，仍然必须遵守下面的阶段顺序和确认门禁。

流程：

1. 运行：
   `scripts/patchbay plan --task "<用户任务>"`

2. 阅读并展示：
   `.ai/runs/<run_id>/PLAN.md`

3. 等待用户明确确认。

4. 用户确认后运行：
   `scripts/patchbay approve <run_id>`
   `scripts/patchbay write <run_id>`
   `scripts/patchbay test <run_id>`
   `scripts/patchbay review <run_id>`

5. 如果 review 是 CHANGES_REQUESTED：
   最多运行两轮：
   `scripts/patchbay fix <run_id>`
   `scripts/patchbay test <run_id>`
   `scripts/patchbay review <run_id>`

6. 只有 review PASS 且测试通过后，才询问用户是否 apply。

7. 未经用户确认，不要运行：
   `scripts/patchbay apply <run_id>`
