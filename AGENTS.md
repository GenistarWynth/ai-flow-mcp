# Multi-Agent Workflow

当用户明确说：
- “走多模型流程”
- “用 Claude 规划，DeepSeek 实现，Codex 审查”
- “multi-agent workflow”

你必须使用 `scripts/patchbay`，不要直接改代码。旧入口 `scripts/ai-flow` 仍可兼容使用，但新文档优先使用 Patchbay 名称。

如果当前 MCP host 已配置 `patchbay_*` MCP 工具，可以用 MCP 调用同一套 Patchbay 编排器；旧的 `ai_flow_*` 工具名也保留为兼容别名。无论入口是什么，仍然必须遵守下面的阶段顺序和确认门禁。

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
