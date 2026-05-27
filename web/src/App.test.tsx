import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Workbench } from "./App";
import type { HandoffContext, PatchbayClient } from "./api";

const readyContext: HandoffContext = {
  run_id: "run-ready",
  handoff_summary: "Run run-ready is REVIEWED_PASS in phase apply; next safe action: apply.",
  status: "REVIEWED_PASS",
  current_phase: "apply",
  gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
  next_actions: [
    {
      name: "apply",
      safe: true,
      tool: "patchbay_apply",
      requires_human_confirmation: true,
      reason: "Tests passed and review returned PASS; human confirmation is still required."
    }
  ],
  provider_trail: [{ phase: "review", provider: "codex_cli", model: "gpt-5", status: "PASS", timestamp: "2026-05-24T10:02:00Z" }],
  artifacts: [{ name: "REVIEW.md", purpose: "review verdict", path: ".ai/runs/run-ready/REVIEW.md" }],
  timeline: [
    {
      source: "event",
      index: 0,
      timestamp: "2026-05-24T10:02:00Z",
      phase: "review",
      action: "success",
      status: "PASS",
      detail: "ready from context",
      provider: "codex_cli",
      artifact_paths: ["REVIEW.md"],
      next_action: "apply"
    }
  ],
  agent_activity: {
    headline: "Patchbay Agent 已准备好执行：应用补丁。",
    tone: "ready",
    current_step: {
      phase: "apply",
      label: "应用",
      status: "REVIEWED_PASS",
      status_label: "审查通过",
      summary: "Tests passed and review returned PASS; human confirmation is still required."
    },
    next_action: {
      name: "apply",
      label: "应用补丁",
      safe: true,
      tool: "patchbay_apply",
      requires_human_confirmation: true,
      reason: "Tests passed and review returned PASS; human confirmation is still required."
    },
    conversation_state: {
      task: "Ship dashboard",
      status: "REVIEWED_PASS",
      status_label: "审查通过",
      phase: "apply",
      phase_label: "应用",
      tone: "ready",
      next_step: "需要你确认后，Patchbay Agent 才会执行“应用补丁”。",
      composer_placeholder: "输入“确认”或点击“应用补丁”继续",
      suggestions: [
        {
          id: "apply",
          label: "应用补丁",
          action: "apply",
          safe: true,
          tool: "patchbay_apply",
          requires_human_confirmation: true,
          reason: "Tests passed and review returned PASS; human confirmation is still required."
        }
      ]
    },
    gate_cards: [
      { key: "approval", label: "批准", status: "done", tone: "success", detail: "计划已批准" },
      { key: "tests", label: "测试", status: "pass", tone: "success", detail: "测试通过" },
      { key: "review", label: "审查", status: "PASS", tone: "success", detail: "审查通过" },
      { key: "apply", label: "应用", status: "ready", tone: "ready", detail: "可以应用" }
    ],
    messages: [
      {
        id: "event-0",
        kind: "event",
        timestamp: "2026-05-24T10:02:00Z",
        phase: "review",
        title: "审查 · 完成 · 通过",
        body: "ready from context",
        status: "PASS",
        status_label: "通过",
        tone: "success",
        artifacts: ["REVIEW.md"],
        provider: "codex_cli",
        model: "gpt-5",
        tool: "patchbay_apply"
      }
    ]
  },
  cursors: { event: 1, trace: 0 }
};

const plannedContext: HandoffContext = {
  ...readyContext,
  run_id: "run-planned",
  status: "PLANNED",
  current_phase: "plan",
  gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
  next_actions: [
    {
      name: "approve",
      safe: true,
      tool: "patchbay_approve",
      requires_human_confirmation: true,
      reason: "Plan is ready for human approval before implementation."
    }
  ],
  agent_activity: {
    ...readyContext.agent_activity,
    headline: "Patchbay Agent 已准备好执行：批准计划。",
    current_step: { phase: "plan", label: "规划", status: "PLANNED", status_label: "等待批准", summary: "Plan is ready for human approval before implementation." },
    next_action: {
      name: "approve",
      label: "批准计划",
      safe: true,
      tool: "patchbay_approve",
      requires_human_confirmation: true,
      reason: "Plan is ready for human approval before implementation."
    },
    conversation_state: {
      task: "Approve a plan",
      status: "PLANNED",
      status_label: "等待批准",
      phase: "plan",
      phase_label: "规划",
      tone: "ready",
      next_step: "需要你确认后，Patchbay Agent 才会执行“批准计划”。",
      composer_placeholder: "输入“确认”或点击“批准计划”继续",
      suggestions: [
        {
          id: "approve",
          label: "批准计划",
          action: "approve",
          safe: true,
          tool: "patchbay_approve",
          requires_human_confirmation: true,
          reason: "Plan is ready for human approval before implementation."
        }
      ]
    },
    messages: [
      {
        id: "state-summary",
        kind: "state",
        timestamp: "2026-05-24T10:02:00Z",
        phase: "plan",
        title: "规划 · 状态更新 · 等待批准",
        body: "等待批准",
        status: "PLANNED",
        status_label: "等待批准",
        tone: "ready"
      }
    ]
  }
};

function createClient(overrides: Partial<PatchbayClient> = {}): PatchbayClient {
  return {
    agentMessage: vi.fn().mockResolvedValue({ run_id: "run-new", status: { run_id: "run-new", status: "PLANNED" } }),
    createRun: vi.fn().mockResolvedValue({ run_id: "run-new", status: "PLANNED" }),
    listRuns: vi.fn().mockResolvedValue({
      runs: [
        { run_id: "run-ready", task: "Ship dashboard", status: "REVIEWED_PASS", updated_at: "2026-05-24T10:00:00Z" },
        { run_id: "run-fix", task: "Needs fix", status: "REVIEWED_CHANGES_REQUESTED", updated_at: "2026-05-24T09:00:00Z" }
      ]
    }),
    getStatus: vi.fn().mockResolvedValue({
      run_id: "run-ready",
      task: "Ship dashboard",
      status: "REVIEWED_PASS",
      current_phase: "apply",
      tests_passed: true,
      review_result: "PASS",
      gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
      next_commands: ["apply"],
      artifacts: ["PLAN.md", "writer.log", "FINAL.diff"],
      effective_phase_providers: {
        plan: { provider: "claude_cli", model: "opus", command_key: "" },
        write: { provider: "reasonix_cli", model: "", command_key: "reasonix" },
        review: { provider: "codex_cli", model: "gpt-5", command_key: "" },
        fix: { provider: "reasonix_cli", model: "", command_key: "reasonix" }
      }
    }),
    getContext: vi.fn().mockResolvedValue(readyContext),
    getTrace: vi.fn().mockResolvedValue({
      total: 1,
      events: [
        {
          seq: 1,
          timestamp: "2026-05-24T10:02:00Z",
          agent: "codex_cli",
          phase: "review",
          action: "success",
          tool: "patchbay_review",
          path: ".ai/runs/run-ready/REVIEW.md",
          status: "PASS",
          detail: "ready"
        }
      ]
    }),
    getDiff: vi.fn().mockResolvedValue({ diff: "diff --git a/web b/web" }),
    getArtifact: vi.fn().mockResolvedValue({ text: "artifact text" }),
    getConfig: vi.fn().mockResolvedValue({ phases: { write: { provider: "reasonix_cli" } } }),
    runAction: vi.fn().mockResolvedValue({ ok: true }),
    apply: vi.fn().mockResolvedValue({ ok: true }),
    cleanup: vi.fn().mockResolvedValue({ ok: true }),
    ...overrides
  };
}

describe("Workbench", () => {
  it("renders a Codex-style thread and keeps orchestration details in the closed diagnostics drawer", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    expect(await screen.findByText("Patchbay Agent 已准备好执行：应用补丁。")).toBeInTheDocument();
    expect(await screen.findByText("ready from context")).toBeInTheDocument();
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toHaveAttribute("placeholder", "输入“确认”或点击“应用补丁”继续");
    expect(screen.queryByLabelText("阶段操作")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("门禁状态")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "诊断" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("reasonix_cli")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "提供方" }));

    expect(screen.getAllByText("reasonix_cli")[0]).toBeVisible();
    expect(screen.getAllByText("codex_cli")[0]).toBeVisible();
    expect(client.getContext).toHaveBeenCalledWith("run-ready");
  });

  it("filters the run list by search and status", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.selectOptions(screen.getByLabelText("状态筛选"), "REVIEWED_CHANGES_REQUESTED");
    await userEvent.type(screen.getByLabelText("搜索运行"), "fix");

    expect(screen.queryByRole("heading", { name: "Ship dashboard" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
  });

  it("creates a new plan run from the composer when no run is selected", async () => {
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValueOnce({ runs: [{ run_id: "run-new", task: "Build a chat thread", status: "PLANNED" }] }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-new",
        task: "Build a chat thread",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: {},
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({
        ...plannedContext,
        run_id: "run-new",
        agent_activity: {
          ...plannedContext.agent_activity,
          conversation_state: {
            ...plannedContext.agent_activity!.conversation_state!,
            task: "Build a chat thread"
          }
        }
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "Build a chat thread");
    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => expect(client.agentMessage).toHaveBeenCalledWith("Build a chat thread", { include: { plan: true }, background: true }));
    expect(await screen.findByRole("heading", { name: "Build a chat thread" })).toBeInTheDocument();
  });

  it("maps approve intent through the confirmation gate", async () => {
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: {},
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    expect(await screen.findByText("Patchbay Agent 已准备好执行：批准计划。")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "批准");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    const dialog = await screen.findByRole("dialog", { name: "确认批准计划" });
    expect(client.runAction).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "批准" }));
    expect(client.agentMessage).toHaveBeenCalledWith("approve", {
      runId: "run-ready",
      confirmation: "plan_approved",
      include: { diff: false, review: false },
      background: true
    });
  });

  it("advances implementation phases through agent autopilot", async () => {
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({
        runs: [{ run_id: "run-ready", task: "Implement through autopilot", status: "APPROVED" }]
      }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Implement through autopilot",
        status: "APPROVED",
        current_phase: "write",
        gate_state: { approved: true, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["write"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({
        ...plannedContext,
        run_id: "run-ready",
        status: "APPROVED",
        current_phase: "write",
        next_actions: [
          {
            name: "write",
            safe: true,
            tool: "patchbay_write",
            requires_human_confirmation: false,
            reason: "Plan was approved; writer may work inside the isolated worktree."
          }
        ],
        agent_activity: {
          ...plannedContext.agent_activity!,
          headline: "Patchbay Agent 已准备好执行：开始实现。",
          next_action: {
            name: "write",
            label: "开始实现",
            safe: true,
            tool: "patchbay_write",
            requires_human_confirmation: false,
            reason: "Plan was approved; writer may work inside the isolated worktree."
          },
          conversation_state: {
            ...plannedContext.agent_activity!.conversation_state!,
            composer_placeholder: "输入“继续”或点击“开始实现”",
            suggestions: [
              {
                id: "write",
                label: "开始实现",
                action: "write",
                safe: true,
                tool: "patchbay_write",
                requires_human_confirmation: false,
                reason: "Plan was approved; writer may work inside the isolated worktree."
              }
            ]
          }
        }
      })
    });

    render(<Workbench client={client} />);

    await screen.findByText("Patchbay Agent 已准备好执行：开始实现。");
    await userEvent.click(screen.getByRole("button", { name: /执行/ }));

    await waitFor(() =>
      expect(client.agentMessage).toHaveBeenCalledWith("continue", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("requires confirmation before apply and keeps blocked apply gated", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    await screen.findByText("Patchbay Agent 已准备好执行：应用补丁。");
    await userEvent.click(screen.getByRole("button", { name: /^确认$/ }));
    expect(client.apply).not.toHaveBeenCalled();

    const dialog = screen.getByRole("dialog", { name: /确认应用补丁/i });
    await userEvent.click(within(dialog).getByRole("button", { name: "应用" }));
    expect(client.agentMessage).toHaveBeenCalledWith("apply", {
      runId: "run-ready",
      confirmation: "apply_approved",
      include: { diff: true, review: true },
      background: false
    });

    const blockedContext = {
      ...readyContext,
      gate_state: { ready_to_apply: false },
      next_actions: [
        {
          name: "apply",
          safe: false,
          tool: "patchbay_apply",
          requires_human_confirmation: true,
          reason: "Apply is blocked until tests pass and review returns PASS."
        }
      ],
      agent_activity: {
        ...readyContext.agent_activity!,
        next_action: {
          name: "apply",
          label: "应用补丁",
          safe: false,
          tool: "patchbay_apply",
          requires_human_confirmation: true,
          reason: "Apply is blocked until tests pass and review returns PASS."
        },
        conversation_state: {
          ...readyContext.agent_activity!.conversation_state!,
          suggestions: [
            {
              id: "apply",
              label: "应用补丁",
              action: "apply",
              safe: false,
              requires_human_confirmation: true,
              reason: "Apply is blocked until tests pass and review returns PASS."
            }
          ]
        }
      }
    };
    const blockedClient = createClient({
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { ready_to_apply: false },
        next_commands: ["apply"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue(blockedContext)
    });

    render(<Workbench client={blockedClient} />);
    await screen.findByText("Apply is blocked until tests pass and review returns PASS.");
    await userEvent.click(screen.getAllByRole("button", { name: /应用补丁/i }).at(-1)!);

    expect(await screen.findByRole("dialog", { name: "暂不能执行" })).toBeInTheDocument();
    expect(blockedClient.apply).not.toHaveBeenCalled();
  });

  it("does not duplicate state-summary messages during empty incremental polling", async () => {
    const client = createClient({
      getContext: vi
        .fn()
        .mockResolvedValueOnce(plannedContext)
        .mockResolvedValueOnce({
          ...plannedContext,
          timeline: [],
          agent_activity: {
            ...plannedContext.agent_activity!,
            messages: []
          },
          cursors: { event: 1, trace: 0 }
        })
    });

    render(<Workbench client={client} pollIntervalMs={20} />);

    expect(await screen.findByText("等待批准")).toBeInTheDocument();
    await waitFor(() => {
      expect(client.getContext).toHaveBeenLastCalledWith("run-ready", { since_event: 1 });
    });
    expect(screen.getAllByText("等待批准")).toHaveLength(2);
  });

  it("sends free text through the conversational agent endpoint", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "这个 UI 应该更像一个对话线程");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("这个 UI 应该更像一个对话线程")).toBeInTheDocument();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
    expect(client.agentMessage).toHaveBeenCalledWith("这个 UI 应该更像一个对话线程", {
      runId: "run-ready",
      include: { diff: true, review: true },
      background: true
    });
  });

  it("treats background jobs as first-class running state", async () => {
    const runningContext: HandoffContext = {
      ...plannedContext,
      run_id: "run-ready",
      status: "RUNNING",
      current_phase: "write",
      next_actions: [],
      timeline: [
        {
          source: "event",
          index: 0,
          timestamp: "2026-05-24T10:03:00Z",
          phase: "agent",
          action: "queued",
          status: "QUEUED",
          detail: "Background agent turn queued."
        }
      ],
      agent_activity: {
        ...plannedContext.agent_activity!,
        headline: "Patchbay Agent 正在执行实现阶段。",
        tone: "running",
        current_step: { phase: "write", label: "实现", status: "RUNNING", status_label: "运行中", summary: "后台任务正在运行，状态会自动刷新。" },
        next_action: null,
        conversation_state: {
          task: "Background implementation",
          status: "RUNNING",
          status_label: "运行中",
          phase: "write",
          phase_label: "实现",
          tone: "running",
          next_step: "后台任务正在运行，完成后会出现下一步。",
          composer_placeholder: "后台任务运行中，完成后可继续",
          suggestions: [{ id: "write", label: "开始实现", action: "write", safe: true }]
        },
        messages: [
          {
            id: "event-0",
            kind: "event",
            timestamp: "2026-05-24T10:03:00Z",
            phase: "agent",
            title: "agent · 已排队 · 已排队",
            body: "Background agent turn queued.",
            status: "QUEUED",
            status_label: "已排队",
            tone: "running"
          }
        ]
      }
    };
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({
        runs: [{ run_id: "run-ready", task: "Background implementation", status: "APPROVED" }]
      }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Background implementation",
        status: "RUNNING",
        current_phase: "write",
        gate_state: { approved: true, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: [],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue(runningContext)
    });

    render(<Workbench client={client} />);

    expect(await screen.findByText("Patchbay Agent 正在执行实现阶段。")).toBeInTheDocument();
    expect(screen.getByText("后台任务运行中")).toBeInTheDocument();
    expect(screen.getByText("运行中 · 实现")).toBeInTheDocument();
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toBeDisabled();
    expect(screen.getByRole("button", { name: "发送消息" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /开始实现/ })).toBeDisabled();
  });
});
