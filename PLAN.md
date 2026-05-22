下面是一份可以直接交给 Codex 实现的 \*\*PLAN.md\*\*。目标是：\*\*Codex Desktop 作为唯一交互入口，Claude Code 负责规划，Reasonix/DeepSeek 负责实现，Codex/gpt-5.5 负责审查，所有阶段由 Codex 调用本地编排工具完成。\*\*



\---



\# PLAN: Codex-Orchestrated Multi-Agent Coding Workflow



\## 1. 目标



实现一个本地多模型编排工作流，用户只通过 Codex Desktop 交互：



```text

User

&#x20;↓

Codex Desktop

&#x20;↓

ai-flow 编排器

&#x20;├─ Claude Code / claude-opus-4-7：只读分析与计划

&#x20;├─ Reasonix / deepseek-v4-pro：按计划实现

&#x20;├─ 本地测试 / lint / typecheck：事实验证

&#x20;└─ Codex / gpt-5.5：独立代码审查

```



核心要求：



1\. 用户只和 Codex 交互。

2\. Claude 只负责计划，默认不修改代码。

3\. Reasonix/DeepSeek 只负责实现计划。

4\. Codex reviewer 默认只审查，不直接修代码。

5\. 每个阶段都落盘，方便追踪与回滚。

6\. 默认使用独立 git worktree，避免污染当前工作区。

7\. 必须有人类确认计划后才能进入实现阶段。



\---



\## 2. 最终交互方式



用户在 Codex Desktop 中输入：



```text

走多模型流程：为 xxx 功能做 yyy 修改，补充测试，确保不破坏 zzz。

```



Codex 应执行：



```bash

scripts/ai-flow plan --task "..."

```



然后把生成的计划展示给用户。



用户确认后，Codex 再执行：



```bash

scripts/ai-flow approve <run\_id>

scripts/ai-flow write <run\_id>

scripts/ai-flow test <run\_id>

scripts/ai-flow review <run\_id>

```



如果 review 要求修改：



```bash

scripts/ai-flow fix <run\_id>

scripts/ai-flow test <run\_id>

scripts/ai-flow review <run\_id>

```



最多循环 2 次。



最终通过后：



```bash

scripts/ai-flow apply <run\_id>

```



将 worktree 中的最终 patch 应用回当前仓库。



\---



\## 3. 推荐目录结构



在仓库中新增：



```text

scripts/

&#x20; ai-flow                         # 可执行入口

&#x20; ai\_flow/

&#x20;   \_\_init\_\_.py

&#x20;   \_\_main\_\_.py

&#x20;   cli.py

&#x20;   config.py

&#x20;   state.py

&#x20;   git\_utils.py

&#x20;   safety.py

&#x20;   runner.py

&#x20;   artifacts.py



&#x20;   adapters/

&#x20;     \_\_init\_\_.py

&#x20;     claude\_planner.py

&#x20;     reasonix\_writer.py

&#x20;     deepseek\_writer.py

&#x20;     codex\_reviewer.py



&#x20;   prompts/

&#x20;     planner.md

&#x20;     writer.md

&#x20;     repair.md

&#x20;     reviewer.md



&#x20;   mcp\_server.py                 # 第二阶段实现



.ai/

&#x20; ai-flow.example.toml

&#x20; runs/                           # gitignore

&#x20; logs/                           # gitignore



docs/

&#x20; ai-flow.md

```



`.gitignore` 中加入：



```gitignore

.ai/runs/

.ai/logs/

.ai/worktrees/

```



\---



\## 4. 配置文件



新增 `.ai/ai-flow.example.toml`：



```toml

\[models]

planner = "claude-opus-4-7"

writer = "deepseek-v4-pro"

reviewer = "gpt-5.5"



\[commands]

claude = "claude"

codex = "codex"

reasonix = ""



\[writer]

provider = "deepseek\_api" # 可选：reasonix\_cli / deepseek\_api

max\_context\_files = 30

max\_patch\_attempts = 3

max\_repair\_iterations = 2



\[deepseek]

base\_url = "https://api.deepseek.com"

api\_key\_env = "DEEPSEEK\_API\_KEY"



\[workflow]

require\_plan\_approval = true

default\_branch\_prefix = "ai-flow"

worktree\_root = "../.ai-flow-worktrees"

fail\_on\_dirty\_workspace = true

apply\_to\_current\_workspace\_only\_after\_review\_pass = true



\[commands\_allowlist]

test = \[

&#x20; "npm test",

&#x20; "npm run test",

&#x20; "npm run lint",

&#x20; "npm run typecheck",

&#x20; "pytest",

&#x20; "pytest -q",

&#x20; "go test ./...",

&#x20; "cargo test"

]

```



实际使用时复制为：



```bash

cp .ai/ai-flow.example.toml .ai/ai-flow.toml

```



\---



\## 5. Run 状态与产物



每次任务生成一个 run：



```text

.ai/runs/<run\_id>/

&#x20; TASK.md

&#x20; PLAN.md

&#x20; plan.json

&#x20; APPROVAL.json

&#x20; STATUS.json



&#x20; WORKTREE\_PATH

&#x20; BASE\_COMMIT



&#x20; IMPLEMENTATION.md

&#x20; FINAL.diff



&#x20; TEST.log

&#x20; REVIEW.md

&#x20; FIXES.md



&#x20; claude-planner.log

&#x20; writer.log

&#x20; codex-reviewer.log

```



`STATUS.json` 维护状态机：



```text

NEW

&#x20;-> PLANNED

&#x20;-> APPROVED

&#x20;-> IMPLEMENTING

&#x20;-> IMPLEMENTED

&#x20;-> TESTING

&#x20;-> TESTED

&#x20;-> REVIEWING

&#x20;-> REVIEWED\_PASS

&#x20;-> REVIEWED\_CHANGES\_REQUESTED

&#x20;-> FIXING

&#x20;-> READY\_TO\_APPLY

&#x20;-> APPLIED

```



任何失败进入：



```text

FAILED

```



失败时必须写入：



```json

{

&#x20; "error": "...",

&#x20; "stage": "...",

&#x20; "suggested\_next\_action": "..."

}

```



\---



\## 6. CLI 命令



实现以下命令：



```bash

scripts/ai-flow init

scripts/ai-flow plan --task "..."

scripts/ai-flow approve <run\_id>

scripts/ai-flow write <run\_id>

scripts/ai-flow test <run\_id>

scripts/ai-flow review <run\_id>

scripts/ai-flow fix <run\_id>

scripts/ai-flow status <run\_id>

scripts/ai-flow diff <run\_id>

scripts/ai-flow apply <run\_id>

scripts/ai-flow cleanup <run\_id>

```



行为要求：



\### `plan`



\- 调用 Claude Code。

\- 只读分析。

\- 生成 `PLAN.md` 和 `plan.json`。

\- 不创建代码变更。

\- 不自动进入实现阶段。



\### `approve`



\- 写入 `APPROVAL.json`。

\- 后续 `write` 必须检查 approval。



\### `write`



\- 创建独立 git worktree。

\- 调用 Reasonix CLI 或 DeepSeek API。

\- 按 `PLAN.md` 和 `plan.json` 实现。

\- 保存最终 diff。



\### `test`



\- 在 worktree 中运行测试命令。

\- 测试命令来自：

&#x20; 1. `plan.json`

&#x20; 2. `.ai/ai-flow.toml`

&#x20; 3. 项目自动探测

\- 输出写入 `TEST.log`。



\### `review`



\- 调用 Codex CLI / gpt-5.5。

\- 只审查，不修改。

\- 输入包括：

&#x20; - `TASK.md`

&#x20; - `PLAN.md`

&#x20; - `FINAL.diff`

&#x20; - `TEST.log`

\- 输出 `REVIEW.md`。

\- 格式必须是：

&#x20; - `PASS`

&#x20; - 或 `CHANGES\_REQUESTED`



\### `fix`



\- 只处理 reviewer 指出的具体问题或测试失败。

\- 不允许额外重构。

\- 最多执行 2 轮。



\### `apply`



\- 只有当状态为 `REVIEWED\_PASS` 才允许。

\- 将 `FINAL.diff` 应用到当前工作区。

\- 如果当前工作区不干净，默认失败。



\---



\## 7. Claude Planner 规范



`prompts/planner.md` 内容要求：



```text

你是只读规划专家。



任务：

\- 分析当前仓库。

\- 不修改任何文件。

\- 不生成实现代码。

\- 输出可执行的实现计划。

\- 如果需求存在关键歧义，必须停止并提出问题。



输出必须包含两部分：



第一部分是机器可解析 JSON，位于：



BEGIN\_AI\_FLOW\_PLAN\_JSON

...

END\_AI\_FLOW\_PLAN\_JSON



第二部分是人类可读 Markdown 计划。

```



`plan.json` schema：



```json

{

&#x20; "version": 1,

&#x20; "summary": "",

&#x20; "requires\_user\_decision": false,

&#x20; "questions": \[],

&#x20; "assumptions": \[],

&#x20; "affected\_files": \[

&#x20;   {

&#x20;     "path": "",

&#x20;     "operation": "read|modify|create|delete",

&#x20;     "reason": ""

&#x20;   }

&#x20; ],

&#x20; "implementation\_steps": \[

&#x20;   {

&#x20;     "id": "S1",

&#x20;     "description": "",

&#x20;     "files": \[],

&#x20;     "verification": \[]

&#x20;   }

&#x20; ],

&#x20; "test\_commands": \[],

&#x20; "lint\_commands": \[],

&#x20; "typecheck\_commands": \[],

&#x20; "acceptance\_criteria": \[],

&#x20; "risks": \[],

&#x20; "out\_of\_scope": \[],

&#x20; "review\_checklist": \[]

}

```



调用方式示例：



```bash

claude -p "<planner prompt>" \\

&#x20; --model claude-opus-4-7 \\

&#x20; --permission-mode plan

```



如果本地 Claude CLI 参数不同，实现时应通过 `claude --help` 适配。



\---



\## 8. Writer 规范



Writer 支持两种 provider：



```text

reasonix\_cli

deepseek\_api

```



优先实现 `deepseek\_api`，如果配置了 Reasonix CLI，则可切换到 `reasonix\_cli`。



Writer 输入：



```text

TASK.md

PLAN.md

plan.json

受影响文件内容

项目约束

```



Writer 行为要求：



1\. 只能实现计划中的内容。

2\. 不允许无关重构。

3\. 不允许修改 `.env`、密钥、`.git`、CI secret、系统目录。

4\. 如果需要新增受影响文件之外的文件，必须在 `IMPLEMENTATION.md` 中说明原因。

5\. 必须补充或更新测试。

6\. 输出最终 diff。



DeepSeek API 调用建议：



```json

{

&#x20; "model": "deepseek-v4-pro",

&#x20; "thinking": {"type": "enabled"},

&#x20; "reasoning\_effort": "high"

}

```



Writer 输出格式使用 sentinel，方便解析：



```text

BEGIN\_WRITER\_SUMMARY

...

END\_WRITER\_SUMMARY



BEGIN\_DIFF

diff --git ...

END\_DIFF

```



如果需要更多文件上下文，输出：



```text

BEGIN\_NEED\_FILES

\["path/to/file1", "path/to/file2"]

END\_NEED\_FILES

```



编排器收到后读取文件，再次调用 writer。



最多允许 3 次上下文补充。



\---



\## 9. Codex Reviewer 规范



Reviewer 使用独立 Codex 调用。



要求：



1\. 审查者不能修改代码。

2\. 审查输入必须包括：

&#x20;  - 原始任务

&#x20;  - Claude 计划

&#x20;  - 实现 diff

&#x20;  - 测试日志

3\. 审查重点：

&#x20;  - 是否符合计划

&#x20;  - 是否引入 bug

&#x20;  - 是否有边界条件遗漏

&#x20;  - 是否缺测试

&#x20;  - 是否破坏兼容性

&#x20;  - 是否有安全问题

&#x20;  - 是否过度实现

4\. 输出必须为以下之一：



```text

PASS



Summary:

...

```



或：



```text

CHANGES\_REQUESTED



Blocking Issues:

1\. ...



Non-blocking Suggestions:

1\. ...



Required Fixes:

1\. ...

```



Reviewer prompt 中必须明确：



```text

不要调用 ai-flow。

不要实现代码。

不要修改文件。

只输出审查结果。

```



调用示例：



```bash

codex exec \\

&#x20; --model gpt-5.5 \\

&#x20; "Review the implementation..."

```



如果本地 Codex CLI 参数不同，实现时通过 `codex --help` 适配。



审查前后必须比较 worktree diff，确保 reviewer 没有改代码。



\---



\## 10. Git / Worktree 策略



默认不在当前工作区直接写代码。



流程：



```bash

git rev-parse --show-toplevel

git status --porcelain

git worktree add -b ai-flow/<run\_id> <worktree\_root>/<run\_id> HEAD

```



Writer、test、review 都在 worktree 中执行。



最终通过后生成：



```bash

FINAL.diff

```



用户确认后：



```bash

git apply .ai/runs/<run\_id>/FINAL.diff

```



如果当前工作区有未提交修改，`apply` 默认失败。



\---



\## 11. 安全规则



实现 `safety.py`：



必须拦截：



1\. 修改 repo 之外的路径。

2\. 修改 `.git/`。

3\. 修改 `.env`、`.env.\*`。

4\. 写入 private key、token、credential 文件。

5\. 执行未在 allowlist 中的测试命令。

6\. patch 中包含绝对路径。

7\. patch 中包含路径穿越，例如 `../`。

8\. reviewer 阶段发生文件修改。



所有外部命令必须：



\- 记录 command。

\- 记录 exit code。

\- stdout/stderr 写入日志。

\- 对 API key 做脱敏。



\---



\## 12. AGENTS.md 规则



在仓库 `AGENTS.md` 中加入：



```markdown

\# Multi-Agent Workflow



当用户明确说：

\- “走多模型流程”

\- “用 Claude 规划，DeepSeek 实现，Codex 审查”

\- “multi-agent workflow”



你必须使用 `scripts/ai-flow`，不要直接改代码。



流程：



1\. 运行：

&#x20;  `scripts/ai-flow plan --task "<用户任务>"`



2\. 阅读并展示：

&#x20;  `.ai/runs/<run\_id>/PLAN.md`



3\. 等待用户明确确认。



4\. 用户确认后运行：

&#x20;  `scripts/ai-flow approve <run\_id>`

&#x20;  `scripts/ai-flow write <run\_id>`

&#x20;  `scripts/ai-flow test <run\_id>`

&#x20;  `scripts/ai-flow review <run\_id>`



5\. 如果 review 是 CHANGES\_REQUESTED：

&#x20;  最多运行两轮：

&#x20;  `scripts/ai-flow fix <run\_id>`

&#x20;  `scripts/ai-flow test <run\_id>`

&#x20;  `scripts/ai-flow review <run\_id>`



6\. 只有 review PASS 且测试通过后，才询问用户是否 apply。



7\. 未经用户确认，不要运行：

&#x20;  `scripts/ai-flow apply <run\_id>`

```



\---



\## 13. MCP 第二阶段



CLI 跑通后，实现 MCP server：



```text

scripts/ai\_flow/mcp\_server.py

```



暴露工具：



```text

ai\_flow\_plan(task: string) -> run\_id, plan\_path, summary

ai\_flow\_approve(run\_id: string)

ai\_flow\_write(run\_id: string)

ai\_flow\_test(run\_id: string)

ai\_flow\_review(run\_id: string)

ai\_flow\_fix(run\_id: string)

ai\_flow\_status(run\_id: string)

ai\_flow\_diff(run\_id: string)

ai\_flow\_apply(run\_id: string)

```



MCP 只调用已有 Python 函数，不复制业务逻辑。



Codex 侧配置通过：



```bash

codex mcp add ai-flow -- python scripts/ai\_flow/mcp\_server.py

```



若 Codex Desktop 支持 MCP，则优先使用 MCP；否则继续使用 CLI。



\---



\## 14. 测试要求



实现 mock 模式：



```bash

scripts/ai-flow plan --task "..." --mock

scripts/ai-flow write <run\_id> --mock

scripts/ai-flow review <run\_id> --mock

```



至少测试：



1\. `plan.json` 解析。

2\. run 状态流转。

3\. worktree 创建失败时的错误处理。

4\. writer diff 解析。

5\. 非法路径 patch 被拒绝。

6\. reviewer 修改文件时被检测。

7\. test command allowlist 生效。

8\. fix 循环最多 2 次。

9\. dirty workspace 时 apply 失败。

10\. artifact 文件完整生成。



\---



\## 15. 文档



新增 `docs/ai-flow.md`，包含：



1\. 环境准备：

&#x20;  - Claude Code 登录

&#x20;  - Codex CLI 登录

&#x20;  - DeepSeek API key

2\. 配置方式。

3\. 常用命令。

4\. Codex Desktop 使用方式。

5\. 故障排查：

&#x20;  - Claude CLI 不存在

&#x20;  - Codex CLI 不存在

&#x20;  - DeepSeek API key 缺失

&#x20;  - patch apply 失败

&#x20;  - test command 不在 allowlist

6\. 安全说明。

7\. 如何清理 worktree。



\---



\## 16. Definition of Done



实现完成必须满足：



1\. 用户可在 Codex Desktop 中触发完整流程。

2\. `plan` 阶段只读，不产生代码 diff。

3\. 未 approve 前，`write` 失败。

4\. Writer 修改发生在独立 worktree。

5\. 每个 run 都有完整 artifacts。

6\. 测试日志可追踪。

7\. Codex reviewer 默认不改代码。

8\. Review 不通过时可进入 fix loop。

9\. 最多 fix 2 轮。

10\. Review PASS + tests pass 后才能 apply。

11\. apply 前检查当前 workspace 是否干净。

12\. 所有密钥不写入日志。

13\. 有 mock 测试，不依赖真实 API 也能跑通主流程。



\---



\## 17. 实施顺序



按以下顺序实现，不要跳步：



```text

P0: 创建目录结构、配置文件、文档骨架

P1: 实现 run\_id、artifact、STATUS.json

P2: 实现 CLI 命令框架

P3: 实现 Claude planner adapter

P4: 实现 approval gate

P5: 实现 git worktree 管理

P6: 实现 DeepSeek writer adapter

P7: 实现 patch safety validation

P8: 实现 test runner

P9: 实现 Codex reviewer adapter

P10: 实现 fix loop

P11: 实现 apply

P12: 实现 mock 测试

P13: 实现 MCP server

P14: 完善 AGENTS.md 与 docs

```



