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
  run_metrics: {
    duration_known: true,
    duration_source: "event_or_timestamp",
    total_duration_ms: 12340,
    phase_durations_ms: { plan: 1200, write: 8000, test: 940, review: 2200 },
    phase_attempts: { plan: 1, write: 1, test: 1, review: 1 },
    event_count: 8,
    trace_count: 5,
    provider_usage: [
      { phase: "plan", provider: "claude_cli", model: "opus", events: 2, duration_ms: 1200 },
      { phase: "write", provider: "reasonix_cli", model: "", events: 2, duration_ms: 8000 },
      { phase: "review", provider: "codex_cli", model: "gpt-5", events: 2, duration_ms: 2200 }
    ],
    cost: { known: false, currency: "USD", estimated_total: null, by_phase: {} },
    token_usage: { known: false, input_tokens: null, output_tokens: null, cached_tokens: null, total_tokens: null, by_phase: {} }
  },
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
    health_cards: [
      {
        key: "economy_route",
        label: "Economy route",
        status: "healthy",
        tone: "success",
        detail: "Economy route is configured and observed for all high-volume write/fix phases.",
        recommendation: "",
        next_action: "none",
        coverage_percent: 100
      }
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
      run_metrics: readyContext.run_metrics,
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
    getConfigProfile: vi.fn().mockResolvedValue({ profile: "custom" }),
    applyConfigProfile: vi.fn().mockResolvedValue({
      profile: "economy",
      status: {
        profile: "economy",
        economy: {
          matches: true,
          write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
          fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
          command_ready: false,
          command_status: {
            write: { required: true, ready: false, status: "missing_config", command_key: "reasonix" },
            fix: { required: true, ready: false, status: "missing_config", command_key: "reasonix" }
          }
        },
        phase_strategy: {
          plan: { provider: "claude_cli", model: "opus", tier: "supervision", reason: "Use a stronger planner." },
          write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", tier: "economy", economy_route: true },
          fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", tier: "economy", economy_route: true },
          review: { provider: "codex_cli", model: "gpt-5", tier: "supervision", reason: "Use a stronger reviewer." }
        }
      },
      next_actions: ["readiness", "start"]
    }),
    getDoctor: vi.fn().mockResolvedValue({
      ok: false,
      root: "C:/repo",
      checks: {
        repo: { ok: true },
        config: { ok: true },
        mcp: { ok: true, skipped: true, note: "Skipped by web workbench." },
        skill: { ok: true, installed: false }
      },
      next_actions: ["Run `patchbay skill install codex` so Codex can discover the Patchbay Skill."],
      actions: [
        {
          id: "install_skill",
          label: "Install Codex Skill",
          kind: "command",
          command: "patchbay skill install codex",
          safe: true,
          reason: "Install the bundled Patchbay Skill."
        },
        {
          id: "refresh_readiness",
          label: "Refresh readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Re-run read-only readiness checks."
        }
      ]
    }),
    runAction: vi.fn().mockResolvedValue({ ok: true }),
    apply: vi.fn().mockResolvedValue({ ok: true }),
    cleanup: vi.fn().mockResolvedValue({ ok: true }),
    ...overrides
  };
}

describe("Workbench", () => {
  it("copies structured readiness command actions from the diagnostics panel", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: vi.fn().mockResolvedValue({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: false } },
        next_actions: ["Run `patchbay skill install codex` so Codex can discover the Patchbay Skill."],
        actions: [
          {
            id: "install_skill",
            label: "Install Codex Skill",
            kind: "command",
            command: "patchbay skill install codex",
            safe: true,
            reason: "Install the bundled Patchbay Skill."
          }
        ]
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.click(within(details).getByRole("button", { name: "Copy command Install Codex Skill" }));

    expect(writeText).toHaveBeenCalledWith("patchbay skill install codex");
    expect(await within(details).findByRole("button", { name: "Copy command Install Codex Skill" })).toHaveTextContent("Copied");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.agentMessage).not.toHaveBeenCalled();
  });

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
    expect(screen.getByText("12s")).toBeVisible();
    expect(screen.getAllByText("实现 8.0s")[0]).toBeVisible();
    expect(screen.getByText("8 / 5")).toBeVisible();
    expect(screen.getByText("未上报")).toBeVisible();
    expect(screen.getByText("待上报")).toBeVisible();

    await userEvent.click(screen.getByRole("tab", { name: "提供方" }));

    expect(screen.getAllByText("reasonix_cli")[0]).toBeVisible();
    expect(screen.getAllByText("codex_cli")[0]).toBeVisible();
    expect(client.getContext).toHaveBeenCalledWith("run-ready");

    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    expect(await screen.findByText("需要处理")).toBeVisible();
    expect(screen.getAllByText(/patchbay skill install codex/)[0]).toBeVisible();
    expect(screen.getByRole("button", { name: "Refresh readiness" })).toBeVisible();
    expect(client.getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex" });
  });

  it("surfaces token totals and retry phases in efficiency metrics", async () => {
    const metricsContext: HandoffContext = {
      ...readyContext,
      run_metrics: {
        ...readyContext.run_metrics!,
        phase_attempts: { plan: 1, write: 1, test: 1, review: 2, fix: 1 },
        provider_usage: [
          {
            phase: "review",
            provider: "codex_cli",
            model: "gpt-5",
            events: 2,
            duration_ms: 2200,
            total_tokens: 4000,
            token_usage: { known: true, input_tokens: 3000, output_tokens: 1000, cached_tokens: 0, total_tokens: 4000 },
            cost: { known: true, currency: "USD", estimated_total: 0.12 }
          }
        ],
        token_usage: {
          known: true,
          input_tokens: 8200,
          output_tokens: 4100,
          cached_tokens: 0,
          total_tokens: 12300,
          by_phase: { review: { known: true, input_tokens: 3000, output_tokens: 1000, cached_tokens: 0, total_tokens: 4000 } }
        },
        cost: { known: true, currency: "USD", estimated_total: 0.42, by_phase: { review: { known: true, currency: "USD", estimated_total: 0.12 } } },
        routing_evidence: {
          economy_configured: true,
          summary: "Economy route configured; observed write, fix not observed yet.",
          phases: {
            write: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true },
            fix: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true }
          },
          observed_economy_phases: ["write"],
          missing_evidence: ["fix"],
          coverage: {
            required_phases: ["write", "fix"],
            required_total: 2,
            configured_economy_total: 2,
            observed_total: 1,
            observed_economy_total: 1,
            observed_other_total: 0,
            observed_economy_ratio: 0.5,
            observed_economy_percent: 50,
            complete: false,
            label: "1/2 economy phases observed"
          },
          economy_health: {
            status: "pending_evidence",
            severity: "info",
            configured: true,
            target: { provider: "reasonix_cli", model: "deepseek-v4-pro" },
            required_phases: ["write", "fix"],
            missing_config_phases: [],
            drift_phases: [],
            missing_evidence: ["fix"],
            observed_economy_phases: ["write"],
            summary: "Economy route is configured; waiting for fix provider evidence.",
            recommendation: "Run or poll write/fix phases to confirm high-volume work is actually using the economy route.",
            next_action: "wait_for_routing_evidence"
          },
          actions: [
            {
              id: "inspect_routing_events",
              label: "Inspect routing events",
              kind: "diagnostic_tab",
              tab: "Trace",
              safe: true,
              reason: "Open provider events to inspect routing evidence."
            }
          ]
        }
      }
    };
    const client = createClient({
      getContext: vi.fn().mockResolvedValue(metricsContext),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
        run_metrics: metricsContext.run_metrics,
        artifacts: [],
        effective_phase_providers: {}
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));

    expect(screen.getByText("12.3k")).toBeVisible();
    expect(screen.getByText("USD 0.42")).toBeVisible();
    expect(screen.getByText("审查 4.0k")).toBeVisible();
    expect(screen.getByText("审查 USD 0.12")).toBeVisible();
    expect(screen.getByText("审查 / codex_cli 4.0k tok | USD 0.12")).toBeVisible();
    expect(screen.getByText("Economy route configured; observed write, fix not observed yet.")).toBeVisible();
    const healthSection = screen.getByRole("heading", { name: "健康" }).closest("section")!;
    expect(within(healthSection).getByText("Economy route")).toBeVisible();
    expect(within(healthSection).getByText("100% economy observed")).toBeVisible();
    expect(screen.getByText("经济覆盖")).toBeVisible();
    expect(screen.getByText("50% · 1/2")).toBeVisible();
    expect(screen.getByText("经济健康")).toBeVisible();
    expect(screen.getAllByText("待观测").length).toBeGreaterThan(0);
    expect(screen.getByText("6")).toBeVisible();
    expect(screen.getByText("审查 2x")).toBeVisible();
    const metricsSection = screen.getByRole("heading", { name: "效率" }).closest("section")!;
    await userEvent.click(within(metricsSection).getByRole("button", { name: "Inspect routing events" }));
    expect(screen.getByRole("tab", { name: "活动" })).toHaveAttribute("aria-selected", "true");
  });

  it("runs structured health-card actions without advancing run gates", async () => {
    const healthActionContext: HandoffContext = {
      ...readyContext,
      agent_activity: {
        ...readyContext.agent_activity!,
        health_cards: [
          {
            key: "economy_route",
            label: "Economy route",
            status: "not_configured",
            tone: "blocked",
            detail: "Economy route is missing for write/fix; high-volume work may use higher-cost providers.",
            recommendation: "Run `patchbay config profile apply economy` before write/fix.",
            next_action: "apply_economy_profile",
            action: {
              id: "apply_economy_profile",
              label: "Apply economy profile",
              kind: "local_agent",
              message: "apply economy profile",
              safe: true,
              reason: "Routes write/fix to the configured Reasonix/DeepSeek economy profile."
            },
            coverage_percent: 0
          }
        ]
      }
    };
    const client = createClient({
      getContext: vi.fn().mockResolvedValue(healthActionContext),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
        run_metrics: readyContext.run_metrics,
        artifacts: [],
        effective_phase_providers: {}
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    const healthSection = screen.getByRole("heading", { name: "健康" }).closest("section")!;
    await userEvent.click(within(healthSection).getByRole("button", { name: "Apply economy profile" }));

    await waitFor(() => expect(client.applyConfigProfile).toHaveBeenCalledWith("economy"));
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
    expect(client.agentMessage).not.toHaveBeenCalledWith("continue", expect.anything());
  });

  it("opens diagnostics for structured routing inspection health actions", async () => {
    const inspectContext: HandoffContext = {
      ...readyContext,
      agent_activity: {
        ...readyContext.agent_activity!,
        health_cards: [
          {
            key: "economy_route",
            label: "Economy route",
            status: "drift",
            tone: "blocked",
            detail: "Economy route is configured, but write observed non-economy provider events.",
            recommendation: "Inspect provider events and command routing before continuing.",
            next_action: "inspect_routing_events",
            action: {
              id: "inspect_routing_events",
              label: "Inspect routing events",
              kind: "diagnostic_tab",
              tab: "Trace",
              safe: true,
              reason: "Open provider events to inspect the non-economy write/fix provider evidence."
            },
            coverage_percent: 50
          }
        ]
      }
    };
    const client = createClient({
      getContext: vi.fn().mockResolvedValue(inspectContext)
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    const healthSection = screen.getByRole("heading", { name: "健康" }).closest("section")!;
    await userEvent.click(within(healthSection).getByRole("button", { name: "Inspect routing events" }));

    expect(screen.getByRole("tab", { name: "活动" })).toHaveAttribute("aria-selected", "true");
    expect(client.applyConfigProfile).not.toHaveBeenCalled();
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("shows command setup actions for economy command health", async () => {
    const commandContext: HandoffContext = {
      ...readyContext,
      run_metrics: {
        ...readyContext.run_metrics!,
        routing_evidence: {
          economy_configured: true,
          economy_command_ready: false,
          command_not_ready_phases: ["write", "fix"],
          summary: "Economy route is configured, but write/fix cannot execute because the Reasonix command is not ready.",
          phases: {
            write: {
              configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
              configured_economy: true,
              command_status: { required: true, ready: false, status: "missing_config", command_key: "reasonix" }
            },
            fix: {
              configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
              configured_economy: true,
              command_status: { required: true, ready: false, status: "missing_config", command_key: "reasonix" }
            }
          },
          economy_health: {
            status: "command_not_ready",
            severity: "warning",
            configured: true,
            target: { provider: "reasonix_cli", model: "deepseek-v4-pro" },
            required_phases: ["write", "fix"],
            missing_config_phases: [],
            command_not_ready_phases: ["write", "fix"],
            drift_phases: [],
            missing_evidence: ["write", "fix"],
            observed_economy_phases: [],
            summary: "Economy route is configured, but write/fix cannot execute because the Reasonix command is not ready.",
            recommendation: "Set `commands.reasonix` before continuing high-volume write/fix work.",
            next_action: "configure_reasonix_command"
          }
        }
      },
      agent_activity: {
        ...readyContext.agent_activity!,
        health_cards: [
          {
            key: "economy_route",
            label: "Economy route",
            status: "command_not_ready",
            tone: "blocked",
            detail: "Economy route is configured, but write/fix cannot execute because the Reasonix command is not ready.",
            recommendation: "Set `commands.reasonix` before continuing high-volume write/fix work.",
            next_action: "configure_reasonix_command",
            coverage_percent: 0
          }
        ]
      }
    };
    const client = createClient({
      agentMessage: vi.fn().mockResolvedValue({
        run_id: null,
        action: "reasonix_command_configure",
        ok: true,
        reply: "Reasonix command configured."
      }),
      getContext: vi.fn().mockResolvedValue(commandContext),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
        run_metrics: commandContext.run_metrics,
        artifacts: [],
        effective_phase_providers: {}
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    expect(screen.getByText("命令未就绪 · write/fix")).toBeVisible();
    expect(screen.getAllByText("命令未配置").length).toBeGreaterThan(0);
    await userEvent.click(screen.getAllByRole("button", { name: "Configure Reasonix" })[0]);

    expect(client.agentMessage).toHaveBeenCalledWith("configure reasonix command");
    expect(client.applyConfigProfile).not.toHaveBeenCalled();
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("configures an explicit Reasonix path from the readiness panel", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "reasonix_command_configure",
      ok: true,
      reply: "Reasonix command configured."
    });
    const getDoctor = vi.fn().mockResolvedValue({
      ok: false,
      root: "C:/repo",
      host: "codex",
      checks: {
        repo: { ok: true },
        config: { ok: true },
        mcp: { ok: true, skipped: true },
        skill: { ok: true }
      },
      actions: [
        {
          id: "configure_reasonix_command",
          label: "Configure Reasonix",
          kind: "local_agent",
          message: "configure reasonix command",
          safe: true,
          reason: "Set commands.reasonix so the economy route can execute."
        }
      ]
    });
    const client = createClient({ agentMessage, getDoctor });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.type(within(details).getByLabelText("Reasonix command path"), "C:/Program Files/Reasonix/reasonix.cmd");
    await userEvent.click(within(details).getByRole("button", { name: "Configure Reasonix" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith('configure reasonix command to "C:/Program Files/Reasonix/reasonix.cmd"')
    );
    expect(client.applyConfigProfile).not.toHaveBeenCalled();
    expect(client.runAction).not.toHaveBeenCalled();
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

  it("shows a local agent reply when a new-task message does not create a run", async () => {
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage: vi.fn().mockResolvedValue({
        run_id: null,
        action: "runs",
        ok: true,
        reply: "No Patchbay runs found. Send a task to start with a plan.",
        next_actions: [],
        actions: [
          {
            id: "open_readiness",
            label: "Open readiness",
            kind: "local_agent",
            message: "readiness",
            safe: true,
            reason: "Run read-only setup diagnostics."
          },
          {
            id: "apply_economy_profile",
            label: "Apply economy profile",
            kind: "local_agent",
            message: "apply economy profile",
            safe: true,
            reason: "Route write/fix work to Reasonix/DeepSeek."
          },
          {
            id: "start_new_task",
            label: "Start new task",
            kind: "focus_composer",
            safe: true,
            reason: "Focus the composer."
          }
        ],
        runs: { count: 0, runs: [] }
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "status");
    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => expect(client.agentMessage).toHaveBeenCalledWith("status", { include: { plan: true }, background: true }));
    expect(await screen.findByText("No Patchbay runs found. Send a task to start with a plan.")).toBeVisible();
    expect(screen.getByRole("button", { name: /Open readiness/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /Apply economy profile/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /Start new task/ })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Apply economy profile/ }));
    await waitFor(() => expect(client.applyConfigProfile).toHaveBeenCalledWith("economy"));
    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getAllByText("命令未配置")).toHaveLength(2);
    expect(client.getStatus).not.toHaveBeenCalled();
  });

  it("keeps conversational readiness targeted to the host named in the message", async () => {
    const getDoctor = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        host: "codex",
        root: "C:/repo",
        checks: { repo: { ok: true }, mcp: { ok: true, skipped: true } },
        next_actions: []
      })
      .mockResolvedValue({
        ok: false,
        host: "claude-desktop",
        root: "C:/repo",
        checks: { repo: { ok: true }, mcp: { ok: true, skipped: true } },
        next_actions: []
      });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "doctor",
      ok: false,
      reply: "Patchbay readiness checks found setup work.",
      setup_host: "claude-desktop",
      doctor: {
        ok: false,
        host: "claude-desktop",
        root: "C:/repo",
        checks: { repo: { ok: true }, mcp: { ok: true, skipped: true } },
        next_actions: ["Run `patchbay doctor --host claude-desktop --json` for MCP evidence."],
        actions: [
          {
            id: "probe_mcp",
            label: "Probe MCP",
            kind: "command",
            command: "patchbay doctor --host claude-desktop --json",
            host: "claude-desktop",
            safe: true,
            reason: "Run host-aware MCP readiness."
          },
          {
            id: "refresh_readiness",
            label: "Refresh readiness",
            kind: "local_agent",
            message: "readiness",
            host: "claude-desktop",
            safe: true,
            reason: "Refresh host-aware readiness."
          }
        ]
      },
      actions: [
        {
          id: "probe_mcp",
          label: "Probe MCP",
          kind: "command",
          command: "patchbay doctor --host claude-desktop --json",
          host: "claude-desktop",
          safe: true,
          reason: "Run host-aware MCP readiness."
        },
        {
          id: "refresh_readiness",
          label: "Refresh readiness",
          kind: "local_agent",
          message: "readiness",
          host: "claude-desktop",
          safe: true,
          reason: "Refresh host-aware readiness."
        }
      ]
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor,
      agentMessage
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "readiness for Claude Desktop{enter}");

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("readiness for Claude Desktop", { include: { plan: true }, background: true }));
    expect(await screen.findByText("Patchbay readiness checks found setup work.")).toBeVisible();
    expect(screen.getByText("patchbay doctor --host claude-desktop --json")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: /Refresh readiness/ }));
    expect(await screen.findByLabelText("MCP host")).toHaveValue("claude-desktop");
  });

  it("opens the latest run from a missing-run reply without advancing gates", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "missing_run",
      ok: false,
      reply: "`continue` needs an existing run_id. Latest run is run-ready (PLANNED). Open that run first.",
      next_actions: ["open latest run", "runs", "readiness"],
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        suggested_message: "open latest run",
        safe_actions: ["open_run", "status", "events"],
        requested_view: { tab: "Diff", reason: "The prompt asked for the run diff or patch." }
      },
      requested_view: { tab: "Diff", reason: "The prompt asked for the run diff or patch." },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          tab: "Diff",
          safe: true,
          reason: "Open the latest Patchbay run before choosing any gated action."
        },
        {
          id: "open_readiness",
          label: "Open readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Run read-only setup diagnostics."
        }
      ],
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "diff{enter}");

    const openLatest = await screen.findByRole("button", { name: /open latest run/i });
    expect(openLatest).toBeVisible();
    await userEvent.click(openLatest);

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready"));
    expect(screen.getByRole("tab", { name: "差异" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("diff --git a/web b/web")).toBeVisible();
    expect(agentMessage).toHaveBeenCalledTimes(1);
    expect(agentMessage).toHaveBeenCalledWith("diff", { include: { plan: true }, background: true });
    expect(agentMessage).not.toHaveBeenCalledWith("continue", expect.objectContaining({ runId: "run-ready" }));
    expect(agentMessage).not.toHaveBeenCalledWith("approve", expect.anything());
    expect(agentMessage).not.toHaveBeenCalledWith("apply", expect.anything());
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
    expect(client.cleanup).not.toHaveBeenCalled();
  });

  it("uses structured missing-run actions without parsing next-action prose", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "missing_run",
      ok: false,
      reply: "`continue` needs an existing run_id. Latest run is run-ready (PLANNED).",
      next_actions: ["runs", "readiness"],
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        requested_view: { tab: "Trace", reason: "The prompt asked for run events or trace." }
      },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          tab: "Trace",
          safe: true,
          reason: "Open the latest Patchbay run before choosing any gated action."
        }
      ],
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "continue{enter}");

    const openLatest = await screen.findByRole("button", { name: /open latest run/i });
    await userEvent.click(openLatest);

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "活动" })).toHaveAttribute("aria-selected", "true");
    expect(agentMessage).toHaveBeenCalledTimes(1);
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("opens requested diagnostics from run-bound agent replies", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "artifact",
      ok: true,
      reply: "Requested run logs.",
      requested_view: { tab: "Log", reason: "The prompt asked for run logs." },
      actions: [
        {
          id: "open_log",
          label: "Open Log",
          kind: "diagnostic_tab",
          tab: "Log",
          safe: true,
          reason: "Open the requested run diagnostic view."
        }
      ]
    });
    const initialStatus = {
      run_id: "run-ready",
      task: "Ship dashboard",
      status: "REVIEWED_PASS",
      current_phase: "apply",
      tests_passed: true,
      review_result: "PASS",
      gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
      run_metrics: readyContext.run_metrics,
      next_commands: ["apply"],
      artifacts: ["PLAN.md"],
      effective_phase_providers: {}
    };
    const refreshedStatus = {
      ...initialStatus,
      artifacts: ["writer.log", "PLAN.md"]
    };
    const getArtifact = vi
      .fn()
      .mockResolvedValueOnce({ text: "old plan text" })
      .mockResolvedValueOnce({ text: "writer log text" });
    const client = createClient({
      agentMessage,
      getStatus: vi.fn().mockResolvedValueOnce(initialStatus).mockResolvedValue(refreshedStatus),
      getArtifact
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "查看失败原因");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("查看失败原因", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await waitFor(() => expect(screen.getByRole("tab", { name: "日志" })).toHaveAttribute("aria-selected", "true"));
    expect(screen.getByRole("button", { name: "诊断" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("writer log text")).toBeVisible();
    expect(getArtifact).toHaveBeenLastCalledWith("run-ready", "writer.log", { tail: 80 });
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("opens localized diagnostic next-actions from missing-run replies", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "missing_run",
      ok: false,
      reply: "`继续推进` needs an existing run_id. Latest run is run-ready (PLANNED).",
      next_actions: ["查看日志", "就绪"],
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED"
      },
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: ["PLAN.md", "writer.log"],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready", artifacts: [{ name: "writer.log", purpose: "Writer log" }] })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "继续推进{enter}");

    await userEvent.click(await screen.findByRole("button", { name: "查看日志" }));

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "日志" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready"));
    expect(agentMessage).toHaveBeenCalledTimes(1);
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("opens actual Chinese failure next-actions from missing-run replies", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "missing_run",
      ok: false,
      reply: "`为什么失败` needs an existing run_id. Latest run is run-ready (FAILED).",
      next_actions: ["查看失败原因", "就绪"],
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "FAILED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "FAILED"
      },
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "FAILED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "FAILED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "FAILED",
        current_phase: "write",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: [],
        artifacts: ["writer.log"],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready", status: "FAILED", artifacts: [{ name: "writer.log", purpose: "Writer log" }] })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "为什么失败{enter}");

    await userEvent.click(await screen.findByRole("button", { name: "查看失败原因" }));

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "日志" })).toHaveAttribute("aria-selected", "true");
    expect(agentMessage).toHaveBeenCalledTimes(1);
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("maps localized Reasonix setup next-actions to the command configurator", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: null,
        action: "doctor",
        ok: false,
        reply: "Reasonix 命令未配置。",
        next_actions: ["配置 Reasonix 命令"]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "reasonix_command_configure",
        ok: true,
        reply: "Reasonix command configured."
      });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "检查 Reasonix");
    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await userEvent.click(await screen.findByRole("button", { name: "Configure Reasonix" }));

    await waitFor(() => expect(agentMessage).toHaveBeenLastCalledWith("configure reasonix command"));
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("opens the latest run from a structured status reply without gated action text", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "runs",
      ok: true,
      reply: "Latest Patchbay run is run-ready (PLANNED). Open that run before choosing any gated action.",
      next_actions: ["readiness"],
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          safe: true,
          reason: "Open the latest Patchbay run without advancing any gate."
        },
        {
          id: "open_readiness",
          label: "Open readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Run read-only setup diagnostics."
        }
      ],
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "status{enter}");

    const openLatest = await screen.findByRole("button", { name: /open latest run/i });
    await userEvent.click(openLatest);

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready"));
    expect(agentMessage).toHaveBeenCalledTimes(1);
    expect(agentMessage).toHaveBeenCalledWith("status", { include: { plan: true }, background: true });
    expect(agentMessage).not.toHaveBeenCalledWith("continue", expect.objectContaining({ runId: "run-ready" }));
    expect(agentMessage).not.toHaveBeenCalledWith("approve", expect.anything());
    expect(agentMessage).not.toHaveBeenCalledWith("apply", expect.anything());
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("opens the latest run from a safe next-step reply without advancing gates", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "next_step",
      ok: true,
      reply: "Run run-ready is waiting for explicit plan approval. Open that run before taking any gated action from a stateless client.",
      next_actions: ["open latest run", "approve_and_run", "status", "events", "readiness"],
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        safe_actions: ["open_run", "status", "events"],
        next_actions: ["approve_and_run", "status", "events", "artifact"]
      },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          safe: true,
          reason: "Open the latest Patchbay run before choosing any gated action."
        },
        {
          id: "open_plan",
          label: "Open plan",
          kind: "diagnostic_tab",
          tab: "Artifacts",
          safe: true,
          reason: "Review PLAN.md before giving explicit approval."
        },
        {
          id: "open_readiness",
          label: "Open readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Run read-only setup diagnostics."
        }
      ],
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "what should I do next?{enter}");

    expect(await screen.findByText(/waiting for explicit plan approval/i)).toBeVisible();
    await userEvent.click(await screen.findByRole("button", { name: /open latest run/i }));

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready"));
    expect(agentMessage).toHaveBeenCalledWith("what should I do next?", { include: { plan: true }, background: true });
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("opens the latest run from a gate-status reply without advancing gates", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "gate_status",
      ok: true,
      reply: "Run run-ready is blocked by 4 gate checks: Plan approval: Plan has not been explicitly approved.",
      next_actions: ["open latest run", "status", "events", "readiness"],
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        safe_actions: ["open_run", "status", "events"],
        gate_diagnosis: { status: "PLANNED", ready_to_apply: false }
      },
      gate_diagnosis: {
        status: "PLANNED",
        ready_to_apply: false,
        blockers: [{ key: "approval", label: "Plan approval", ok: false, detail: "Plan has not been explicitly approved." }],
        checks: [
          { key: "approval", label: "Plan approval", ok: false, status: "pending", detail: "Plan has not been explicitly approved." },
          { key: "tests", label: "Tests", ok: false, status: "NOT_RUN", detail: "Tests are not passing yet." },
          { key: "review", label: "Review", ok: false, status: "pending", detail: "Review has not returned PASS." },
          { key: "apply", label: "Apply gate", ok: false, status: "blocked", detail: "Apply is blocked until tests pass and review returns PASS." }
        ]
      },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          safe: true,
          reason: "Open the latest Patchbay run before choosing any gated action."
        },
        {
          id: "open_trace",
          label: "Open activity",
          kind: "diagnostic_tab",
          tab: "Trace",
          safe: true,
          reason: "Inspect event and provider activity for gate evidence."
        }
      ],
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "what is blocking apply?{enter}");

    expect(await screen.findByText(/blocked by 4 gate checks/i)).toBeVisible();
    expect(screen.getByLabelText("Gate diagnosis")).toBeVisible();
    expect(screen.getByText("门禁诊断")).toBeVisible();
    expect(screen.getByText("Apply 仍被 1 项检查阻塞。")).toBeVisible();
    expect(screen.getByText("Plan approval")).toBeVisible();
    expect(screen.getByText("Apply gate")).toBeVisible();
    await userEvent.click(await screen.findByRole("button", { name: /open latest run/i }));

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready"));
    expect(agentMessage).toHaveBeenCalledWith("what is blocking apply?", { include: { plan: true }, background: true });
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("renders run-bound gate diagnosis as a local Agent reply without advancing gates", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "gate_status",
      ok: true,
      reply: "Run run-ready is through the technical gates; apply still requires explicit confirmation.",
      gate_diagnosis: {
        status: "REVIEWED_PASS",
        ready_to_apply: true,
        blockers: [],
        checks: [
          { key: "approval", label: "Plan approval", ok: true, status: "done", detail: "Plan approval is recorded." },
          { key: "tests", label: "Tests", ok: true, status: "PASS", detail: "Tests passed." },
          { key: "review", label: "Review", ok: true, status: "PASS", detail: "Review passed." },
          { key: "apply", label: "Apply gate", ok: true, status: "ready", detail: "Apply can proceed with explicit confirmation." }
        ]
      },
      actions: [
        {
          id: "open_diff",
          label: "Open diff",
          kind: "diagnostic_tab",
          tab: "Diff",
          safe: true,
          reason: "Inspect the patch and evidence related to the apply gate."
        }
      ]
    });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "why is apply blocked");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("why is apply blocked", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    expect(await screen.findByText(/through the technical gates/i)).toBeVisible();
    expect(screen.getByLabelText("Gate diagnosis")).toBeVisible();
    expect(screen.getByText("所有技术门禁已通过；apply 仍需要显式确认。")).toBeVisible();
    expect(screen.getByText("Apply gate")).toBeVisible();
    expect(screen.getByRole("tab", { name: "差异" })).toHaveAttribute("aria-selected", "true");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("sends selected-run economy prompts to Agent instead of treating apply as a phase command", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "profile_apply",
      ok: true,
      reply: "Economy routing profile applied."
    });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "apply economy profile");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("apply economy profile", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    expect(await screen.findByText("Economy routing profile applied.")).toBeVisible();
    expect(screen.queryByRole("dialog", { name: "确认应用补丁" })).not.toBeInTheDocument();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("uses self-contained structured open-run actions without fallback run references", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "runs",
      ok: true,
      reply: "Latest Patchbay run is available.",
      next_actions: ["readiness"],
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          tab: "Diff",
          safe: true,
          reason: "Open the latest Patchbay run without advancing any gate."
        }
      ],
      runs: { count: 1, runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "status{enter}");

    await userEvent.click(await screen.findByRole("button", { name: /open latest run/i }));

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready"));
    expect(screen.getByText("diff --git a/web b/web")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("runs local setup from the empty state and exposes readiness immediately", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay setup completed.",
      setup: {
        doctor: {
          ok: true,
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    expect(screen.getByRole("button", { name: "运行 setup" })).toBeVisible();
    expect(screen.getByRole("button", { name: "就绪" })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "运行 setup" }));
    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup"));
    expect(await screen.findByText("Patchbay setup completed.")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "就绪" }));
    expect(await screen.findByText("环境就绪")).toBeVisible();
  });

  it("runs host-aware setup from the empty state and shows MCP guidance", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay setup completed with follow-up steps.",
      setup_host: "claude-desktop",
      setup: {
        ok: true,
        root: "C:/repo",
        mcp: {
          host: "claude-desktop",
          command: "claude mcp add patchbay -- python scripts/patchbay_mcp_server.py",
          executed: false
        },
        doctor: {
          ok: true,
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
          next_actions: []
        },
        next_actions: ["Register the MCP server with: claude mcp add patchbay -- python scripts/patchbay_mcp_server.py"]
      },
      actions: [
        {
          id: "register_mcp",
          label: "Register MCP",
          kind: "command",
          command: "claude mcp add patchbay -- python scripts/patchbay_mcp_server.py",
          safe: true,
          reason: "Copy the MCP registration command for Claude Desktop."
        }
      ]
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "Setup Claude Desktop" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup for claude-desktop"));
    const setupResult = await screen.findByLabelText("Setup result");
    expect(within(setupResult).getByText("Claude Desktop")).toBeVisible();
    expect(within(setupResult).getByText("claude mcp add patchbay -- python scripts/patchbay_mcp_server.py")).toBeVisible();
    expect(within(setupResult).getByText("Register the MCP server with: claude mcp add patchbay -- python scripts/patchbay_mcp_server.py")).toBeVisible();
    await userEvent.click(within(setupResult).getByRole("button", { name: "Copy command MCP registration" }));
    expect(writeText).toHaveBeenCalledWith("claude mcp add patchbay -- python scripts/patchbay_mcp_server.py");
    expect(within(setupResult).getByRole("button", { name: "Copy command MCP registration" })).toHaveTextContent("Copied");
    const commandActions = screen.getByLabelText("Agent command actions");
    await userEvent.click(within(commandActions).getByRole("button", { name: "Copy command Register MCP" }));
    expect(writeText).toHaveBeenCalledWith("claude mcp add patchbay -- python scripts/patchbay_mcp_server.py");
    expect(within(commandActions).getByRole("button", { name: "Copy command Register MCP" })).toHaveTextContent("Copied");
  });

  it("runs local setup from the readiness panel without creating a run", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay setup completed.",
      setup: {
        doctor: {
          ok: true,
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    expect(await screen.findByText("需要处理")).toBeVisible();
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.click(within(details).getByRole("button", { name: "运行 setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup"));
    expect(await screen.findByText("环境就绪")).toBeVisible();
    expect(client.getStatus).not.toHaveBeenCalled();
  });

  it("runs host-aware setup from the readiness panel without creating a run", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay setup completed.",
      setup_host: "gemini",
      setup: {
        doctor: {
          ok: true,
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.click(within(details).getByRole("button", { name: "Setup Gemini" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("install patchbay for gemini"));
    expect(await screen.findByText("环境就绪")).toBeVisible();
    expect(client.getStatus).not.toHaveBeenCalled();
  });

  it("refreshes readiness for the selected MCP host and keeps setup host-aware", async () => {
    const getDoctor = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        host: "codex",
        root: "C:/repo",
        checks: { repo: { ok: true }, mcp: { ok: true, skipped: true } },
        next_actions: []
      })
      .mockResolvedValueOnce({
        ok: false,
        host: "claude-desktop",
        root: "C:/repo",
        checks: { repo: { ok: true }, mcp: { ok: false } },
        next_actions: ["Run `patchbay mcp doctor --json`; then re-run `patchbay mcp install claude-desktop` if tools are missing."],
        actions: [
          {
            id: "install_mcp",
            label: "Register MCP",
            kind: "command",
            command: "patchbay mcp install claude-desktop",
            host: "claude-desktop",
            safe: true,
            reason: "Register the target host."
          },
          {
            id: "run_setup",
            label: "Run setup",
            kind: "local_agent",
            message: "patchbay setup for claude-desktop",
            host: "claude-desktop",
            safe: true,
            reason: "Run host setup."
          }
        ]
      });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay setup completed.",
      setup_host: "claude-desktop",
      setup: {
        doctor: {
          ok: true,
          host: "claude-desktop",
          root: "C:/repo",
          checks: { repo: { ok: true }, mcp: { ok: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor,
      agentMessage
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex" }));
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getAllByRole("tab")[1]);
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.selectOptions(within(details).getByLabelText("MCP host"), "claude-desktop");

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "claude-desktop" }));
    expect(await within(details).findByText("patchbay mcp install claude-desktop")).toBeVisible();
    await userEvent.click(within(details).getByRole("button", { name: "Run setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup for claude-desktop"));
    expect(within(details).getByText("环境就绪")).toBeVisible();
    expect(within(details).getAllByText(/Claude Desktop/).length).toBeGreaterThan(0);
  });

  it("shows non-blocking doctor recommendations in readiness", async () => {
    const applyConfigProfile = vi.fn().mockResolvedValue({
      profile: "economy",
      status: {
        profile: "economy",
        economy: {
          matches: true,
          write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
          fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }
        },
        phase_strategy: {
          plan: { provider: "claude_cli", model: "opus", tier: "supervision", reason: "Use a stronger planner." },
          write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", tier: "economy", economy_route: true },
          fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", tier: "economy", economy_route: true },
          review: { provider: "codex_cli", model: "gpt-5", tier: "supervision", reason: "Use a stronger reviewer." }
        }
      },
      next_actions: ["readiness", "start"],
      actions: [
        {
          id: "open_readiness",
          label: "Open readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Inspect setup and resolved write/fix routing."
        },
        {
          id: "start_new_task",
          label: "Start new task",
          kind: "focus_composer",
          safe: true,
          reason: "Start a new task."
        }
      ]
    });
    const getDoctor = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        next_actions: [],
        recommendations: [
          "Run `patchbay config profile apply economy` to route write/fix implementation work to Reasonix/DeepSeek."
        ],
        actions: [
          {
            id: "apply_economy_profile",
            label: "Apply economy profile",
            kind: "local_agent",
            message: "apply economy profile",
            safe: true,
            reason: "Route high-volume write/fix work to Reasonix/DeepSeek."
          }
        ]
      })
      .mockResolvedValue({
        ok: true,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        next_actions: [],
        recommendations: []
      });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor,
      applyConfigProfile
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));

    expect(await screen.findByText("建议")).toBeVisible();
    expect(screen.getByText(/patchbay config profile apply economy/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Apply economy profile" }));

    await waitFor(() => expect(applyConfigProfile).toHaveBeenCalledWith("economy"));
    expect(await screen.findByText("Economy routing profile applied.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Open readiness" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Start new task" })).toBeVisible();
    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getByText("经济路由已启用")).toBeVisible();
    expect(within(routingResult).getAllByText("reasonix_cli / deepseek-v4-pro")).toHaveLength(2);
    expect(client.getConfig).toHaveBeenCalled();
  });

  it("shows Reasonix command readiness without offering economy reapply", async () => {
    const applyConfigProfile = vi.fn();
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "reasonix_command_configure",
      ok: true,
      reply: "Reasonix command configured."
    });
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
      next_actions: [],
      recommendations: ["Set `commands.reasonix` so the Reasonix/DeepSeek write/fix economy route can actually execute."],
      actions: [
        {
          id: "configure_reasonix_command",
          label: "Configure Reasonix",
          kind: "local_agent",
          message: "configure reasonix command",
          command: "patchbay config --set-key commands.reasonix --set-value reasonix",
          safe: true,
          reason: "Set the Reasonix executable."
        }
      ]
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage,
      getDoctor,
      applyConfigProfile
    });

    render(<Workbench client={client} />);

    await screen.findByText("Patchbay Agent");
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getAllByRole("tab")[1]);

    expect((await screen.findAllByText(/commands.reasonix/)).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Configure Reasonix" }));
    expect(agentMessage).toHaveBeenCalledWith("configure reasonix command");
    expect(screen.queryByRole("button", { name: "Apply economy profile" })).not.toBeInTheDocument();
    expect(applyConfigProfile).not.toHaveBeenCalled();
  });

  it("shows active economy routing evidence in readiness", async () => {
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: vi.fn().mockResolvedValue({
        ok: true,
        root: "C:/repo",
        checks: {
          repo: { ok: true },
          skill: { ok: true },
          config: {
            ok: true,
            profile: {
              profile: "economy",
              economy: {
                matches: true,
                intent: "High-volume write/fix work runs on the low-cost Reasonix/DeepSeek route.",
                write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
                fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }
              },
              phase_strategy: {
                plan: { provider: "claude_cli", model: "opus", tier: "supervision", reason: "Use a stronger planner." },
                write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", tier: "economy", economy_route: true },
                fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", tier: "economy", economy_route: true },
                review: { provider: "codex_cli", model: "gpt-5", tier: "supervision", reason: "Use a stronger reviewer." }
              }
            }
          }
        },
        next_actions: [],
        recommendations: []
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));

    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(await within(details).findByText("路由")).toBeVisible();
    expect(within(details).getByText("经济路由已启用")).toBeVisible();
    expect(within(details).getAllByText("实现")).toHaveLength(2);
    expect(within(details).getAllByText("修复")).toHaveLength(2);
    expect(within(details).getAllByText("reasonix_cli / deepseek-v4-pro")).toHaveLength(4);
    expect(within(details).getByText("四阶段路由")).toBeVisible();
    expect(within(details).getAllByText("经济")).toHaveLength(2);
    expect(within(details).getAllByText("监督")).toHaveLength(2);
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

  it("surfaces failed run recovery guidance without executing a phase action", async () => {
    const guidance = "Ask the planner to emit valid JSON inside the sentinel block.";
    const failedContext: HandoffContext = {
      ...plannedContext,
      run_id: "run-failed",
      status: "FAILED",
      current_phase: "plan",
      next_actions: [],
      timeline: [],
      agent_activity: {
        ...plannedContext.agent_activity!,
        headline: "Patchbay Agent 在规划阶段遇到错误。",
        tone: "failed",
        current_step: {
          phase: "plan",
          label: "规划",
          status: "FAILED",
          status_label: "失败",
          summary: "Planner JSON could not be parsed: Expecting value"
        },
        next_action: null,
        conversation_state: {
          task: "Bad planner output",
          status: "FAILED",
          status_label: "失败",
          phase: "plan",
          phase_label: "规划",
          tone: "failed",
          next_step: guidance,
          composer_placeholder: "输入“修复”或打开诊断查看错误",
          suggestions: []
        },
        messages: []
      }
    };
    const runAction = vi.fn().mockResolvedValue({ ok: true });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({
        runs: [{ run_id: "run-failed", task: "Bad planner output", status: "FAILED" }]
      }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-failed",
        task: "Bad planner output",
        status: "FAILED",
        current_phase: "plan",
        error: "Planner JSON could not be parsed: Expecting value",
        suggested_next_action: guidance,
        failure_recovery: {
          stage: "plan",
          error: "Planner JSON could not be parsed: Expecting value",
          suggested_next_action: guidance,
          safe_actions: ["status", "events", "artifact", "diff", "new_run"],
          actions: [
            {
              id: "inspect_events",
              label: "Inspect events",
              kind: "diagnostic_tab",
              tab: "Trace",
              safe: true,
              reason: "Open event timeline."
            },
            {
              id: "inspect_artifacts",
              label: "Inspect artifacts",
              kind: "diagnostic_tab",
              tab: "Artifacts",
              safe: true,
              reason: "Open failed artifacts."
            },
            {
              id: "start_new_task",
              label: "Start replacement task",
              kind: "focus_composer",
              safe: true,
              reason: "Start over with a narrower task."
            }
          ],
          artifacts: ["PLAN.md", "plan.json", "events.jsonl"],
          summary: "Run failed in plan; inspect PLAN.md, plan.json, events.jsonl before taking another action."
        },
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: [],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue(failedContext),
      runAction
    });

    render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Bad planner output" })).toBeInTheDocument();
    expect(await screen.findByText("Patchbay Agent 在规划阶段遇到错误。")).toBeInTheDocument();
    const card = screen.getByLabelText("失败恢复建议");
    expect(within(card).getByText("运行失败")).toBeVisible();
    expect(within(card).getByText("Run failed in plan; inspect PLAN.md, plan.json, events.jsonl before taking another action.")).toBeVisible();
    expect(within(card).getByText(guidance)).toBeVisible();
    expect(within(card).getByText("PLAN.md")).toBeVisible();
    expect(within(card).getByText("events.jsonl")).toBeVisible();
    expect(within(card).getByRole("button", { name: "Inspect events" })).toBeVisible();
    expect(within(card).getByRole("button", { name: "Inspect artifacts" })).toBeVisible();
    expect(within(card).getByRole("button", { name: "Start replacement task" })).toBeVisible();
    expect(within(card).queryByText("当前没有可执行动作。")).not.toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: /查看诊断/ }));

    expect(runAction).not.toHaveBeenCalled();

    await userEvent.click(within(card).getByRole("button", { name: "Inspect artifacts" }));
    expect(screen.getAllByRole("tab").some((tab) => tab.getAttribute("aria-selected") === "true")).toBe(true);

    await userEvent.click(within(card).getByRole("button", { name: "Start replacement task" }));
    expect(screen.queryByRole("heading", { name: "Bad planner output" })).not.toBeInTheDocument();
    expect(runAction).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "诊断" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("tab", { name: "活动" })).toHaveAttribute("aria-selected", "true");
  });
});
