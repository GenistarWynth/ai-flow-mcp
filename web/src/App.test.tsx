import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Workbench } from "./App";
import type { BackgroundJob, HandoffContext, PatchbayClient } from "./api";

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
  it("runs structured Skill install readiness actions through the local Agent", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Codex Skill installed without MCP registration.",
      setup_host: "codex",
      setup: {
        doctor: {
          ok: true,
          host: "codex",
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage,
      getDoctor: vi.fn().mockResolvedValue({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: false } },
        next_actions: ["Run `patchbay skill install codex` so Codex can discover the Patchbay Skill."],
        actions: [
          {
            id: "install_skill",
            label: "Install Codex Skill",
            kind: "local_agent",
            message: "install Codex Skill",
            host: "codex",
            command: "patchbay skill install codex",
            safe: true,
            reason: "Install the bundled Patchbay Skill without MCP registration."
          }
        ]
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    const installButton = within(details).getByRole("button", { name: "Install Codex Skill" });
    expect(installButton).toHaveAttribute("title", "Install the bundled Patchbay Skill without MCP registration.");
    await userEvent.click(installButton);

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("install Codex Skill"));
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup");
    expect(await screen.findByText("Codex Skill installed without MCP registration.")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("copies custom economy provider command fixes from readiness", async () => {
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
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        next_actions: ["Set `providers.cheap_writer.command` before write/fix phases run."],
        actions: [
          {
            id: "configure_economy_provider_command",
            label: "Copy provider command",
            kind: "command",
            command: "patchbay config --set-key providers.cheap_writer.command --set-value <command>",
            safe: true,
            reason: "Copy the command for the cheap_writer economy provider into .ai/patchbay.toml."
          }
        ]
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.click(within(details).getByRole("button", { name: "Copy command Copy provider command" }));

    expect(writeText).toHaveBeenCalledWith("patchbay config --set-key providers.cheap_writer.command --set-value <command>");
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
        tier_usage: {
          economy: {
            tier: "economy",
            label: "Economy write/fix",
            phases: ["write", "fix"],
            duration_known: true,
            duration_ms: 5100,
            duration_percent: 41.3,
            phase_durations_ms: { write: 4000, fix: 1100 },
            token_usage: {
              known: true,
              input_tokens: 6200,
              output_tokens: 2100,
              cached_tokens: 0,
              total_tokens: 8300,
              token_percent: 67.5
            },
            cost: { known: true, currency: "USD", estimated_total: 0.3, cost_percent: 71.4 }
          },
          supervision: {
            tier: "supervision",
            label: "Supervision plan/review",
            phases: ["plan", "review"],
            duration_known: true,
            duration_ms: 3400,
            duration_percent: 27.6,
            phase_durations_ms: { review: 2200, plan: 1200 },
            token_usage: {
              known: true,
              input_tokens: 3000,
              output_tokens: 1000,
              cached_tokens: 0,
              total_tokens: 4000,
              token_percent: 32.5
            },
            cost: { known: true, currency: "USD", estimated_total: 0.12, cost_percent: 28.6 }
          }
        },
        efficiency_summary: {
          status: "verified_economy",
          routing_status: "healthy",
          usage_known: { tokens: true, cost: true, duration: true },
          economy_share: {
            token_percent: 67.5,
            total_tokens: 8300,
            cost_percent: 71.4,
            estimated_cost: 0.3,
            currency: "USD",
            duration_percent: 41.3,
            duration_ms: 5100
          },
          coverage: {
            required_phases: ["write", "fix"],
            required_total: 2,
            configured_economy_total: 2,
            observed_total: 2,
            observed_economy_total: 2,
            observed_other_total: 0,
            observed_economy_ratio: 1,
            observed_economy_percent: 100,
            complete: true,
            label: "2/2 economy phases observed"
          },
          summary: "Economy write/fix route is verified with 8300 tokens / 67.5%, USD 0.3 / 71.4%, 5100 ms / 41.3%.",
          recommendation: "Keep simple write/fix work on the low-cost model."
        },
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
    expect(screen.getByText("经济层 8.3k tok / 67.5% | USD 0.3 / 71.4% | 5.1s / 41.3%")).toBeVisible();
    expect(screen.getByText("监督层 4.0k tok / 32.5% | USD 0.12 / 28.6% | 3.4s / 27.6%")).toBeVisible();
    expect(screen.getByText("Economy route configured; observed write, fix not observed yet.")).toBeVisible();
    expect(screen.getByText("Verified economy")).toBeVisible();
    expect(screen.getByText("Economy write/fix route is verified with 8300 tokens / 67.5%, USD 0.3 / 71.4%, 5100 ms / 41.3%.")).toBeVisible();
    expect(screen.getByText("economy tokens 8.3k / 67.5%")).toBeVisible();
    expect(screen.getByText("economy cost USD 0.3 / 71.4%")).toBeVisible();
    expect(screen.getByText("economy time 5.1s / 41.3%")).toBeVisible();
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

  it("configures custom provider command health actions from metrics", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "custom_provider_command_configure",
      ok: true,
      reply: "Custom economy provider command configured."
    });
    const command = "patchbay config --set-key providers.cheap_writer.command --set-value <command>";
    const commandContext: HandoffContext = {
      ...readyContext,
      run_metrics: {
        ...readyContext.run_metrics!,
        routing_evidence: {
          economy_configured: true,
          economy_command_ready: false,
          command_not_ready_phases: ["write", "fix"],
          coverage: { observed_economy_percent: 0, observed_economy_total: 0, required_total: 2 },
          summary: "Economy route is configured, but write/fix cannot execute because the Cheap writer command is not ready.",
          phases: {
            write: {
              configured: { provider: "cheap_writer", model: "cheap-model" },
              configured_economy: true,
              command_status: { required: true, ready: false, status: "not_found", source: "providers.cheap_writer.command" }
            },
            fix: {
              configured: { provider: "cheap_writer", model: "cheap-model" },
              configured_economy: true,
              command_status: { required: true, ready: false, status: "not_found", source: "providers.cheap_writer.command" }
            }
          },
          economy_health: {
            status: "command_not_ready",
            severity: "warning",
            configured: true,
            target: { provider: "cheap_writer", model: "cheap-model", label: "Cheap writer" },
            required_phases: ["write", "fix"],
            missing_config_phases: [],
            command_not_ready_phases: ["write", "fix"],
            drift_phases: [],
            missing_evidence: ["write", "fix"],
            observed_economy_phases: [],
            summary: "Economy route is configured, but write/fix cannot execute because the Cheap writer command is not ready.",
            recommendation: "Fix the configured Cheap writer provider command.",
            next_action: "inspect_economy_provider_command"
          },
          actions: [
            {
              id: "inspect_economy_provider_command",
              label: "Inspect provider command",
              kind: "local_agent",
              message: "readiness",
              safe: true,
              reason: "Open readiness to inspect the configured Cheap writer economy provider command."
            },
            {
              id: "configure_economy_provider_command",
              label: "Copy provider command",
              kind: "command",
              command,
              safe: true,
              reason: "Copy the command for the Cheap writer economy provider into .ai/patchbay.toml."
            }
          ]
        }
      },
      agent_activity: {
        ...readyContext.agent_activity!,
        health_cards: []
      }
    };
    const client = createClient({
      agentMessage,
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
    const details = screen.getAllByRole("complementary")[1];
    expect(within(details).getByLabelText("Provider command path")).toBeVisible();
    await userEvent.click(within(details).getByRole("button", { name: "Copy command Copy provider command" }));
    await userEvent.type(within(details).getByLabelText("Provider command path"), "C:/Program Files/DeepSeek/deepseek-writer.cmd");
    await userEvent.click(within(details).getByRole("button", { name: "Configure" }));

    expect(writeText).toHaveBeenCalledWith(command);
    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith(
        'patchbay config --set-key providers.cheap_writer.command --set-value "C:/Program Files/DeepSeek/deepseek-writer.cmd"'
      )
    );
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

  it("configures an explicit custom provider path from the readiness panel", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "custom_provider_command_configure",
      ok: true,
      reply: "Custom economy provider command configured."
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
          id: "configure_economy_provider_command",
          label: "Copy provider command",
          kind: "command",
          command: "patchbay config --set-key providers.cheap_writer.command --set-value <command>",
          safe: true,
          reason: "Copy the command for the cheap_writer economy provider into .ai/patchbay.toml."
        }
      ]
    });
    const client = createClient({ agentMessage, getDoctor });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getAllByRole("complementary")[1];
    await userEvent.type(within(details).getByLabelText("Provider command path"), "C:/Tools/deepseek-writer.cmd");
    await userEvent.click(within(details).getByRole("button", { name: "Configure" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("patchbay config --set-key providers.cheap_writer.command --set-value C:/Tools/deepseek-writer.cmd")
    );
    expect(client.applyConfigProfile).not.toHaveBeenCalled();
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("runs generic structured readiness actions without advancing gates", async () => {
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      root: "C:/repo",
      checks: {
        repo: { ok: true },
        config: { ok: true },
        mcp: { ok: true, skipped: true },
        skill: { ok: true }
      },
      actions: [
        {
          id: "inspect_readiness_trace",
          label: "Inspect readiness trace",
          kind: "diagnostic_tab",
          tab: "Trace",
          safe: true,
          reason: "Open local readiness timeline."
        },
        {
          id: "open_fix_run",
          label: "Open fix run",
          kind: "open_run",
          run_id: "run-fix",
          tab: "Log",
          safe: true,
          reason: "Open the run that needs repair."
        },
        {
          id: "start_new_task",
          label: "Start replacement task",
          kind: "focus_composer",
          safe: true,
          reason: "Start over with a narrower task."
        }
      ]
    });
    const getStatus = vi.fn().mockImplementation((runId: string) =>
      Promise.resolve(
        runId === "run-fix"
          ? {
              run_id: "run-fix",
              task: "Needs fix",
              status: "REVIEWED_CHANGES_REQUESTED",
              current_phase: "fix",
              gate_state: { approved: true, tests_passed: true, review_result: "CHANGES_REQUESTED", ready_to_apply: false },
              next_commands: ["fix"],
              artifacts: ["writer.log"],
              effective_phase_providers: {}
            }
          : {
              run_id: "run-ready",
              task: "Ship dashboard",
              status: "REVIEWED_PASS",
              current_phase: "apply",
              tests_passed: true,
              review_result: "PASS",
              gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
              next_commands: ["apply"],
              artifacts: ["PLAN.md"],
              effective_phase_providers: {}
            }
      )
    );
    const getContext = vi.fn().mockImplementation((runId: string) =>
      Promise.resolve(
        runId === "run-fix"
          ? {
              ...plannedContext,
              run_id: "run-fix",
              status: "REVIEWED_CHANGES_REQUESTED",
              current_phase: "fix",
              agent_activity: {
                ...plannedContext.agent_activity,
                conversation_state: {
                  ...plannedContext.agent_activity?.conversation_state,
                  task: "Needs fix",
                  status: "REVIEWED_CHANGES_REQUESTED",
                  phase: "fix"
                }
              }
            }
          : readyContext
      )
    );
    const client = createClient({ getDoctor, getStatus, getContext });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });

    await userEvent.click(within(details).getByRole("button", { name: "Inspect readiness trace" }));
    expect(screen.getByRole("tab", { name: "活动" })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    await userEvent.click(within(details).getByRole("button", { name: "Open fix run" }));
    expect(await screen.findByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "日志" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(getContext).toHaveBeenCalledWith("run-fix"));

    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    await userEvent.click(within(details).getByRole("button", { name: "Start replacement task" }));
    expect(await screen.findByRole("heading", { name: "新任务" })).toBeInTheDocument();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
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

  it("keeps start-time economy routing preview visible after selecting the new run", async () => {
    const applyConfigProfile = vi.fn().mockResolvedValue({
      profile: "economy",
      status: {
        profile: "economy",
        economy: {
          matches: true,
          write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
          fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }
        }
      },
      next_actions: ["readiness", "start"]
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValueOnce({ runs: [{ run_id: "run-preview", task: "Build routing preview", status: "PLANNED" }] })
        .mockResolvedValue({ runs: [{ run_id: "run-preview", task: "Build routing preview", status: "PLANNED" }] }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-preview",
        task: "Build routing preview",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: {},
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue({
        ...plannedContext,
        run_id: "run-preview",
        agent_activity: {
          ...plannedContext.agent_activity,
          messages: [
            ...(plannedContext.agent_activity?.messages ?? []),
            {
              id: "server-user-preview",
              kind: "user",
              timestamp: "2026-05-24T10:03:00Z",
              title: "User message",
              body: "Build routing preview"
            },
            {
              id: "server-agent-preview",
              kind: "agent",
              timestamp: "2026-05-24T10:03:01Z",
              title: "Patchbay Agent",
              body: "Plan generated. Economy routing profile is not active."
            }
          ],
          conversation_state: {
            ...plannedContext.agent_activity!.conversation_state!,
            task: "Build routing preview"
          }
        }
      }),
      agentMessage: vi.fn().mockResolvedValue({
        run_id: "run-preview",
        action: "start",
        ok: true,
        reply: "Plan generated. Economy routing profile is not active.",
        routing: {
          profile: "custom",
          economy_configured: false,
          phases: {
            write: { configured: { provider: "mock", model: "mock" }, configured_economy: false },
            fix: { configured: { provider: "mock", model: "mock" }, configured_economy: false }
          },
          summary: "Economy routing profile is not active: write mock / mock, fix mock / mock.",
          recommendation: "Run `patchbay config profile apply economy`."
        },
        actions: [
          {
            id: "apply_economy_profile",
            label: "Apply economy profile",
            kind: "local_agent",
            message: "apply economy profile",
            safe: true,
            reason: "Route high-volume write/fix work to the configured economy profile."
          }
        ]
      }),
      applyConfigProfile
    });

    const rendered = render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "Build routing preview");
    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));

    expect(await screen.findByRole("heading", { name: "Build routing preview" })).toBeInTheDocument();
    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getByText(/Economy routing profile is not active/)).toBeVisible();
    const nonEventBubbles = Array.from(rendered.container.querySelectorAll(".chat-bubble:not(.event)"));
    expect(nonEventBubbles.filter((bubble) => bubble.textContent?.includes("Build routing preview"))).toHaveLength(1);
    expect(nonEventBubbles.filter((bubble) => bubble.textContent?.includes("Plan generated. Economy routing profile is not active."))).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Apply economy profile" }));

    await waitFor(() => expect(applyConfigProfile).toHaveBeenCalledWith("economy"));
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

  it("opens latest-run read-only replies directly from the new-task composer", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "diff",
      ok: true,
      reply: "Latest run run-ready diff view.",
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
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
          reason: "Open the latest Patchbay run that supplied this read-only view."
        }
      ]
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

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "差异" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("diff --git a/web b/web")).toBeVisible();
    expect(screen.getByText("Latest run run-ready diff view.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /open latest run/i })).not.toBeInTheDocument();
    expect(agentMessage).toHaveBeenCalledWith("diff", { include: { plan: true }, background: true });
    expect(client.getStatus).toHaveBeenCalledWith("run-ready");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("opens latest-run context replies directly from the new-task composer", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "context",
      ok: true,
      reply: "Latest run run-ready handoff context.",
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        requested_view: { tab: "Overview", reason: "The prompt asked for the run handoff context." }
      },
      requested_view: { tab: "Overview", reason: "The prompt asked for the run handoff context." },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          tab: "Overview",
          safe: true,
          reason: "Open the latest Patchbay run that supplied this read-only view."
        }
      ]
    });
    const getContext = vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" });
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
      getContext
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "context{enter}");

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "状态" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Latest run run-ready handoff context.")).toBeVisible();
    expect(agentMessage).toHaveBeenCalledWith("context", { include: { plan: true }, background: true });
    expect(getContext).toHaveBeenCalledWith("run-ready");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("loads real run status when opening latest metrics replies", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "metrics",
      ok: true,
      reply: "Latest run run-ready metrics: tokens known.",
      status: {
        run_id: "run-ready",
        status: "PLANNED",
        current_phase: "plan",
        run_metrics: { token_usage: { known: true, total_tokens: 1234 } }
      },
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      run_reference: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        requested_view: { tab: "Overview", reason: "The prompt asked for latest run efficiency metrics." }
      },
      requested_view: { tab: "Overview", reason: "The prompt asked for latest run efficiency metrics." },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          tab: "Overview",
          safe: true,
          reason: "Open the latest Patchbay run that supplied these read-only metrics."
        }
      ]
    });
    const getStatus = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      task: "Approve a plan",
      status: "PLANNED",
      current_phase: "plan",
      gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
      next_commands: ["approve"],
      artifacts: [],
      effective_phase_providers: {}
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValue({ runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }] }),
      agentMessage,
      getStatus,
      getContext: vi.fn().mockResolvedValue({ ...plannedContext, run_id: "run-ready" })
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalled());
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "metrics{enter}");

    expect(await screen.findByRole("heading", { name: "Approve a plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "状态" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Latest run run-ready metrics: tokens known.")).toBeVisible();
    expect(getStatus).toHaveBeenCalledWith("run-ready");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
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

  it("renders selected-run next_action as a confirmable local reply action", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "next_step",
      ok: true,
      reply: "Run run-ready is waiting for explicit plan approval.",
      status: {
        run_id: "run-ready",
        task: "Approve a plan",
        status: "PLANNED",
        current_phase: "plan",
        gate_state: { approved: false, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["approve"],
        artifacts: [],
        effective_phase_providers: {}
      },
      context: { ...plannedContext, run_id: "run-ready" },
      next_action: {
        id: "approve_and_run",
        label: "Approve plan",
        kind: "local_agent",
        message: "approve",
        safe: false,
        reason: "Plan approval is required before write/test/review phases can run.",
        requires_confirmation: { confirmation: "plan_approved" }
      },
      actions: [
        {
          id: "open_plan",
          label: "Open plan",
          kind: "diagnostic_tab",
          tab: "Artifacts",
          safe: true,
          reason: "Review PLAN.md before approval."
        }
      ]
    });
    const client = createClient({
      agentMessage,
      listRuns: vi.fn().mockResolvedValue({
        runs: [{ run_id: "run-ready", task: "Approve a plan", status: "PLANNED" }]
      }),
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

    await screen.findByRole("heading", { name: "Approve a plan" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "what should I do next?{enter}");

    expect(await screen.findByText(/waiting for explicit plan approval/i)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Approve plan" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getAllByRole("button")[1]);

    expect(agentMessage).toHaveBeenCalledWith("approve", {
      runId: "run-ready",
      confirmation: "plan_approved",
      include: { diff: false, review: false },
      background: true
    });
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
        ],
        next_action: {
          id: "approve_and_run",
          label: "Approve plan",
          kind: "local_agent",
          message: "approve",
          safe: false,
          reason: "Plan approval is required before write/test/review phases can run.",
          requires_confirmation: { confirmation: "plan_approved" }
        }
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
    expect(screen.getByText("下一步动作")).toBeVisible();
    expect(screen.getByText("Approve plan")).toBeVisible();
    expect(screen.getByText("需要显式确认")).toBeVisible();
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
        ],
        next_action: {
          id: "apply",
          label: "Apply reviewed diff",
          kind: "local_agent",
          message: "apply",
          safe: false,
          reason: "Tests and review passed; apply still requires explicit confirmation.",
          requires_confirmation: { confirmation: "apply_approved" }
        }
      },
      actions: [
        {
          id: "open_diff",
          label: "Open diff",
          kind: "diagnostic_tab",
          tab: "Diff",
          safe: true,
          reason: "Inspect the patch and evidence related to the apply gate."
        },
        {
          id: "open_trace",
          label: "Open trace",
          kind: "diagnostic_tab",
          tab: "Trace",
          safe: true,
          reason: "Inspect the event timeline related to the apply gate."
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
    expect(screen.getAllByText("Apply reviewed diff").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText("Gate diagnosis")).toBeVisible();
    expect(screen.getByText("所有技术门禁已通过；apply 仍需要显式确认。")).toBeVisible();
    expect(screen.getByText("Apply gate")).toBeVisible();
    expect(screen.queryByRole("tab", { name: "差异" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open diff" }));
    expect(screen.getByRole("tab", { name: "差异" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("button", { name: "Apply reviewed diff" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getAllByRole("button")[1]);
    expect(agentMessage).toHaveBeenCalledWith("apply", {
      runId: "run-ready",
      confirmation: "apply_approved",
      include: { diff: true, review: true },
      background: false
    });
    expect(screen.getByRole("button", { name: "Open trace" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Open trace" }));
    expect(screen.getByRole("tab", { name: "活动" })).toHaveAttribute("aria-selected", "true");
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

  it("renders selected-run routing replies with structured cards and safe actions", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "profile_show",
      ok: true,
      reply: "Economy routing profile is not active: write mock, fix mock. Run evidence: Write/fix are not fully routed to the economy profile.",
      routing: {
        profile: "custom",
        target: { provider: "reasonix_cli", model: "deepseek-v4-pro" },
        economy_configured: false,
        economy_command_ready: null,
        summary: "Economy routing profile is not active: write mock, fix mock.",
        recommendation: "Run `patchbay config profile apply economy`.",
        phases: {
          write: { configured: { provider: "mock", model: "", command_key: "" }, configured_economy: false },
          fix: { configured: { provider: "mock", model: "", command_key: "" }, configured_economy: false }
        }
      },
      efficiency_summary: {
        status: "not_configured",
        routing_status: "not_configured",
        usage_known: { tokens: true, cost: true, duration: true },
        economy_share: {
          token_percent: 100,
          total_tokens: 200,
          cost_percent: 100,
          estimated_cost: 0.02,
          currency: "USD",
          duration_percent: 100,
          duration_ms: 900
        },
        summary: "Write/fix are not fully routed to the economy profile.",
        recommendation: "Apply the economy profile or configure a custom low-cost writer before high-volume implementation work."
      },
      actions: [
        {
          id: "apply_economy_profile",
          label: "Apply economy profile",
          kind: "local_agent",
          message: "apply economy profile",
          safe: true,
          reason: "Route high-volume write/fix work to Reasonix/DeepSeek."
        },
        {
          id: "open_readiness",
          label: "Open readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Run read-only setup diagnostics."
        }
      ]
    });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "is writer using cheap model?");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("is writer using cheap model?", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getByText("经济路由未启用")).toBeVisible();
    expect(within(routingResult).getByText("Economy routing profile is not active: write mock, fix mock.")).toBeVisible();
    expect(within(routingResult).getAllByText("mock / 默认")).toHaveLength(2);
    const efficiencyResult = await screen.findByLabelText("Efficiency summary");
    expect(within(efficiencyResult).getByText("Not configured")).toBeVisible();
    expect(within(efficiencyResult).getByText("economy tokens 200 / 100%")).toBeVisible();
    expect(within(efficiencyResult).getByText("economy cost USD 0.02 / 100%")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Apply economy profile" }));

    await waitFor(() => expect(client.applyConfigProfile).toHaveBeenCalledWith("economy"));
    expect(await screen.findByText("Economy routing profile applied.")).toBeVisible();
    expect(
      await screen.findByText("Economy routing profile is active: write reasonix_cli / deepseek-v4-pro, fix reasonix_cli / deepseek-v4-pro.")
    ).toBeVisible();
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

  it("uses run references for prose open-latest actions in selected runs", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "next_step",
      ok: true,
      reply: "Open the latest run first, then inspect the log.",
      next_actions: ["open latest run"],
      recent_run: { run_id: "run-fix", task: "Needs fix", status: "FAILED" },
      run_reference: {
        run_id: "run-fix",
        task: "Needs fix",
        status: "FAILED",
        requested_view: { tab: "Log", reason: "The prompt asked for run logs." }
      }
    });
    const fixStatus = {
      run_id: "run-fix",
      task: "Needs fix",
      status: "FAILED",
      current_phase: "fix",
      error: "writer.log shows a failure",
      gate_state: { approved: true, tests_passed: false, review_result: "CHANGES_REQUESTED", ready_to_apply: false },
      artifacts: ["writer.log", "PLAN.md"],
      next_commands: ["fix"],
      effective_phase_providers: {}
    };
    const fixContext = {
      ...plannedContext,
      run_id: "run-fix",
      status: "FAILED",
      current_phase: "fix",
      agent_activity: {
        ...plannedContext.agent_activity,
        headline: "Patchbay Agent is tracking run run-fix.",
        current_step: {
          phase: "fix",
          label: "修复",
          status: "FAILED",
          status_label: "失败",
          summary: "writer.log shows a failure"
        },
        conversation_state: {
          ...plannedContext.agent_activity?.conversation_state,
          task: "Needs fix",
          status: "FAILED",
          phase: "fix",
          next_step: "Open the latest run and inspect the log.",
          composer_placeholder: "输入“继续”或写下本地备注"
        }
      }
    } satisfies HandoffContext;
    const getStatus = vi.fn().mockImplementation((runId: string) => Promise.resolve(runId === "run-fix" ? fixStatus : {
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
      effective_phase_providers: {}
    }));
    const getContext = vi.fn().mockImplementation((runId: string) => Promise.resolve(runId === "run-fix" ? fixContext : plannedContext));
    const getArtifact = vi.fn().mockResolvedValue({ text: "writer log text" });
    const client = createClient({
      agentMessage,
      getStatus,
      getContext,
      getArtifact
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "status");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    const openLatest = await screen.findByRole("button", { name: /open latest run/i });
    await userEvent.click(openLatest);

    expect(await screen.findByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
    await waitFor(() => expect(getContext).toHaveBeenCalledWith("run-fix"));
    await waitFor(() => expect(getArtifact).toHaveBeenCalledWith("run-fix", "writer.log", { tail: 80 }));
    expect(screen.getByRole("tab", { name: "日志" })).toHaveAttribute("aria-selected", "true");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("starts a fresh thread from selected-run local Agent replies", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "You can start a replacement task.",
        actions: [
          {
            id: "start_new_task",
            label: "Start new task",
            kind: "focus_composer",
            safe: true,
            reason: "Start over with a new task."
          }
        ]
      })
      .mockResolvedValueOnce({ run_id: "run-new", status: { run_id: "run-new", status: "PLANNED" } });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const selectedRunComposer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(selectedRunComposer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Start new task" }));

    const newTaskComposer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(newTaskComposer, "Build replacement plan{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("Build replacement plan", {
        include: { plan: true },
        background: true
      })
    );
    expect(agentMessage).not.toHaveBeenCalledWith("Build replacement plan", expect.objectContaining({ runId: "run-ready" }));
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("appends selected-run status actions to the active thread", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "Status action available.",
        actions: [
          {
            id: "show_status",
            label: "Show status",
            kind: "local_agent",
            message: "status",
            safe: true,
            reason: "Show the current run status."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "status",
        ok: true,
        reply: "Current run status: reviewed pass.",
        status: {
          run_id: "run-ready",
          task: "Ship dashboard",
          status: "REVIEWED_PASS",
          current_phase: "apply",
          tests_passed: true,
          review_result: "PASS",
          gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
          next_commands: ["apply"],
          artifacts: ["PLAN.md"],
          effective_phase_providers: {}
        }
      });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Show status" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("status", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    expect(await screen.findByText("Current run status: reviewed pass.")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("honors host metadata on help setup shortcuts", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "Setup shortcuts available.",
        actions: [
          {
            id: "run_setup",
            label: "Setup Desktop via help",
            kind: "local_agent",
            message: "patchbay setup",
            host: "claude-desktop",
            safe: true,
            reason: "Run setup for Claude Desktop."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "setup",
        ok: true,
        reply: "Patchbay setup completed for Claude Desktop.",
        setup_host: "claude-desktop",
        setup: {
          doctor: {
            ok: true,
            host: "claude-desktop",
            root: "C:/repo",
            checks: { repo: { ok: true }, config: { ok: true }, mcp: { ok: true } },
            next_actions: []
          }
        }
      });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Setup Desktop via help" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup for claude-desktop"));
    expect(await screen.findByText("Patchbay setup completed for Claude Desktop.")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("preserves scoped setup action messages from local agent replies", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "Scoped setup shortcuts available.",
        actions: [
          {
            id: "install_skill_only",
            label: "Install Codex Skill",
            kind: "local_agent",
            message: "install Codex Skill",
            host: "codex",
            safe: true,
            reason: "Install the Skill without MCP registration."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "setup",
        ok: true,
        reply: "Codex Skill installed without MCP registration.",
        setup_host: "codex",
        setup: {
          doctor: {
            ok: true,
            host: "codex",
            root: "C:/repo",
            checks: { repo: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
            next_actions: []
          }
        }
      });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Install Codex Skill" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("install Codex Skill"));
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup");
    expect(await screen.findByText("Codex Skill installed without MCP registration.")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("preserves no-MCP setup action messages from local agent replies", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "Local setup shortcuts available.",
        actions: [
          {
            id: "run_local_setup",
            label: "Run local setup",
            kind: "local_agent",
            message: "patchbay setup without MCP",
            host: "codex",
            safe: true,
            reason: "Run setup without MCP registration."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "setup",
        ok: true,
        reply: "Patchbay local setup completed without MCP.",
        setup_host: "codex",
        setup: {
          doctor: {
            ok: true,
            host: "codex",
            root: "C:/repo",
            checks: { repo: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
            next_actions: []
          }
        }
      });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run local setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP"));
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup");
    expect(await screen.findByText("Patchbay local setup completed without MCP.")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("keeps readiness local-only after running local setup from an agent reply", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "Local setup shortcuts available.",
        actions: [
          {
            id: "run_local_setup",
            label: "Run local setup",
            kind: "local_agent",
            message: "patchbay setup without MCP",
            host: "codex",
            safe: true,
            reason: "Run setup without MCP registration."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "setup",
        ok: true,
        reply: "Patchbay local setup completed without MCP.",
        setup_host: "codex",
        setup: {
          doctor: {
            ok: true,
            host: "codex",
            root: "C:/repo",
            checks: { repo: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
            next_actions: []
          }
        }
      });
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "claude-desktop",
      root: "C:/repo",
      checks: { repo: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
      next_actions: []
    });
    const client = createClient({ agentMessage, getDoctor });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");
    await userEvent.click(await screen.findByRole("button", { name: "Run local setup" }));
    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP"));

    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getAllByRole("tab")[1]);
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).queryByRole("combobox", { name: "MCP host" })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(details).getByRole("combobox", { name: "Setup host" }), "claude-desktop");

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "claude-desktop", skip_mcp: true }));
  });

  it("routes no-MCP readiness replies to doctor checks instead of setup", async () => {
    const agentMessage = vi.fn().mockResolvedValueOnce({
      run_id: "run-ready",
      action: "local_mode",
      ok: true,
      reply: "Local-only mode selected.",
      actions: [
        {
          id: "open_local_readiness",
          label: "Open local readiness",
          kind: "local_agent",
          message: "readiness without MCP",
          host: "codex",
          safe: true,
          reason: "Run local-only readiness checks without MCP probing."
        }
      ]
    });
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "codex",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, mcp: { ok: true, skipped: true } },
      next_actions: []
    });
    const client = createClient({ agentMessage, getDoctor });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    const localActions = await screen.findByLabelText("Agent 建议动作");
    await userEvent.click(within(localActions).getByRole("button", { name: "Open local readiness" }));

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex", skip_mcp: true }));
    expect(screen.queryByRole("combobox", { name: "MCP host" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Setup host" })).toHaveValue("codex");
    expect(agentMessage).not.toHaveBeenCalledWith("readiness without MCP");
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup");
  });

  it("persists local-only readiness across host changes after a no-MCP reply", async () => {
    const agentMessage = vi.fn().mockResolvedValueOnce({
      run_id: "run-ready",
      action: "local_mode",
      ok: true,
      reply: "Local-only mode selected.",
      actions: [
        {
          id: "open_local_readiness",
          label: "Open local readiness",
          kind: "local_agent",
          message: "readiness without MCP",
          host: "codex",
          safe: true,
          reason: "Run local-only readiness checks without MCP probing."
        }
      ]
    });
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "codex",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, mcp: { ok: true, skipped: true } },
      next_actions: []
    });
    const client = createClient({ agentMessage, getDoctor });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");
    const localActions = await screen.findByLabelText("Agent 建议动作");
    await userEvent.click(within(localActions).getByRole("button", { name: "Open local readiness" }));
    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex", skip_mcp: true }));

    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).queryByRole("combobox", { name: "MCP host" })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(details).getByRole("combobox", { name: "Setup host" }), "claude-desktop");

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "claude-desktop", skip_mcp: true }));
  });

  it("normalizes host names in prose setup actions", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "Setup guidance available.",
        next_actions: ["patchbay setup for Claude Desktop"]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "setup",
        ok: true,
        reply: "Patchbay setup completed for Claude Desktop.",
        setup_host: "claude-desktop",
        setup: {
          doctor: {
            ok: true,
            host: "claude-desktop",
            root: "C:/repo",
            checks: { repo: { ok: true }, config: { ok: true }, mcp: { ok: true } },
            next_actions: []
          }
        }
      });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Claude Desktop" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup for claude-desktop"));
    expect(await screen.findByText("Patchbay setup completed for Claude Desktop.")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("normalizes host names in prose readiness actions", async () => {
    const getDoctor = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        host: "claude-desktop",
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, mcp: { ok: true } },
        next_actions: []
      });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "help",
      ok: true,
      reply: "Readiness guidance available.",
      next_actions: ["readiness for Claude Desktop"]
    });
    const client = createClient({ agentMessage, getDoctor });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    await userEvent.click(await screen.findByRole("button", { name: "Claude Desktop readiness" }));

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "claude-desktop" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getAllByText(/Claude Desktop/).length).toBeGreaterThan(0);
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("runs structured host readiness help actions", async () => {
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "claude-desktop",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, mcp: { ok: true } },
      next_actions: []
    });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "help",
      ok: true,
      reply: "Readiness shortcuts available.",
      actions: [
        {
          id: "readiness_claude_desktop",
          label: "Check Claude Desktop readiness",
          kind: "local_agent",
          message: "readiness for claude-desktop",
          host: "claude-desktop",
          safe: true,
          reason: "Run read-only Patchbay readiness checks for Claude Desktop MCP registration."
        }
      ]
    });
    const client = createClient({ agentMessage, getDoctor });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "help{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("help", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    const actionButton = await screen.findByRole("button", { name: "Check Claude Desktop readiness" });
    expect(actionButton).toHaveAttribute("title", "Run read-only Patchbay readiness checks for Claude Desktop MCP registration.");
    await userEvent.click(actionButton);

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "claude-desktop" }));
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("runs local-only setup from the empty state without MCP registration", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay local setup completed.",
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
    expect(screen.getByRole("button", { name: "本地 setup" })).toBeVisible();
    expect(screen.getByRole("button", { name: "就绪" })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "本地 setup" }));
    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP"));
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup");
    expect(await screen.findByText("Patchbay local setup completed.")).toBeVisible();

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

  it("runs local-only setup from the readiness panel without creating a run", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay local setup completed.",
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
    await userEvent.click(within(details).getByRole("button", { name: "本地 setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP"));
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup");
    expect(await screen.findByText("环境就绪")).toBeVisible();
    expect(client.getStatus).not.toHaveBeenCalled();
  });

  it("keeps local-only setup host-aware from the readiness panel", async () => {
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
        next_actions: []
      });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay local setup completed for Claude Desktop.",
      setup_host: "claude-desktop",
      setup: {
        doctor: {
          ok: true,
          host: "claude-desktop",
          root: "C:/repo",
          checks: { repo: { ok: true }, mcp: { ok: true, skipped: true } },
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
    await userEvent.click(within(details).getByRole("button", { name: "本地 setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP for claude-desktop"));
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup for claude-desktop");
    expect(within(details).getByText("环境就绪")).toBeVisible();
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

  it("does not mark profile routes as economy when command keys mismatch", async () => {
    const applyConfigProfile = vi.fn().mockResolvedValue({
      profile: "custom",
      status: {
        profile: "custom",
        economy: {
          matches: false,
          target: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" },
          write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "other_reasonix" },
          fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "other_reasonix" },
          command_ready: true
        },
        phase_strategy: {
          plan: { provider: "claude_cli", model: "opus", tier: "supervision", reason: "Use a stronger planner." },
          write: {
            provider: "reasonix_cli",
            model: "deepseek-v4-pro",
            command_key: "other_reasonix",
            tier: "economy",
            economy_route: false
          },
          fix: {
            provider: "reasonix_cli",
            model: "deepseek-v4-pro",
            command_key: "other_reasonix",
            tier: "economy",
            economy_route: false
          },
          review: { provider: "codex_cli", model: "gpt-5", tier: "supervision", reason: "Use a stronger reviewer." }
        }
      },
      next_actions: ["apply economy profile", "readiness"]
    });
    const getDoctor = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        next_actions: [],
        recommendations: [],
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
    await userEvent.click(await screen.findByRole("button", { name: "Apply economy profile" }));

    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getByText("经济路由未启用")).toBeVisible();
    expect(within(routingResult).getAllByText("未观测")).toHaveLength(2);
    expect(within(routingResult).queryByText("待观测")).not.toBeInTheDocument();
  });

  it("renders custom economy targets from profile status", async () => {
    const applyConfigProfile = vi.fn().mockResolvedValue({
      profile: "economy",
      status: {
        profile: "economy",
        economy: {
          matches: true,
          target: { provider: "local_writer", model: "cheap-model", label: "Local cheap writer" },
          write: { provider: "local_writer", model: "cheap-model" },
          fix: { provider: "local_writer", model: "cheap-model" },
          command_ready: true
        },
        phase_strategy: {
          plan: { provider: "claude_cli", model: "opus", tier: "supervision", reason: "Use a stronger planner." },
          write: { provider: "local_writer", model: "cheap-model", tier: "economy", economy_route: true },
          fix: { provider: "local_writer", model: "cheap-model", tier: "economy", economy_route: true },
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
        recommendations: ["Run `patchbay config profile apply economy` to route write/fix implementation work to Local cheap writer."],
        actions: [
          {
            id: "apply_economy_profile",
            label: "Apply economy profile",
            kind: "local_agent",
            message: "apply economy profile",
            safe: true,
            reason: "Route high-volume write/fix work to Local cheap writer."
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
    await userEvent.click(await screen.findByRole("button", { name: "Apply economy profile" }));

    await waitFor(() => expect(applyConfigProfile).toHaveBeenCalledWith("economy"));
    expect(await screen.findByText("Economy routing profile applied.")).toBeVisible();
    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getAllByText("local_writer / cheap-model")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Configure Reasonix" })).not.toBeInTheDocument();
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

  it("uses the alternative setup action when the next phase is blocked", async () => {
    const alternativeAction = {
      id: "configure_reasonix_command",
      label: "Configure Reasonix",
      kind: "local_agent",
      message: "configure reasonix command",
      safe: true,
      reason: "Set the Reasonix executable."
    };
    const blockedWriteContext: HandoffContext = {
      ...plannedContext,
      run_id: "run-ready",
      status: "APPROVED",
      current_phase: "write",
      next_actions: [
        {
          name: "write",
          safe: false,
          tool: "patchbay_write",
          requires_human_confirmation: false,
          reason: "write is blocked because commands.reasonix is not ready.",
          alternative_action: alternativeAction
        }
      ],
      agent_activity: {
        ...plannedContext.agent_activity!,
        next_action: {
          name: "write",
          label: "Start write",
          safe: false,
          tool: "patchbay_write",
          requires_human_confirmation: false,
          reason: "write is blocked because commands.reasonix is not ready.",
          alternative_action: alternativeAction
        },
        conversation_state: {
          ...plannedContext.agent_activity!.conversation_state!,
          suggestions: [
            {
              id: "write",
              label: "Start write",
              action: "write",
              safe: false,
              tool: "patchbay_write",
              requires_human_confirmation: false,
              reason: "write is blocked because commands.reasonix is not ready.",
              alternative_action: alternativeAction
            }
          ]
        },
        health_cards: []
      }
    };
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({
        runs: [{ run_id: "run-ready", task: "Blocked economy route", status: "APPROVED" }]
      }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Blocked economy route",
        status: "APPROVED",
        current_phase: "write",
        gate_state: { approved: true, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: ["write"],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue(blockedWriteContext)
    });

    render(<Workbench client={client} />);

    await screen.findByText("write is blocked because commands.reasonix is not ready.");
    await userEvent.click(screen.getByRole("button", { name: "Configure Reasonix" }));

    await waitFor(() => expect(client.agentMessage).toHaveBeenCalledWith("configure reasonix command"));
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
    const backgroundJob: BackgroundJob = {
      active: true,
      status: "running",
      kind: "agent",
      phase: "write",
      action: "continue",
      pid: 4321,
      duration_ms: 1500,
      started_at: "2026-05-24T10:03:00Z",
      actions: [
        {
          id: "open_background_run",
          label: "Open background run",
          kind: "open_run",
          run_id: "run-ready",
          tab: "Overview",
          safe: true,
          reason: "Open the run that owns this background job without advancing any gate."
        },
        {
          id: "open_trace",
          label: "Open activity",
          kind: "diagnostic_tab",
          run_id: "run-ready",
          tab: "Trace",
          safe: true,
          reason: "Inspect queued/running background agent events and provider activity."
        },
        {
          id: "poll_status",
          label: "Poll status",
          kind: "local_agent",
          run_id: "run-ready",
          message: "status",
          safe: true,
          reason: "Refresh this background run without approving, continuing, or applying changes."
        },
        {
          id: "poll_context",
          label: "Poll context",
          kind: "local_agent",
          run_id: "run-ready",
          message: "context",
          safe: true,
          reason: "Refresh the latest handoff context for this background run."
        },
        {
          id: "poll_events",
          label: "Poll events",
          kind: "local_agent",
          run_id: "run-ready",
          message: "events",
          safe: true,
          reason: "Read the background run event stream without advancing any phase."
        }
      ]
    };
    const runningContext: HandoffContext = {
      ...plannedContext,
      run_id: "run-ready",
      status: "RUNNING",
      current_phase: "write",
      background_job: backgroundJob,
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
        background_job: backgroundJob,
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
        runs: [{ run_id: "run-ready", task: "Background implementation", status: "APPROVED", background_job: backgroundJob }]
      }),
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Background implementation",
        status: "RUNNING",
        current_phase: "write",
        background_job: backgroundJob,
        gate_state: { approved: true, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: [],
        artifacts: [],
        effective_phase_providers: {}
      }),
      getContext: vi.fn().mockResolvedValue(runningContext)
    });

    render(<Workbench client={client} />);

    expect(await screen.findByText("Patchbay Agent 正在执行实现阶段。")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Background job status")).toHaveLength(2);
    expect(screen.getAllByText(/后台运行中/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/pid 4321/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Open background run" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open activity" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Poll status" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Poll context" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Poll events" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open activity" }));
    expect(screen.getByRole("tab", { selected: true })).toBeInTheDocument();
    const statusCalls = vi.mocked(client.getStatus).mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Poll status" }));
    await waitFor(() => expect(client.getStatus).toHaveBeenCalledTimes(statusCalls + 1));
    const contextCalls = vi.mocked(client.getContext).mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Poll context" }));
    await waitFor(() => expect(client.getContext).toHaveBeenCalledTimes(contextCalls + 1));
    expect(screen.getByRole("heading", { name: "Background implementation" })).toBeInTheDocument();
    expect(screen.getAllByText(/1.5s/).length).toBeGreaterThan(0);
    expect(screen.getByText("后台任务运行中")).toBeInTheDocument();
    expect(screen.getByText("运行中 · 实现")).toBeInTheDocument();
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toBeDisabled();
    expect(screen.getByRole("button", { name: "发送消息" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /开始实现/ })).toBeDisabled();
  });

  it("auto-refreshes active background jobs until completion", async () => {
    const runningJob: BackgroundJob = {
      active: true,
      status: "running",
      kind: "agent",
      phase: "write",
      action: "continue",
      pid: 4321
    };
    const finishedJob: BackgroundJob = {
      ...runningJob,
      active: false,
      status: "finished",
      exit_code: 0,
      duration_ms: 2400,
      finished_at: "2026-05-24T10:03:02Z"
    };
    const runningContext: HandoffContext = {
      ...plannedContext,
      run_id: "run-ready",
      status: "RUNNING",
      current_phase: "write",
      background_job: runningJob,
      timeline: [],
      cursors: { event: 1, trace: 0 },
      agent_activity: {
        ...plannedContext.agent_activity!,
        background_job: runningJob,
        conversation_state: {
          ...plannedContext.agent_activity!.conversation_state!,
          task: "Background implementation",
          status: "RUNNING",
          phase: "write",
          suggestions: []
        }
      }
    };
    const finishedContext: HandoffContext = {
      ...readyContext,
      run_id: "run-ready",
      status: "REVIEWED_PASS",
      current_phase: "apply",
      background_job: finishedJob,
      timeline: [
        {
          source: "event",
          index: 1,
          timestamp: "2026-05-24T10:03:02Z",
          phase: "agent",
          action: "success",
          status: "SUCCESS",
          detail: "Background agent turn finished."
        }
      ],
      cursors: { event: 2, trace: 0 },
      agent_activity: {
        ...readyContext.agent_activity!,
        background_job: finishedJob,
        conversation_state: {
          ...readyContext.agent_activity!.conversation_state!,
          task: "Background implementation"
        }
      }
    };
    const statusRunning = {
      run_id: "run-ready",
      task: "Background implementation",
      status: "RUNNING",
      current_phase: "write",
      background_job: runningJob,
      gate_state: { approved: true, tests_passed: false, review_result: null, ready_to_apply: false },
      next_commands: [],
      artifacts: [],
      effective_phase_providers: {}
    };
    const statusFinished = {
      run_id: "run-ready",
      task: "Background implementation",
      status: "REVIEWED_PASS",
      current_phase: "apply",
      background_job: finishedJob,
      gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
      tests_passed: true,
      review_result: "PASS",
      next_commands: ["apply"],
      artifacts: ["REVIEW.md"],
      effective_phase_providers: {}
    };
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({
          runs: [{ run_id: "run-ready", task: "Background implementation", status: "RUNNING", background_job: runningJob }]
        })
        .mockResolvedValue({
          runs: [{ run_id: "run-ready", task: "Background implementation", status: "REVIEWED_PASS", background_job: finishedJob }]
        }),
      getStatus: vi.fn().mockResolvedValueOnce(statusRunning).mockResolvedValue(statusFinished),
      getContext: vi.fn().mockResolvedValueOnce(runningContext).mockResolvedValue(finishedContext)
    });

    render(<Workbench client={client} pollIntervalMs={20} />);

    expect(await screen.findByRole("heading", { name: "Background implementation" })).toBeInTheDocument();
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready", { since_event: 1 }));
    await waitFor(() => expect(client.getStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(client.listRuns).toHaveBeenCalledTimes(2));
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
