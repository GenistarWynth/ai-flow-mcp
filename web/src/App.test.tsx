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

function createClient(overrides: Partial<PatchbayClient> = {}): PatchbayClient {
  return {
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
  it("renders the unified Patchbay Agent activity view with diagnostics folded", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    expect(await screen.findByText("Patchbay Agent")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    expect(await screen.findByText("Patchbay Agent 已准备好执行：应用补丁。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /应用补丁/i })).toBeInTheDocument();
    expect(screen.getByText("计划已批准")).toBeInTheDocument();
    expect(screen.getByText("测试通过")).toBeInTheDocument();
    expect(screen.getAllByText("审查通过").length).toBeGreaterThan(0);
    expect(await screen.findByText("ready from context")).toBeInTheDocument();
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

    expect(screen.queryByText("Ship dashboard")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
  });

  it("polls context incrementally and appends agent messages", async () => {
    const client = createClient({
      getContext: vi
        .fn()
        .mockResolvedValueOnce({
          ...readyContext,
          agent_activity: {
            ...readyContext.agent_activity,
            messages: [
              {
                id: "event-0",
                kind: "event",
                timestamp: "2026-05-24T10:02:00Z",
                phase: "review",
                title: "审查 · 开始 · 运行中",
                body: "reviewing",
                status: "RUNNING",
                status_label: "运行中",
                tone: "running"
              }
            ]
          },
          timeline: [
            {
              source: "event",
              index: 0,
              timestamp: "2026-05-24T10:02:00Z",
              phase: "review",
              action: "start",
              status: "RUNNING",
              detail: "reviewing"
            }
          ],
          cursors: { event: 1, trace: 0 }
        })
        .mockResolvedValueOnce({
          ...readyContext,
          agent_activity: {
            ...readyContext.agent_activity,
            messages: [
              {
                id: "event-1",
                kind: "gate",
                timestamp: "2026-05-24T10:04:00Z",
                phase: "apply",
                title: "应用 · 门禁 · 就绪",
                body: "ready to apply",
                status: "READY",
                status_label: "就绪",
                tone: "ready"
              }
            ]
          },
          timeline: [
            {
              source: "event",
              index: 1,
              timestamp: "2026-05-24T10:04:00Z",
              phase: "apply",
              action: "gate",
              status: "READY",
              detail: "ready to apply"
            }
          ],
          cursors: { event: 2, trace: 0 }
        })
    });

    render(<Workbench client={client} pollIntervalMs={20} />);

    expect(await screen.findByText("reviewing")).toBeInTheDocument();
    await waitFor(() => {
      expect(client.getContext).toHaveBeenLastCalledWith("run-ready", { since_event: 1 });
    });
    expect(await screen.findByText("ready to apply")).toBeInTheDocument();
  });

  it("requires confirmation before apply and cleanup, and gates apply readiness", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    const apply = await screen.findByRole("button", { name: /应用已审查 diff/i });
    await userEvent.click(apply);
    expect(client.apply).not.toHaveBeenCalled();

    const dialog = screen.getByRole("dialog", { name: /确认应用/i });
    await userEvent.click(within(dialog).getByRole("button", { name: "确认" }));
    expect(client.apply).toHaveBeenCalledWith("run-ready");

    await userEvent.click(screen.getByRole("button", { name: /清理运行/i }));
    expect(client.cleanup).not.toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(client.cleanup).not.toHaveBeenCalled();
  });

  it("disables apply when ready_to_apply is false", async () => {
    const blockedContext = {
      ...readyContext,
      gate_state: { ready_to_apply: false },
      next_actions: [],
      agent_activity: {
        ...readyContext.agent_activity,
        next_action: null,
        gate_cards: [{ key: "apply", label: "应用", status: "blocked", tone: "blocked" as const, detail: "等待门禁" }]
      }
    };
    const client = createClient({
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { ready_to_apply: false },
        next_commands: [],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue(blockedContext)
    });

    render(<Workbench client={client} />);

    expect(await screen.findByRole("button", { name: /应用已审查 diff/i })).toBeDisabled();
  });
});
