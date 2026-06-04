import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
      count: 2,
      runs: [
        {
          run_id: "run-ready",
          task: "Ship dashboard",
          status: "REVIEWED_PASS",
          updated_at: "2026-05-24T10:00:00Z",
          current_phase: "apply",
          next_commands: ["apply"],
          gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
          run_metrics: {
            ...readyContext.run_metrics!,
            routing_evidence: {
              economy_health: {
                status: "healthy",
                severity: "ok",
                summary: "Economy route is configured and observed for write/fix.",
                target: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", label: "Reasonix/DeepSeek" }
              },
              coverage: { required_total: 2, observed_economy_total: 2, observed_economy_percent: 100 },
              phases: {
                write: { configured_economy: true, observed_economy: true },
                fix: { configured_economy: true, observed_economy: true }
              }
            },
            efficiency_summary: {
              status: "verified_economy",
              routing_status: "healthy",
              usage_known: { duration: true },
              economy_share: { duration_percent: 65, duration_ms: 8000 },
              summary: "Economy write/fix route verified by provider events."
            }
          },
          provider_trail: [{ phase: "review", provider: "codex_cli", model: "gpt-5", status: "PASS", timestamp: "2026-05-24T10:02:00Z" }],
          inbox: {
            key: "ready_to_apply",
            label: "Ready to apply",
            summary: "Tests and review passed; apply requires explicit confirmation.",
            priority: 80,
            safe: false,
            requires_confirmation: true,
            next_action: {
              id: "apply",
              label: "Apply reviewed diff",
              kind: "local_agent",
              run_id: "run-ready",
              message: "apply",
              safe: false,
              requires_confirmation: { type: "apply_approval", required_action: "apply", confirmation: "apply_approved" },
              reason: "Tests and review passed; apply still requires explicit confirmation."
            }
          }
        },
        {
          run_id: "run-fix",
          task: "Needs fix",
          status: "REVIEWED_CHANGES_REQUESTED",
          updated_at: "2026-05-24T09:00:00Z",
          current_phase: "fix",
          next_commands: ["fix"],
          gate_state: { approved: true, tests_passed: true, review_result: "CHANGES_REQUESTED", ready_to_apply: false },
          inbox: {
            key: "ready_to_continue",
            label: "Ready to continue",
            summary: "Run can advance to the next gated Patchbay phase.",
            priority: 60,
            safe: false,
            requires_confirmation: false,
            next_action: {
              id: "continue",
              label: "Continue run",
              kind: "local_agent",
              run_id: "run-fix",
              message: "continue",
              safe: false,
              reason: "Run the next Patchbay phase for this selected run."
            }
          }
        }
      ],
      inbox: {
        total: 2,
        active_count: 0,
        confirmation_required_count: 1,
        safe_action_count: 0,
        focus_run_id: "run-ready",
        summary: "2 runs; 1 need confirmation; Ready to apply: 1, Ready to continue: 1.",
        groups: [
          { key: "ready_to_apply", label: "Ready to apply", count: 1, run_ids: ["run-ready"] },
          { key: "ready_to_continue", label: "Ready to continue", count: 1, run_ids: ["run-fix"] }
        ]
      }
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
    createProvider: vi.fn().mockResolvedValue({ provider: "cheap_writer", activated_economy: true }),
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

function setDocumentVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: state
  });
}

describe("Workbench", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setDocumentVisibility("visible");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: undefined
    });
  });

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

  it("shows outdated Skill drift details in readiness", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Codex Skill updated.",
      setup_host: "codex",
      setup: {
        doctor: {
          ok: true,
          host: "codex",
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true, ready: true }, mcp: { ok: true, skipped: true } },
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
        host: "codex",
        checks: {
          repo: { ok: true },
          config: { ok: true },
          skill: {
            ok: true,
            ready: false,
            status: "outdated",
            installed: true,
            installed_matches_source: false,
            changed_installed_files: ["SKILL.md"],
            missing_installed_files: ["references/install.md"],
            extra_installed_files: ["legacy.md"],
            contract: {
              kind: "progressive-skill",
              entrypoint: "skills/patchbay/SKILL.md"
            }
          },
          mcp: { ok: true, skipped: true, note: "Skipped by web workbench." }
        },
        next_actions: ["Run `patchbay skill install codex` to update the installed Patchbay Skill from the bundled source."],
        actions: [
          {
            id: "install_skill",
            label: "Update Codex Skill",
            kind: "local_agent",
            message: "install Codex Skill",
            host: "codex",
            command: "patchbay skill install codex",
            safe: true,
            reason: "Update the installed Patchbay Skill from the bundled source without attempting MCP host registration."
          }
        ]
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getByText("需更新")).toBeVisible();
    expect(within(details).getByText("status: outdated")).toBeVisible();
    expect(within(details).getByText("contract: progressive-skill")).toBeVisible();
    expect(within(details).getByText("entrypoint: skills/patchbay/SKILL.md")).toBeVisible();
    expect(within(details).getByText("missing installed files: references/install.md")).toBeVisible();
    expect(within(details).getByText("changed installed files: SKILL.md")).toBeVisible();
    expect(within(details).getByText("extra installed files: legacy.md")).toBeVisible();
    const updateButton = within(details).getByRole("button", { name: "Update Codex Skill" });
    expect(updateButton).toHaveAttribute(
      "title",
      "Update the installed Patchbay Skill from the bundled source without attempting MCP host registration."
    );
    await userEvent.click(updateButton);

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("install Codex Skill"));
    expect(await screen.findByText("Codex Skill updated.")).toBeVisible();
  });

  it("groups readiness actions by action_groups", async () => {
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: vi.fn().mockResolvedValue({
        ok: false,
        root: "C:/repo",
        checks: {
          repo: { ok: true },
          config: { ok: true },
          skill: { ok: true, ready: false, status: "not_installed" },
          mcp: { ok: true, skipped: true }
        },
        actions: [
          {
            id: "apply_economy_profile",
            label: "Apply economy profile",
            kind: "local_agent",
            message: "apply economy profile",
            safe: true,
            reason: "Route high-volume write/fix work to the economy provider."
          },
          {
            id: "install_skill",
            label: "Install Codex Skill",
            kind: "local_agent",
            message: "install Codex Skill",
            host: "codex",
            command: "patchbay skill install codex",
            safe: true,
            reason: "Install the bundled Patchbay Skill without MCP registration."
          },
          {
            label: "Copy doctor command",
            kind: "command",
            command: "patchbay doctor --json",
            safe: true,
            reason: "Copy the read-only doctor command."
          }
        ],
        action_groups: [
          {
            id: "routing",
            label: "Economy routing",
            reason: "Inspect or repair the low-cost write/fix route.",
            action_ids: ["apply_economy_profile"],
            count: 1
          },
          {
            id: "setup",
            label: "Setup and readiness",
            reason: "Run setup or Skill readiness follow-ups.",
            action_ids: ["install_skill"],
            count: 1
          },
          {
            id: "commands",
            label: "Copyable commands",
            reason: "Commands that can be copied or run outside the Agent.",
            action_ids: ["patchbay doctor --json"],
            count: 1
          }
        ]
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    const groups = within(details).getByLabelText("Readiness action groups");
    expect(within(groups).getByText("经济路由")).toBeVisible();
    expect(within(groups).getByText("Inspect or repair the low-cost write/fix route.")).toBeVisible();
    expect(within(groups).getByRole("button", { name: "Apply economy profile" })).toBeVisible();
    expect(within(groups).getByText("就绪设置")).toBeVisible();
    expect(within(groups).getByText("Run setup or Skill readiness follow-ups.")).toBeVisible();
    expect(within(groups).getByRole("button", { name: "Install Codex Skill" })).toBeVisible();
    expect(within(groups).getByText("命令")).toBeVisible();
    expect(within(groups).getByText("patchbay doctor --json")).toBeVisible();
    expect(within(groups).getByRole("button", { name: "Copy command Copy doctor command" })).toBeVisible();
  });

  it("runs generic DeepSeek provider readiness actions through the local Agent", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "custom_provider_setup",
      ok: true,
      reply: "Provide the DeepSeek writer command."
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage,
      getDoctor: vi.fn().mockResolvedValue({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        next_actions: ["Configure a low-cost DeepSeek writer provider."],
        actions: [
          {
            id: "configure_deepseek_provider",
            label: "Configure DeepSeek provider",
            kind: "local_agent",
            message: "configure DeepSeek provider",
            safe: true,
            reason: "Return a safe command template for a low-cost writer/fixer provider."
          }
        ]
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.click(within(details).getByRole("button", { name: "Configure DeepSeek provider" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("configure DeepSeek provider", {
        include: { plan: true },
        background: true
      })
    );
    expect(await screen.findByText("Provide the DeepSeek writer command.")).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("activates a DeepSeek economy provider directly from readiness", async () => {
    const createProvider = vi.fn().mockResolvedValue({
      provider: "cheap_writer",
      activated_economy: true,
      status: {
        profile: "economy",
        economy: {
          matches: true,
          target: { provider: "cheap_writer", model: "deepseek-chat", label: "DeepSeek cheap writer" },
          write: { provider: "cheap_writer", model: "deepseek-chat" },
          fix: { provider: "cheap_writer", model: "deepseek-chat" },
          command_ready: true
        }
      },
      next_actions: ["readiness"],
      actions: [
        {
          id: "open_readiness",
          label: "Open readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Inspect setup and resolved write/fix routing."
        }
      ],
      action_groups: [
        {
          id: "setup",
          label: "Setup and readiness",
          reason: "Inspect the activated provider from readiness.",
          action_ids: ["open_readiness"],
          count: 1
        }
      ]
    });
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
      actions: [
        {
          id: "configure_deepseek_provider",
          label: "Configure DeepSeek provider",
          kind: "local_agent",
          message: "configure DeepSeek provider",
          safe: true,
          reason: "Offer a custom low-cost CLI writer template."
        }
      ],
      routing: {
        profile: "economy",
        economy_configured: true,
        economy_command_ready: true,
        target: { provider: "cheap_writer", model: "deepseek-chat", label: "DeepSeek cheap writer" },
        summary: "Economy routing profile is active: write cheap_writer / deepseek-chat, fix cheap_writer / deepseek-chat."
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      createProvider,
      getDoctor,
      getConfig: vi.fn().mockResolvedValue({ providers: { cheap_writer: { command: "deepseek-writer" } } })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    const form = within(details).getByRole("form", { name: "Economy provider" });

    expect(within(form).getByLabelText("Provider id")).toHaveValue("cheap_writer");
    expect(within(form).getByLabelText("Writer command")).toHaveValue("deepseek-writer");
    await userEvent.click(within(form).getByRole("button", { name: "Activate economy provider" }));

    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith({
        provider_id: "cheap_writer",
        roles: ["write", "fix"],
        command: "deepseek-writer",
        args: [],
        prompt_mode: "stdin",
        output_contract: "writer_diff",
        activate_economy: true,
        economy_model: "deepseek-chat",
        economy_label: "DeepSeek cheap writer"
      })
    );
    expect(await screen.findByText("Economy provider cheap_writer activated.")).toBeVisible();
    const localActions = await screen.findByLabelText("Agent 建议动作");
    expect(within(localActions).getByText("就绪设置")).toHaveAttribute("title", "Inspect the activated provider from readiness.");
    expect(within(localActions).getByRole("button", { name: "Open readiness" })).toBeVisible();
    expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex" });
    expect(client.agentMessage).not.toHaveBeenCalled();
  });

  it("groups local reply command actions by action_groups", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    const command =
      "patchbay config provider add-cli cheap_writer --roles write fix --command <deepseek-writer-command> --output-contract writer_diff --activate-economy";
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "custom_provider_setup",
      ok: true,
      reply: "Use the command action to register a low-cost CLI writer.",
      actions: [
        {
          id: "configure_custom_economy_provider",
          label: "Configure cheap writer provider",
          kind: "command",
          command,
          safe: true,
          reason: "Register a low-cost CLI writer and route write/fix through it."
        },
        {
          id: "open_readiness",
          label: "Open readiness",
          kind: "local_agent",
          message: "readiness",
          safe: true,
          reason: "Inspect setup and economy route command readiness after registering the provider."
        }
      ],
      action_groups: [
        {
          id: "routing",
          label: "Economy routing",
          reason: "Copy the economy provider registration command.",
          action_ids: ["configure_custom_economy_provider"],
          count: 1
        },
        {
          id: "setup",
          label: "Setup and readiness",
          reason: "Inspect the configured provider from readiness.",
          action_ids: ["open_readiness"],
          count: 1
        }
      ]
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "configure DeepSeek provider");
    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("configure DeepSeek provider", {
        include: { plan: true },
        background: true
      })
    );
    const commandActions = await screen.findByLabelText("Agent command actions");
    expect(within(commandActions).getByText("经济路由")).toHaveAttribute("title", "Copy the economy provider registration command.");
    await userEvent.click(within(commandActions).getByRole("button", { name: "Copy command Configure cheap writer provider" }));
    expect(writeText).toHaveBeenCalledWith(command);

    const localActions = await screen.findByLabelText("Agent 建议动作");
    expect(within(localActions).getByText("就绪设置")).toHaveAttribute("title", "Inspect the configured provider from readiness.");
    expect(within(localActions).getByRole("button", { name: "Open readiness" })).toBeVisible();
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("does not expose the economy provider form when readiness has no provider action", async () => {
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: vi.fn().mockResolvedValue({
        ok: true,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
        actions: [],
        routing: {
          profile: "economy",
          economy_configured: true,
          economy_command_ready: true,
          target: { provider: "cheap_writer", model: "deepseek-chat" },
          summary: "Economy routing is healthy."
        }
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });

    expect(within(details).queryByRole("form", { name: "Economy provider" })).not.toBeInTheDocument();
    expect(client.createProvider).not.toHaveBeenCalled();
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
    expect(within(details).getByText("patchbay config --set-key providers.cheap_writer.command --set-value <command>")).toBeVisible();
    await userEvent.click(within(details).getByRole("button", { name: "Copy command Copy provider command" }));

    expect(writeText).toHaveBeenCalledWith("patchbay config --set-key providers.cheap_writer.command --set-value <command>");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.agentMessage).not.toHaveBeenCalled();
  });

  it("falls back to execCommand when Clipboard API is unavailable", async () => {
    const command = "patchbay doctor --json";
    let copiedText = "";
    const execCommand = vi.fn((name: string) => {
      copiedText = (document.activeElement as HTMLTextAreaElement | null)?.value ?? "";
      return name === "copy";
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: vi.fn().mockResolvedValue({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        actions: [
          {
            id: "copy_doctor",
            label: "Copy doctor command",
            kind: "command",
            command,
            safe: true,
            reason: "Copy the read-only doctor command."
          }
        ]
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    const button = within(details).getByRole("button", { name: "Copy command Copy doctor command" });
    await userEvent.click(button);

    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(copiedText).toBe(command);
    expect(button).toHaveTextContent("Copied");
    expect(document.querySelector("textarea[readonly]")).toBeNull();
  });

  it("falls back to execCommand when Clipboard API rejects writes", async () => {
    const command = "patchbay config --set-key providers.cheap_writer.command --set-value <command>";
    const writeText = vi.fn().mockRejectedValue(new Error("clipboard denied"));
    let copiedText = "";
    const execCommand = vi.fn((name: string) => {
      copiedText = (document.activeElement as HTMLTextAreaElement | null)?.value ?? "";
      return name === "copy";
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: vi.fn().mockResolvedValue({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        actions: [
          {
            id: "configure_economy_provider_command",
            label: "Copy provider command",
            kind: "command",
            command,
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
    const button = within(details).getByRole("button", { name: "Copy command Copy provider command" });
    await userEvent.click(button);

    expect(writeText).toHaveBeenCalledWith(command);
    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(copiedText).toBe(command);
    expect(button).toHaveTextContent("Copied");
    expect(document.querySelector("textarea[readonly]")).toBeNull();
  });

  it("shows provider command copy failures when clipboard fallbacks fail", async () => {
    const command = "patchbay config --set-key providers.cheap_writer.command --set-value <command>";
    const writeText = vi.fn().mockRejectedValue(new Error("clipboard denied"));
    const execCommand = vi.fn(() => false);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: vi.fn().mockResolvedValue({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        actions: [
          {
            id: "configure_economy_provider_command",
            label: "Copy provider command",
            kind: "command",
            command,
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
    const button = within(details).getByRole("button", { name: "Copy command Copy provider command" });
    await userEvent.click(button);

    expect(writeText).toHaveBeenCalledWith(command);
    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(button).toHaveTextContent("Unavailable");
    expect(document.querySelector("textarea[readonly]")).toBeNull();
  });

  it("resets provider command copy state when readiness returns a new command", async () => {
    const firstCommand = "patchbay config --set-key providers.cheap_writer.command --set-value deepseek-writer";
    const nextCommand = "patchbay config --set-key providers.cheap_writer.command --set-value reasonix";
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    const providerAction = (command: string) => ({
      id: "configure_economy_provider_command",
      label: "Copy provider command",
      kind: "command",
      command,
      safe: true,
      reason: "Copy the active economy provider command into .ai/patchbay.toml."
    });
    const getDoctor = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        actions: [
          providerAction(firstCommand),
          {
            id: "refresh_readiness",
            label: "Refresh readiness",
            kind: "local_agent",
            message: "readiness",
            safe: true,
            reason: "Re-run read-only readiness checks."
          }
        ]
      })
      .mockResolvedValueOnce({
        ok: false,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
        actions: [providerAction(nextCommand)]
      });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getByText(firstCommand)).toBeVisible();
    const firstButton = within(details).getByRole("button", { name: "Copy command Copy provider command" });
    await userEvent.click(firstButton);

    expect(writeText).toHaveBeenCalledWith(firstCommand);
    expect(firstButton).toHaveTextContent("Copied");

    await userEvent.click(within(details).getByRole("button", { name: "Refresh readiness" }));
    await waitFor(() => expect(getDoctor).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(within(details).getByRole("button", { name: "Copy command Copy provider command" })).toHaveTextContent(/^Copy$/)
    );
    expect(within(details).getByText(nextCommand)).toBeVisible();
    expect(within(details).queryByText(firstCommand)).not.toBeInTheDocument();
    await userEvent.click(within(details).getByRole("button", { name: "Copy command Copy provider command" }));

    expect(writeText).toHaveBeenLastCalledWith(nextCommand);
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
    const snapshot = screen.getByLabelText("运行概览");
    expect(within(snapshot).getByRole("heading", { name: "运行概览" })).toBeVisible();
    expect(within(snapshot).getByText("阶段")).toBeVisible();
    expect(within(snapshot).getByText("应用 · 审查通过")).toBeVisible();
    expect(within(snapshot).getByText("门禁")).toBeVisible();
    expect(within(snapshot).getByText("4/4 gates")).toBeVisible();
    expect(within(snapshot).getByText("可以应用")).toBeVisible();
    expect(within(snapshot).getByText("经济路由")).toBeVisible();
    expect(within(snapshot).getByText("等待 write/fix provider 证据")).toBeVisible();
    expect(within(snapshot).getByText("最近 provider")).toBeVisible();
    expect(within(snapshot).getByText("审查 · codex_cli / gpt-5")).toBeVisible();
    expect(within(snapshot).getByText("通过 · 10:02:00")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    expect(screen.getByText("12s")).toBeVisible();
    expect(screen.getAllByText("实现 8.0s")[0]).toBeVisible();
    expect(screen.getByText("8 / 5")).toBeVisible();
    expect(screen.getByText("未上报")).toBeVisible();
    expect(screen.getByText("待上报")).toBeVisible();

    await userEvent.click(screen.getByRole("tab", { name: "提供方" }));

    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getByRole("heading", { name: "提供方摘要" })).toBeVisible();
    expect(within(details).getByText("Configured phase providers and observed provider events are summarized for routing inspection.")).toBeVisible();
    expect(within(details).getByText("4 configured")).toBeVisible();
    expect(within(details).getByText("3 observed")).toBeVisible();
    expect(within(details).getByText("1 events")).toBeVisible();
    const routesSection = within(details).getByRole("heading", { name: "阶段路由" }).closest("section")!;
    expect(within(routesSection).getByText("实现")).toBeVisible();
    expect(within(routesSection).getAllByText("reasonix_cli / reasonix")[0]).toBeVisible();
    expect(within(routesSection).getByText("reasonix_cli · 2 events · 8.0s")).toBeVisible();
    expect(within(routesSection).getByText("No provider usage observed.")).toBeVisible();
    const trailSection = within(details).getByRole("heading", { name: "事件轨迹" }).closest("section")!;
    expect(within(trailSection).getByText("codex_cli / gpt-5")).toBeVisible();
    expect(within(trailSection).getByText("通过 · 10:02:00")).toBeVisible();
    expect(client.getContext).toHaveBeenCalledWith("run-ready");

    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    expect(await screen.findByText("需要处理")).toBeVisible();
    expect(screen.getAllByText(/patchbay skill install codex/)[0]).toBeVisible();
    expect(screen.getByRole("button", { name: "Refresh readiness" })).toBeVisible();
    expect(client.getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex" });
  });

  it("shows a named error when the initial run list load fails", async () => {
    const client = createClient({
      listRuns: vi.fn().mockRejectedValue(new Error("list unavailable"))
    });

    render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("加载运行列表失败：list unavailable");
    expect(screen.getByRole("heading", { name: "新任务" })).toBeInTheDocument();
    expect(client.getStatus).not.toHaveBeenCalled();
  });

  it("shows a named error when selected run details fail to load", async () => {
    const getContext = vi.fn().mockRejectedValue(new Error("context unavailable"));
    const client = createClient({ getContext });

    render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("加载运行详情失败：context unavailable");
    await waitFor(() => expect(getContext).toHaveBeenCalledWith("run-ready"));
  });

  it("renders the Trace diagnostics drawer as readable timeline summaries", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "活动" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });

    expect(within(details).getByRole("heading", { name: "活动摘要" })).toBeVisible();
    expect(within(details).getByText("1 selected")).toBeVisible();
    expect(within(details).getByText("1 timeline")).toBeVisible();
    expect(within(details).getByText("1 trace")).toBeVisible();
    const selectedSection = within(details).getByRole("heading", { name: "Selected message" }).closest("section")!;
    const timelineSection = within(details).getByRole("heading", { name: "Run timeline" }).closest("section")!;
    const providerSection = within(details).getByRole("heading", { name: "Provider trace" }).closest("section")!;
    expect(within(selectedSection).getByText("ready from context")).toBeVisible();
    expect(within(timelineSection).getByText("ready from context")).toBeVisible();
    expect(within(providerSection).getByText("ready")).toBeVisible();
    expect(within(providerSection).getByText("patchbay_review")).toBeVisible();
    expect(within(providerSection).getByText(".ai/runs/run-ready/REVIEW.md")).toBeVisible();
    expect(within(details).getByText("Raw trace JSON")).toBeVisible();
    expect(within(details).getByText(/selected_message/)).not.toBeVisible();
  });

  it("restores the selected Trace message for each run after remount", async () => {
    const contextWithMessages = {
      ...readyContext,
      agent_activity: {
        ...readyContext.agent_activity!,
        messages: [
          {
            id: "event-first",
            kind: "event",
            timestamp: "2026-05-24T10:02:00Z",
            phase: "plan",
            title: "First trace event",
            body: "First selected trace body",
            status: "PLANNED",
            status_label: "waiting",
            tone: "ready"
          },
          {
            id: "event-second",
            kind: "event",
            timestamp: "2026-05-24T10:03:00Z",
            phase: "review",
            title: "Second trace event",
            body: "Second selected trace body",
            status: "PASS",
            status_label: "pass",
            tone: "success",
            provider: "codex_cli",
            model: "gpt-5"
          }
        ]
      }
    };
    const client = createClient({ getContext: vi.fn().mockResolvedValue(contextWithMessages) });
    const { unmount } = render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: /Second trace event/ }));

    expect(window.localStorage.getItem("patchbay.selectedMessage.run-ready")).toBe("event-second");
    unmount();

    render(<Workbench client={createClient({ getContext: vi.fn().mockResolvedValue(contextWithMessages) })} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "活动" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    const selectedSection = within(details).getByRole("heading", { name: "Selected message" }).closest("section")!;
    expect(within(selectedSection).getByText("Second selected trace body")).toBeVisible();
    expect(within(selectedSection).queryByText("First selected trace body")).not.toBeInTheDocument();
  });

  it("renders the Config diagnostics drawer as readable configuration summaries", async () => {
    const client = createClient({
      getConfig: vi.fn().mockResolvedValue({
        config: "C:/repo/.ai/patchbay.toml",
        resolved: {
          phases: {
            plan: { provider: "claude_cli", model: "opus", timeout: 900 },
            write: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", timeout: 900 },
            fix: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", timeout: 900 },
            review: { provider: "codex_cli", model: "gpt-5", timeout: 900 },
            test: { commands: ["npm test"], timeout: 300 },
            apply: { timeout: 120 }
          },
          commands: { claude: "claude", codex: "codex", reasonix: "" },
          providers: { cheap_writer: { roles: ["write", "fix"], command: "deepseek-writer", args: ["--json"] } },
          commands_allowlist: { test: ["npm test", "pytest -q"] },
          workflow: {
            require_plan_approval: true,
            fail_on_dirty_workspace: true,
            apply_to_current_workspace_only_after_review_pass: true,
            allow_apply_without_tests: false
          }
        }
      })
    });

    render(<Workbench client={client} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "配置" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });

    expect(within(details).getByRole("heading", { name: "配置摘要" })).toBeVisible();
    expect(within(details).getByText("C:/repo/.ai/patchbay.toml")).toBeVisible();
    expect(within(details).getByText("6 phases")).toBeVisible();
    expect(within(details).getByText("3 commands")).toBeVisible();
    expect(within(details).getByText("1 providers")).toBeVisible();
    expect(within(details).getByText("2 tests")).toBeVisible();
    expect(within(details).getAllByText("reasonix_cli / deepseek-v4-pro").length).toBeGreaterThan(0);
    expect(within(details).getAllByText("command reasonix · 900s").length).toBeGreaterThan(0);
    expect(within(details).getByText("cheap_writer")).toBeVisible();
    expect(within(details).getByText("write/fix · deepseek-writer --json")).toBeVisible();
    expect(within(details).getByText("reasonix: 未配置")).toBeVisible();
    expect(within(details).getByText("npm test")).toBeVisible();
    expect(within(details).getByText("pytest -q")).toBeVisible();
    expect(within(details).getByText("计划批准门禁")).toBeVisible();
    expect(within(details).getAllByText("开启").length).toBeGreaterThan(0);
    expect(within(details).getByText("Raw config JSON")).toBeVisible();
    expect(within(details).getAllByText(/patchbay.toml/).length).toBeGreaterThan(0);
  });

  it("does not label custom write and fix providers as economy in the strategy map", async () => {
    const routing = {
      profile: "custom",
      economy_configured: false,
      summary: "Custom routing active.",
      phases: {
        write: { configured: { provider: "codex_cli", model: "gpt-5" }, configured_economy: false },
        fix: { configured: { provider: "codex_cli", model: "gpt-5" }, configured_economy: false }
      }
    };
    const customContext = {
      ...readyContext,
      run_metrics: {
        ...readyContext.run_metrics!,
        routing_evidence: routing
      }
    };
    const client = createClient({
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
        effective_phase_providers: {
          plan: { provider: "claude_cli", model: "opus" },
          write: { provider: "codex_cli", model: "gpt-5" },
          fix: { provider: "codex_cli", model: "gpt-5" },
          review: { provider: "codex_cli", model: "gpt-5" }
        },
        run_metrics: customContext.run_metrics
      }),
      getContext: vi.fn().mockResolvedValue(customContext)
    });

    render(<Workbench client={client} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });

    expect(within(details).getByText("路由策略")).toBeVisible();
    expect(within(details).getAllByText("自定义")).toHaveLength(2);
    expect(within(details).queryByText("经济")).not.toBeInTheDocument();
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
    const metricsSection = screen.getByRole("heading", { name: "效率" }).closest("section")!;
    expect(within(metricsSection).getByText("经济覆盖")).toBeVisible();
    expect(within(metricsSection).getByText("50% · 1/2")).toBeVisible();
    expect(within(metricsSection).getByText("经济健康")).toBeVisible();
    expect(screen.getAllByText("待观测").length).toBeGreaterThan(0);
    expect(screen.getByText("6")).toBeVisible();
    expect(screen.getByText("审查 2x")).toBeVisible();
    await userEvent.click(within(metricsSection).getByRole("button", { name: "Inspect routing events" }));
    expect(screen.getByRole("tab", { name: "活动" })).toHaveAttribute("aria-selected", "true");
  });

  it("opens readiness from generic health card local Agent actions", async () => {
    const getDoctor = vi.fn().mockResolvedValue({
      ok: false,
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
      next_actions: ["Inspect provider command readiness."],
      actions: []
    });
    const client = createClient({
      getDoctor,
      getContext: vi.fn().mockResolvedValue({
        ...readyContext,
        agent_activity: {
          ...readyContext.agent_activity,
          health_cards: [
            {
              key: "provider_command",
              label: "Provider command",
              status: "command_not_ready",
              tone: "blocked",
              detail: "The economy provider command needs inspection.",
              next_action: "inspect_economy_provider_command"
            }
          ]
        }
      })
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.click(within(details).getByRole("button", { name: "Inspect provider command" }));

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex" }));
    expect(screen.getByRole("tab", { name: "就绪" })).toHaveAttribute("aria-selected", "true");
    expect(client.agentMessage).not.toHaveBeenCalledWith("readiness", expect.anything());
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
    const metricsSection = screen.getByRole("heading", { name: "效率" }).closest("section")!;
    expect(within(metricsSection).getByText("命令未就绪 · write/fix")).toBeVisible();
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
              id: "configure_economy_provider_command",
              label: "Copy provider command",
              kind: "command",
              command,
              safe: true,
              reason: "Copy the command for the Cheap writer economy provider into .ai/patchbay.toml."
            },
            {
              id: "inspect_economy_provider_command",
              label: "Inspect provider command",
              kind: "local_agent",
              message: "readiness",
              safe: true,
              reason: "Open readiness to inspect the configured Cheap writer economy provider command."
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
    expect(within(details).getByText(command)).toBeVisible();
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

  it("restores sidebar search and status filters after remount", async () => {
    const { unmount } = render(<Workbench client={createClient()} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.selectOptions(screen.getByLabelText("状态筛选"), "REVIEWED_CHANGES_REQUESTED");
    await userEvent.type(screen.getByLabelText("搜索运行"), "fix");

    expect(window.localStorage.getItem("patchbay.statusFilter")).toBe("REVIEWED_CHANGES_REQUESTED");
    expect(window.localStorage.getItem("patchbay.runSearch")).toBe("fix");
    unmount();

    const getStatus = vi.fn().mockResolvedValue({
      run_id: "run-fix",
      task: "Needs fix",
      status: "REVIEWED_CHANGES_REQUESTED",
      current_phase: "fix",
      gate_state: { approved: true, tests_passed: true, review_result: "CHANGES_REQUESTED", ready_to_apply: false },
      artifacts: []
    });
    const getContext = vi.fn().mockResolvedValue({
      ...plannedContext,
      run_id: "run-fix",
      status: "REVIEWED_CHANGES_REQUESTED",
      current_phase: "fix",
      agent_activity: {
        ...plannedContext.agent_activity!,
        conversation_state: {
          ...plannedContext.agent_activity!.conversation_state!,
          task: "Needs fix",
          status: "REVIEWED_CHANGES_REQUESTED",
          phase: "fix",
          phase_label: "修复"
        }
      }
    });
    render(<Workbench client={createClient({ getStatus, getContext })} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
    expect(screen.getByLabelText("搜索运行")).toHaveValue("fix");
    expect(screen.getByLabelText("状态筛选")).toHaveValue("REVIEWED_CHANGES_REQUESTED");
    const runList = screen.getByLabelText("运行线程");
    expect(within(runList).queryByRole("button", { name: /Ship dashboard/ })).not.toBeInTheDocument();
    expect(within(runList).getByRole("button", { name: /Needs fix/ })).toBeInTheDocument();
  });

  it("restores the selected run and diagnostics view after remount", async () => {
    const { unmount } = render(<Workbench client={createClient()} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const runList = screen.getByLabelText("运行线程");
    await userEvent.click(within(runList).getByRole("button", { name: /Needs fix/ }));
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "日志" }));

    expect(window.localStorage.getItem("patchbay.selectedRun")).toBe("run-fix");
    expect(window.localStorage.getItem("patchbay.diagnosticsOpen")).toBe("true");
    expect(window.localStorage.getItem("patchbay.diagnosticsTab")).toBe("Log");
    unmount();

    const getStatus = vi.fn().mockResolvedValue({
      run_id: "run-fix",
      task: "Needs fix",
      status: "REVIEWED_CHANGES_REQUESTED",
      current_phase: "fix",
      gate_state: { approved: true, tests_passed: true, review_result: "CHANGES_REQUESTED", ready_to_apply: false },
      artifacts: []
    });
    const getContext = vi.fn().mockResolvedValue({
      ...plannedContext,
      run_id: "run-fix",
      status: "REVIEWED_CHANGES_REQUESTED",
      current_phase: "fix",
      agent_activity: {
        ...plannedContext.agent_activity!,
        conversation_state: {
          ...plannedContext.agent_activity!.conversation_state!,
          task: "Needs fix",
          status: "REVIEWED_CHANGES_REQUESTED",
          phase: "fix",
          phase_label: "修复"
        }
      }
    });
    render(<Workbench client={createClient({ getStatus, getContext })} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "诊断" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("tab", { name: "日志" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(getStatus).toHaveBeenCalledWith("run-fix"));
    await waitFor(() => expect(getContext).toHaveBeenCalledWith("run-fix"));
  });

  it("refreshes the selected run details from the topbar", async () => {
    const initialContext = {
      ...readyContext,
      timeline: [
        {
          source: "event",
          index: 0,
          timestamp: "2026-05-24T10:02:00Z",
          phase: "review",
          action: "success",
          status: "PASS",
          detail: "initial timeline detail"
        }
      ],
      agent_activity: {
        ...readyContext.agent_activity!,
        messages: [
          {
            id: "initial-event",
            kind: "event",
            timestamp: "2026-05-24T10:02:00Z",
            phase: "review",
            title: "Initial event",
            body: "initial context body",
            status: "PASS",
            status_label: "pass",
            tone: "success"
          }
        ]
      },
      cursors: { event: 1, trace: 0 }
    };
    const refreshedContext = {
      ...initialContext,
      timeline: [
        {
          source: "event",
          index: 1,
          timestamp: "2026-05-24T10:03:00Z",
          phase: "review",
          action: "success",
          status: "PASS",
          detail: "refreshed timeline detail"
        }
      ],
      agent_activity: {
        ...initialContext.agent_activity,
        messages: [
          {
            id: "refreshed-event",
            kind: "event",
            timestamp: "2026-05-24T10:03:00Z",
            phase: "review",
            title: "Refreshed event",
            body: "refreshed context body",
            status: "PASS",
            status_label: "pass",
            tone: "success"
          }
        ]
      },
      cursors: { event: 2, trace: 0 }
    };
    const status = {
      run_id: "run-ready",
      task: "Ship dashboard",
      status: "REVIEWED_PASS",
      current_phase: "apply",
      gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
      artifacts: []
    };
    const getStatus = vi.fn().mockResolvedValue(status);
    const getContext = vi.fn().mockResolvedValueOnce(initialContext).mockResolvedValue(refreshedContext);
    const getTrace = vi
      .fn()
      .mockResolvedValueOnce({ events: [{ seq: 1, phase: "plan", action: "start", detail: "initial provider trace" }] })
      .mockResolvedValue({ events: [{ seq: 2, phase: "review", action: "success", detail: "refreshed provider trace" }] });
    const getDiff = vi.fn().mockResolvedValueOnce({ diff: "diff --git a/old b/old" }).mockResolvedValue({ diff: "diff --git a/fresh b/fresh" });
    const client = createClient({ getStatus, getContext, getTrace, getDiff });

    render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByText("initial context body")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "刷新运行" }));

    await waitFor(() => expect(getContext).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("refreshed context body")).toBeVisible();
    expect(screen.queryByText("initial context body")).not.toBeInTheDocument();
    expect(getStatus).toHaveBeenCalledTimes(2);
    expect(getTrace).toHaveBeenCalledTimes(2);
    expect(getDiff).toHaveBeenCalledTimes(2);

    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "活动" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    const providerSection = within(details).getByRole("heading", { name: "Provider trace" }).closest("section")!;
    expect(within(providerSection).getByText("refreshed provider trace")).toBeVisible();
    expect(within(providerSection).queryByText("initial provider trace")).not.toBeInTheDocument();
  });

  it("shows a visible error when topbar refresh fails", async () => {
    const getContext = vi.fn().mockResolvedValueOnce(readyContext).mockRejectedValueOnce(new Error("context unavailable"));
    const client = createClient({ getContext });

    render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    const refresh = screen.getByRole("button", { name: "刷新运行" });
    await userEvent.click(refresh);

    expect(await screen.findByRole("alert")).toHaveTextContent("刷新运行失败：context unavailable");
    await waitFor(() => expect(refresh).toBeEnabled());
  });

  it("falls back to the inbox focus when the restored run no longer exists", async () => {
    window.localStorage.setItem("patchbay.selectedRun", "run-gone");
    const getStatus = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      task: "Ship dashboard",
      status: "REVIEWED_PASS",
      current_phase: "apply",
      gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
      artifacts: []
    });
    const getContext = vi.fn().mockResolvedValue(readyContext);
    const client = createClient({ getStatus, getContext });

    render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    await waitFor(() => expect(getStatus).toHaveBeenCalledWith("run-ready"));
    expect(getStatus).not.toHaveBeenCalledWith("run-gone");
    expect(getContext).not.toHaveBeenCalledWith("run-gone");
    expect(window.localStorage.getItem("patchbay.selectedRun")).toBe("run-ready");
  });

  it("keeps composer drafts isolated per selected run", async () => {
    const client = createClient();

    render(<Workbench client={client} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const composer = screen.getByLabelText("给 Patchbay Agent 输入消息");
    await userEvent.type(composer, "check the apply gate");

    expect(window.localStorage.getItem("patchbay.composerDraft.run-ready")).toBe("check the apply gate");

    const runList = screen.getByLabelText("运行线程");
    await userEvent.click(within(runList).getByRole("button", { name: /Needs fix/ }));

    expect(await screen.findByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
    expect(composer).toHaveValue("");
    await userEvent.type(composer, "fix review comments");

    expect(window.localStorage.getItem("patchbay.composerDraft.run-fix")).toBe("fix review comments");

    await userEvent.click(within(runList).getByRole("button", { name: /Ship dashboard/ }));

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    expect(composer).toHaveValue("check the apply gate");
  });

  it("restores the new-task composer draft after remount", async () => {
    const client = createClient({ listRuns: vi.fn().mockResolvedValue({ runs: [] }) });
    const { unmount } = render(<Workbench client={client} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "Build offline workbench mode");

    expect(window.localStorage.getItem("patchbay.composerDraft.__new__")).toBe("Build offline workbench mode");
    unmount();

    render(<Workbench client={createClient({ listRuns: vi.fn().mockResolvedValue({ runs: [] }) })} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "新任务" })).toBeInTheDocument();
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toHaveValue("Build offline workbench mode");
  });

  it("restores the new-task view and draft even when existing runs are available", async () => {
    const client = createClient();
    const { unmount } = render(<Workbench client={client} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "新任务" }));

    expect(await screen.findByRole("heading", { name: "新任务" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "Build persistent new task view");

    expect(window.localStorage.getItem("patchbay.newTaskMode")).toBe("true");
    expect(window.localStorage.getItem("patchbay.composerDraft.__new__")).toBe("Build persistent new task view");
    unmount();

    render(<Workbench client={createClient()} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "新任务" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ship dashboard" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toHaveValue("Build persistent new task view");

    const runList = screen.getByLabelText("运行线程");
    await userEvent.click(within(runList).getByRole("button", { name: /Ship dashboard/ }));

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    expect(window.localStorage.getItem("patchbay.newTaskMode")).toBeNull();
  });

  it("clears the matching composer draft after a successful submit", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      reply: "Run run-ready is through the technical gates.",
      context: readyContext,
      status: {
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
        artifacts: []
      }
    });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "why is apply blocked");

    expect(window.localStorage.getItem("patchbay.composerDraft.run-ready")).toBe("why is apply blocked");

    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("why is apply blocked", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    expect(window.localStorage.getItem("patchbay.composerDraft.run-ready")).toBeNull();
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toHaveValue("");
  });

  it("preserves a selected-run composer draft when submit fails", async () => {
    const agentMessage = vi.fn().mockRejectedValue(new Error("network unavailable"));
    const client = createClient({ agentMessage });

    render(<Workbench client={client} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "keep this note");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("发送消息失败：network unavailable");
    expect(window.localStorage.getItem("patchbay.composerDraft.run-ready")).toBe("keep this note");
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toHaveValue("keep this note");
  });

  it("restores compact new-task local Agent replies after remount", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay setup completed with follow-up steps.",
      status: { run_id: "ignored-heavy-status", status: "PLANNED" },
      context: readyContext,
      diff: "diff --git a/large b/large",
      job: { transcript: "large worker payload" },
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
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true } },
          next_actions: []
        }
      },
      actions: [
        {
          id: "register_mcp",
          label: "Register MCP",
          kind: "command",
          command: "claude mcp add patchbay -- python scripts/patchbay_mcp_server.py",
          safe: true
        }
      ],
      action_groups: [{ id: "commands", label: "Commands", action_ids: ["register_mcp"] }]
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });
    const { unmount } = render(<Workbench client={client} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "Setup Claude Desktop" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup for claude-desktop"));
    expect(await screen.findByText("Patchbay setup completed with follow-up steps.")).toBeVisible();
    expect(within(screen.getByLabelText("Setup result")).getByText("claude mcp add patchbay -- python scripts/patchbay_mcp_server.py")).toBeVisible();
    expect(within(screen.getByLabelText("Agent command actions")).getByRole("button", { name: "Copy command Register MCP" })).toBeVisible();

    const stored = JSON.parse(window.localStorage.getItem("patchbay.newTaskReply") ?? "{}");
    expect(stored.reply).toBe("Patchbay setup completed with follow-up steps.");
    expect(stored.setup?.mcp?.command).toBe("claude mcp add patchbay -- python scripts/patchbay_mcp_server.py");
    expect(stored.actions).toHaveLength(1);
    expect(stored.context).toBeUndefined();
    expect(stored.status).toBeUndefined();
    expect(stored.diff).toBeUndefined();
    expect(stored.job).toBeUndefined();
    unmount();

    render(<Workbench client={createClient({ listRuns: vi.fn().mockResolvedValue({ runs: [] }) })} pollIntervalMs={0} />);

    expect(await screen.findByText("Patchbay setup completed with follow-up steps.")).toBeVisible();
    expect(within(screen.getByLabelText("Setup result")).getByText("Claude Desktop")).toBeVisible();
    expect(within(screen.getByLabelText("Agent command actions")).getByRole("button", { name: "Copy command Register MCP" })).toBeVisible();
  });

  it("restores selected-run local messages and compact Agent replies after remount", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "profile_show",
      ok: true,
      reply: "Writer/fix economy route is verified.",
      context: readyContext,
      status: {
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
        artifacts: []
      },
      metrics: {
        routing_evidence: {
          economy_configured: true,
          economy_health: {
            status: "healthy",
            severity: "ok",
            summary: "Economy write/fix provider was observed.",
            target: { provider: "reasonix_cli", model: "deepseek-v4-pro", label: "Reasonix/DeepSeek" }
          },
          phases: {
            write: { configured_economy: true, observed_economy: true },
            fix: { configured_economy: true, observed_economy: true }
          }
        },
        efficiency_summary: {
          status: "verified_economy",
          routing_status: "healthy",
          usage_known: { duration: true },
          economy_share: { duration_percent: 72, duration_ms: 9000 },
          summary: "Cheap writer/fix work handled most simple implementation time."
        }
      }
    });
    const client = createClient({ agentMessage });
    const { unmount } = render(<Workbench client={client} pollIntervalMs={0} />);

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
    expect(await screen.findByText("is writer using cheap model?")).toBeVisible();
    expect(await screen.findByText("Writer/fix economy route is verified.")).toBeVisible();
    expect(screen.getByLabelText("Routing result")).toBeVisible();

    const stored = JSON.parse(window.localStorage.getItem("patchbay.localMessages") ?? "{}");
    expect(stored["run-ready"]).toHaveLength(2);
    expect(stored["run-ready"][1].response.reply).toBe("Writer/fix economy route is verified.");
    expect(stored["run-ready"][1].response.metrics.efficiency_summary.status).toBe("verified_economy");
    expect(stored["run-ready"][1].response.context).toBeUndefined();
    expect(stored["run-ready"][1].response.status).toBeUndefined();
    unmount();

    render(<Workbench client={createClient()} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    expect(await screen.findByText("is writer using cheap model?")).toBeVisible();
    expect(await screen.findByText("Writer/fix economy route is verified.")).toBeVisible();
    expect(screen.getByLabelText("Routing result")).toBeVisible();
  });

  it("keeps persisted local transcript caches bounded", async () => {
    const oldMessages = Array.from({ length: 10 }, (_, index) => ({
      id: `old-${index}`,
      body: `persisted note ${index}`,
      timestamp: `2026-05-24T10:${String(index).padStart(2, "0")}:00Z`
    }));
    window.localStorage.setItem("patchbay.localMessages", JSON.stringify({ "run-ready": oldMessages }));
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      ok: true,
      reply: "Pruning reply.",
      context: readyContext,
      status: {
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
        artifacts: []
      }
    });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} pollIntervalMs={0} />);

    expect(await screen.findByText("persisted note 2")).toBeVisible();
    expect(screen.queryByText("persisted note 0")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "fresh pruning note");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalled());
    const stored = JSON.parse(window.localStorage.getItem("patchbay.localMessages") ?? "{}");
    expect(stored["run-ready"]).toHaveLength(8);
    expect(stored["run-ready"].map((message: { body: string }) => message.body)).toEqual([
      "persisted note 4",
      "persisted note 5",
      "persisted note 6",
      "persisted note 7",
      "persisted note 8",
      "persisted note 9",
      "fresh pruning note",
      "Pruning reply."
    ]);
  });

  it("renders structured runs inbox state in the sidebar", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const summary = screen.getByLabelText("Agent inbox summary");
    expect(within(summary).getByText("Agent inbox")).toBeVisible();
    expect(within(summary).getByText(/2 runs; 1 need confirmation/)).toBeVisible();
    expect(within(summary).getByText("Ready to apply")).toBeVisible();
    expect(within(summary).getByText("Ready to continue")).toBeVisible();

    const runList = screen.getByLabelText("运行线程");
    const readyRun = within(runList).getByRole("button", { name: /Ship dashboard/ });
    expect(within(readyRun).getByText("Ready to apply")).toBeVisible();
    expect(within(readyRun).getByText("Apply reviewed diff · needs confirmation")).toBeVisible();
    const readySignals = within(readyRun).getByLabelText("Run quick signals");
    expect(within(readySignals).getByText("阶段")).toBeVisible();
    expect(within(readySignals).getByText("应用")).toBeVisible();
    expect(within(readySignals).getByText("门禁")).toBeVisible();
    expect(within(readySignals).getByText("4/4 gates")).toBeVisible();
    expect(within(readySignals).getByText("经济")).toBeVisible();
    expect(within(readySignals).getByText("健康")).toBeVisible();
    expect(within(readySignals).getByText("提供方")).toBeVisible();
    expect(within(readySignals).getByText("审查 · codex_cli / gpt-5")).toBeVisible();

    const fixRun = within(runList).getByRole("button", { name: /Needs fix/ });
    expect(within(fixRun).getByText("Ready to continue")).toBeVisible();
    expect(within(fixRun).getByText("Continue run")).toBeVisible();
    expect(within(runList).getByRole("button", { name: "Run inbox action: Apply reviewed diff" })).toBeVisible();
    expect(within(runList).getByRole("button", { name: "Run inbox action: Continue run" })).toBeVisible();
  });

  it("keeps confirmable inbox actions behind the confirmation gate", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const runList = screen.getByLabelText("运行线程");

    await userEvent.click(within(runList).getByRole("button", { name: "Run inbox action: Apply reviewed diff" }));
    expect(await screen.findByRole("dialog", { name: "确认应用补丁" })).toBeInTheDocument();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.agentMessage).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    await userEvent.click(within(runList).getByRole("button", { name: "Run inbox action: Continue run" }));

    expect(await screen.findByRole("dialog", { name: "确认继续运行" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.agentMessage).not.toHaveBeenCalled();
  });

  it("opens safe inbox run actions directly", async () => {
    const getContext = vi.fn((runId: string) =>
      Promise.resolve(
        runId === "run-old"
          ? {
              ...readyContext,
              run_id: "run-old",
              status: "APPLIED",
              current_phase: "apply",
              agent_activity: {
                ...readyContext.agent_activity!,
                conversation_state: {
                  ...readyContext.agent_activity!.conversation_state!,
                  task: "Already applied",
                  status: "APPLIED"
                }
              }
            }
          : readyContext
      )
    );
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({
        count: 2,
        runs: [
          {
            run_id: "run-ready",
            task: "Ship dashboard",
            status: "REVIEWED_PASS",
            gate_state: { approved: true, tests_passed: true, review_result: "PASS", ready_to_apply: true },
            inbox: {
              key: "ready_to_apply",
              label: "Ready to apply",
              next_action: { id: "apply", label: "Apply reviewed diff", kind: "local_agent", run_id: "run-ready", message: "apply", safe: false }
            }
          },
          {
            run_id: "run-old",
            task: "Already applied",
            status: "APPLIED",
            inbox: {
              key: "applied",
              label: "Applied",
              next_action: { id: "open_run", label: "Open run", kind: "open_run", run_id: "run-old", tab: "Overview", safe: true }
            }
          }
        ],
        inbox: {
          total: 2,
          focus_run_id: "run-ready",
          groups: [
            { key: "ready_to_apply", label: "Ready to apply", count: 1, run_ids: ["run-ready"] },
            { key: "applied", label: "Applied", count: 1, run_ids: ["run-old"] }
          ]
        }
      }),
      getContext
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "Run inbox action: Open run" }));

    expect(await screen.findByRole("heading", { name: "Already applied" })).toBeInTheDocument();
    await waitFor(() => expect(getContext).toHaveBeenCalledWith("run-old"));
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.agentMessage).not.toHaveBeenCalled();
  });

  it("filters runs by inbox group chips", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    const summary = screen.getByLabelText("Agent inbox summary");
    await userEvent.click(within(summary).getByRole("button", { name: /Ready to continue/ }));

    const runList = screen.getByLabelText("运行线程");
    expect(window.localStorage.getItem("patchbay.inboxFilter")).toBe("ready_to_continue");
    expect(within(runList).queryByRole("button", { name: /Ship dashboard/ })).not.toBeInTheDocument();
    expect(within(runList).getByRole("button", { name: /Needs fix/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needs fix" })).toBeInTheDocument();

    await userEvent.click(within(summary).getByRole("button", { name: /Ready to continue/ }));
    expect(window.localStorage.getItem("patchbay.inboxFilter")).toBeNull();
    expect(within(runList).getByRole("button", { name: /Ship dashboard/ })).toBeInTheDocument();
    expect(within(runList).getByRole("button", { name: /Needs fix/ })).toBeInTheDocument();
  });

  it("restores inbox group filters and clears them when they are stale", async () => {
    const { unmount } = render(<Workbench client={createClient()} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(within(screen.getByLabelText("Agent inbox summary")).getByRole("button", { name: /Ready to continue/ }));

    expect(window.localStorage.getItem("patchbay.inboxFilter")).toBe("ready_to_continue");
    unmount();

    const getStatus = vi.fn().mockResolvedValue({
      run_id: "run-fix",
      task: "Needs fix",
      status: "REVIEWED_CHANGES_REQUESTED",
      current_phase: "fix",
      gate_state: { approved: true, tests_passed: true, review_result: "CHANGES_REQUESTED", ready_to_apply: false },
      artifacts: []
    });
    const getContext = vi.fn().mockResolvedValue({
      ...plannedContext,
      run_id: "run-fix",
      status: "REVIEWED_CHANGES_REQUESTED",
      current_phase: "fix",
      agent_activity: {
        ...plannedContext.agent_activity!,
        conversation_state: {
          ...plannedContext.agent_activity!.conversation_state!,
          task: "Needs fix",
          status: "REVIEWED_CHANGES_REQUESTED",
          phase: "fix",
          phase_label: "修复"
        }
      }
    });
    const restored = render(<Workbench client={createClient({ getStatus, getContext })} pollIntervalMs={0} />);

    expect(await screen.findByRole("heading", { name: "Needs fix" })).toBeInTheDocument();
    expect(window.localStorage.getItem("patchbay.inboxFilter")).toBe("ready_to_continue");
    let runList = screen.getByLabelText("运行线程");
    expect(within(runList).queryByRole("button", { name: /Ship dashboard/ })).not.toBeInTheDocument();
    expect(within(runList).getByRole("button", { name: /Needs fix/ })).toBeInTheDocument();
    restored.unmount();

    window.localStorage.setItem("patchbay.inboxFilter", "stale_group");
    render(<Workbench client={createClient()} pollIntervalMs={0} />);

    await waitFor(() => expect(window.localStorage.getItem("patchbay.inboxFilter")).toBeNull());
    runList = screen.getByLabelText("运行线程");
    expect(within(runList).getByRole("button", { name: /Ship dashboard/ })).toBeInTheDocument();
    expect(within(runList).getByRole("button", { name: /Needs fix/ })).toBeInTheDocument();
  });

  it("auto-selects the inbox focus run instead of the first recent run", async () => {
    const getContext = vi.fn().mockResolvedValue(readyContext);
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({
        count: 2,
        runs: [
          {
            run_id: "run-old",
            task: "Already applied",
            status: "APPLIED",
            updated_at: "2026-05-24T11:00:00Z",
            inbox: {
              key: "applied",
              label: "Applied",
              priority: 20,
              safe: true,
              next_action: { id: "open_run", label: "Open run", kind: "open_run", run_id: "run-old", safe: true }
            }
          },
          {
            run_id: "run-ready",
            task: "Ship dashboard",
            status: "REVIEWED_PASS",
            updated_at: "2026-05-24T10:00:00Z",
            inbox: {
              key: "ready_to_apply",
              label: "Ready to apply",
              priority: 80,
              safe: false,
              requires_confirmation: true,
              next_action: { id: "apply", label: "Apply reviewed diff", kind: "local_agent", run_id: "run-ready", message: "apply", safe: false }
            }
          }
        ],
        inbox: {
          total: 2,
          focus_run_id: "run-ready",
          confirmation_required_count: 1,
          groups: [
            { key: "ready_to_apply", label: "Ready to apply", count: 1, run_ids: ["run-ready"] },
            { key: "applied", label: "Applied", count: 1, run_ids: ["run-old"] }
          ]
        }
      }),
      getContext
    });

    render(<Workbench client={client} />);

    expect(await screen.findByRole("heading", { name: "Ship dashboard" })).toBeInTheDocument();
    await waitFor(() => expect(getContext).toHaveBeenCalledWith("run-ready"));
    expect(getContext).not.toHaveBeenCalledWith("run-old");
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
        action_groups: [
          {
            id: "setup",
            label: "Setup and readiness",
            reason: "Message-keyed readiness action.",
            action_ids: ["readiness"],
            count: 1
          },
          {
            id: "routing",
            label: "Economy routing",
            reason: "Label-keyed economy action.",
            action_ids: ["Apply economy profile"],
            count: 1
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
    const localActions = await screen.findByLabelText("Agent 建议动作");
    expect(within(localActions).getByText("就绪设置")).toHaveAttribute("title", "Message-keyed readiness action.");
    expect(within(localActions).getByText("经济路由")).toHaveAttribute("title", "Label-keyed economy action.");
    expect(within(localActions).getByText("建议动作")).toBeVisible();
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
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getByRole("heading", { name: "差异摘要" })).toBeVisible();
    expect(within(details).getByText("1 file")).toBeVisible();
    expect(within(details).getByText("web")).toBeVisible();
    expect(within(details).getByText("Raw diff")).toBeVisible();
    expect(within(details).getByText("diff --git a/web b/web")).not.toBeVisible();
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
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getByRole("heading", { name: "差异摘要" })).toBeVisible();
    expect(within(details).getByText("1 file")).toBeVisible();
    expect(within(details).getByText("web")).toBeVisible();
    expect(within(details).getByText("Raw diff")).toBeVisible();
    expect(within(details).getByText("diff --git a/web b/web")).not.toBeVisible();
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

  it("shows a visible error when a local reply action fails", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "next_step",
      ok: true,
      reply: "Run run-ready is waiting for explicit plan approval. Open that run before taking any gated action from a stateless client.",
      recent_run: { run_id: "run-ready", task: "Approve a plan", status: "PLANNED" },
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          run_id: "run-ready",
          safe: true,
          reason: "Open the latest Patchbay run before choosing any gated action."
        }
      ]
    });
    const client = createClient({
      listRuns: vi
        .fn()
        .mockResolvedValueOnce({ runs: [] })
        .mockResolvedValueOnce({ runs: [] })
        .mockRejectedValueOnce(new Error("run list unavailable")),
      agentMessage
    });

    render(<Workbench client={client} pollIntervalMs={0} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalledTimes(1));
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "what should I do next?{enter}");

    expect(await screen.findByText(/waiting for explicit plan approval/i)).toBeVisible();
    await userEvent.click(await screen.findByRole("button", { name: /open latest run/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Open latest run失败：run list unavailable");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
  });

  it("shows a named error when a local reply open-latest action has no run reference", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "next_step",
      ok: true,
      reply: "No run is currently selected.",
      actions: [
        {
          id: "open_latest_run",
          label: "Open latest run",
          kind: "open_run",
          safe: true,
          reason: "Open the latest Patchbay run before choosing any gated action."
        }
      ]
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} pollIntervalMs={0} />);

    await waitFor(() => expect(client.listRuns).toHaveBeenCalledTimes(1));
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "what should I do next?{enter}");

    expect(await screen.findByText("No run is currently selected.")).toBeVisible();
    await userEvent.click(await screen.findByRole("button", { name: /open latest run/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Open latest run失败：No recent run was returned by Patchbay Agent.");
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
      ],
      action_groups: [
        {
          id: "routing",
          label: "Economy routing",
          reason: "Inspect or repair the low-cost write/fix route.",
          action_ids: ["apply_economy_profile"],
          count: 1
        },
        {
          id: "setup",
          label: "Setup and readiness",
          reason: "Run local setup or readiness follow-ups.",
          action_ids: ["open_readiness"],
          count: 1
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
    const localActions = await screen.findByLabelText("Agent 建议动作");
    expect(within(localActions).getByText("经济路由")).toBeVisible();
    expect(within(localActions).getByText("就绪设置")).toBeVisible();
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
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getByRole("heading", { name: "差异摘要" })).toBeVisible();
    expect(within(details).getByText("1 file")).toBeVisible();
    expect(within(details).getByText("web")).toBeVisible();
    expect(within(details).getByText("Raw diff")).toBeVisible();
    expect(within(details).getByText("diff --git a/web b/web")).not.toBeVisible();
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

  it("renders help capabilities from local Agent replies", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "help",
      ok: true,
      reply: "Patchbay Agent can help.",
      capabilities: [
        {
          name: "unattended-approval",
          summary:
            "When a concrete run_id is selected, phrases such as `full access` or `无需向我确认` can approve the plan; final apply still needs apply_approved confirmation."
        },
        {
          name: "economy-profile",
          summary: "Route high-volume write/fix work to the economy provider while plan/review stay supervised."
        },
        {
          name: "agent-skill-contract",
          summary: "Render structured Agent fields instead of parsing prose.",
          contract: {
            kind: "progressive-skill",
            entrypoint: "skills/patchbay/SKILL.md",
            local_only_supported: true,
            references: [
              {
                path: "skills/patchbay/references/agent-contract.md",
                purpose: "Structured actions, action_groups, and failure recovery."
              }
            ],
            commands: ["patchbay skill doctor codex --json", "patchbay skill print codex"]
          }
        }
      ],
      actions: []
    });
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
    const capabilities = await screen.findByLabelText("Agent capabilities");
    expect(within(capabilities).getByText("unattended-approval")).toBeVisible();
    expect(within(capabilities).getByText(/full access/)).toBeVisible();
    expect(within(capabilities).getByText(/无需向我确认/)).toBeVisible();
    expect(within(capabilities).getByText(/apply_approved/)).toBeVisible();
    expect(within(capabilities).getByText("economy-profile")).toBeVisible();
    expect(within(capabilities).getByText("agent-skill-contract")).toBeVisible();
    expect(within(capabilities).getByText("progressive-skill")).toBeVisible();
    expect(within(capabilities).getByText("local-only supported")).toBeVisible();
    expect(within(capabilities).getByText("skills/patchbay/SKILL.md")).toBeVisible();
    expect(within(capabilities).getByText("skills/patchbay/references/agent-contract.md")).toBeVisible();
    expect(within(capabilities).getByText("patchbay skill doctor codex --json")).toBeVisible();
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

  it("renders failed run recovery in selected-run status replies", async () => {
    const failedContext: HandoffContext = {
      ...plannedContext,
      run_id: "run-ready",
      status: "FAILED",
      current_phase: "write",
      timeline: [],
      failure_recovery: {
        stage: "write",
        error: "writer exploded",
        suggested_next_action: "Inspect writer.log and rerun with a narrower task.",
        artifacts: ["writer.log", "events.jsonl"],
        summary: "Run failed in write."
      },
      agent_activity: {
        ...plannedContext.agent_activity!,
        headline: "Patchbay Agent 在实现阶段遇到错误。",
        tone: "failed",
        current_step: {
          phase: "write",
          label: "实现",
          status: "FAILED",
          status_label: "失败",
          summary: "writer exploded"
        },
        conversation_state: {
          ...plannedContext.agent_activity!.conversation_state,
          task: "Ship dashboard",
          status: "FAILED",
          phase: "write",
          next_step: "Inspect writer.log and rerun with a narrower task."
        },
        messages: []
      }
    };
    const recovery = {
      stage: "write",
      error: "writer exploded",
      suggested_next_action: "Inspect writer.log and rerun with a narrower task.",
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
          reason: "Start over."
        }
      ],
      action_groups: [
        { id: "diagnostics", label: "Diagnostics", action_ids: ["inspect_events", "inspect_artifacts"], count: 2 },
        { id: "new_task", label: "New task", action_ids: ["start_new_task"], count: 1 }
      ],
      artifacts: ["writer.log", "events.jsonl"],
      summary: "Run failed in write."
    };
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: "run-ready",
      action: "status",
      ok: true,
      reply: "Run failed in write. Suggested next action: Inspect writer.log.",
      recovery,
      status: {
        run_id: "run-ready",
        task: "Ship dashboard",
        status: "FAILED",
        current_phase: "write",
        error: "writer exploded",
        suggested_next_action: "Inspect writer.log and rerun with a narrower task.",
        failure_recovery: recovery,
        gate_state: { approved: true, tests_passed: false, review_result: null, ready_to_apply: false },
        next_commands: [],
        artifacts: ["writer.log", "events.jsonl"],
        effective_phase_providers: {}
      },
      context: failedContext
    });
    const client = createClient({ agentMessage });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.type(screen.getByLabelText("给 Patchbay Agent 输入消息"), "status{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("status", {
        runId: "run-ready",
        include: { diff: true, review: true },
        background: true
      })
    );
    const panel = await screen.findByLabelText("Agent failure recovery");
    expect(within(panel).getByText("失败恢复")).toBeVisible();
    expect(within(panel).getByText("实现")).toBeVisible();
    expect(within(panel).getByText("Run failed in write.")).toBeVisible();
    expect(within(panel).getByText("writer exploded")).toBeVisible();
    expect(within(panel).getByText("Inspect writer.log and rerun with a narrower task.")).toBeVisible();
    expect(within(panel).getByText("writer.log")).toBeVisible();
    expect(within(panel).getByText("events.jsonl")).toBeVisible();
    expect(within(panel).getByText("诊断")).toBeVisible();
    expect(within(panel).getByText("新任务")).toBeVisible();

    await userEvent.click(within(panel).getByRole("button", { name: "Inspect artifacts" }));
    expect(screen.getByRole("tab", { name: "产物" })).toHaveAttribute("aria-selected", "true");
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    const diagnosticSummary = within(details).getByLabelText("Failure diagnostic summary");
    expect(within(diagnosticSummary).getByText("失败摘要")).toBeVisible();
    expect(within(diagnosticSummary).getByText("实现")).toBeVisible();
    expect(within(diagnosticSummary).getByText("Run failed in write.")).toBeVisible();
    expect(within(diagnosticSummary).getByText("writer exploded")).toBeVisible();
    expect(within(diagnosticSummary).getByText("Inspect writer.log and rerun with a narrower task.")).toBeVisible();
    const artifactInventory = within(details).getByLabelText("Artifact inventory");
    expect(within(artifactInventory).getByText("产物索引")).toBeVisible();
    expect(within(artifactInventory).getAllByText("优先失败产物").length).toBeGreaterThan(0);
    expect(within(details).getByText("当前预览")).toBeVisible();
    expect(within(details).getByText("artifact text")).toBeVisible();

    await userEvent.click(within(panel).getByRole("button", { name: "Start replacement task" }));
    expect(await screen.findByRole("heading", { name: "新任务" })).toBeInTheDocument();
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

  it("runs DeepSeek provider help actions through the local Agent", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "DeepSeek provider setup is available.",
        actions: [
          {
            id: "configure_deepseek_provider",
            label: "Configure DeepSeek provider",
            kind: "local_agent",
            message: "configure DeepSeek provider",
            safe: true,
            reason: "Configure a cheap writer/fixer provider for high-volume work."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "custom_provider_configure",
        ok: true,
        reply: "Provide the DeepSeek writer command.",
        next_actions: []
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
    const localActions = await screen.findByLabelText("Agent 建议动作");
    await userEvent.click(within(localActions).getByRole("button", { name: "Configure DeepSeek provider" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("configure DeepSeek provider", {
        include: { plan: true },
        background: true
      })
    );
    expect(await screen.findByText("Provide the DeepSeek writer command.")).toBeVisible();
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

  it("persists local-only mode after using the help local-mode action", async () => {
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "help",
        ok: true,
        reply: "Local mode shortcut available.",
        actions: [
          {
            id: "use_local_mode",
            label: "Use local mode",
            kind: "local_agent",
            message: "走本地模式，不走 MCP",
            host: "codex",
            safe: true,
            reason: "Use local CLI and Skill actions."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: "run-ready",
        action: "local_mode",
        ok: true,
        reply: "Local-only mode selected.",
        local_mode: { skip_mcp: true },
        actions: []
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
    const localActions = await screen.findByLabelText("Agent 建议动作");
    await userEvent.click(within(localActions).getByRole("button", { name: "Use local mode" }));

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("走本地模式，不走 MCP", {
        include: { plan: true },
        background: true
      })
    );
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

  it("shows a named setup error from the empty state and re-enables setup", async () => {
    const agentMessage = vi.fn().mockRejectedValue(new Error("setup unavailable"));
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "运行 setup" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Codex setup失败：setup unavailable");
    await waitFor(() => expect(screen.getByRole("button", { name: "运行 setup" })).toBeEnabled());
    expect(client.createRun).not.toHaveBeenCalled();
  });

  it("shows local-only economy routing in the start context before creating a run", async () => {
    const setupRouting = {
      profile: "economy",
      economy_configured: true,
      target: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", label: "Reasonix/DeepSeek" },
      summary: "Economy routing profile is active: write reasonix_cli / deepseek-v4-pro, fix reasonix_cli / deepseek-v4-pro.",
      phases: {
        write: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true },
        fix: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true }
      }
    };
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay local setup completed.",
      routing: setupRouting,
      setup: {
        routing: setupRouting,
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

    const startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("Codex setup")).toBeVisible();
    await userEvent.click(within(startContext).getByRole("button", { name: "无 MCP setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP"));
    const updatedContext = await screen.findByLabelText("启动上下文");
    expect(within(updatedContext).getByText("本地模式 / No MCP")).toBeVisible();
    expect(within(updatedContext).getByText("启动环境就绪")).toBeVisible();
    expect(within(updatedContext).getByText("经济路由已启用")).toBeVisible();
    expect(within(updatedContext).getAllByText("reasonix_cli / deepseek-v4-pro").length).toBeGreaterThan(0);
    expect(within(updatedContext).queryByRole("button", { name: "启用经济路由" })).not.toBeInTheDocument();
    expect(client.getStatus).not.toHaveBeenCalled();
  });

  it("shows a named readiness refresh error from the start context", async () => {
    const getDoctor = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        host: "codex",
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
        next_actions: []
      })
      .mockRejectedValueOnce(new Error("doctor unavailable"));
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex" }));
    const startContext = await screen.findByLabelText("启动上下文");
    await userEvent.click(within(startContext).getByRole("button", { name: "打开启动检查" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Codex readiness失败：doctor unavailable");
    await waitFor(() => expect(getDoctor).toHaveBeenCalledTimes(2));
  });

  it("restores persisted local-only mode on startup", async () => {
    window.localStorage.setItem("patchbay.localOnlyMode", "true");
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "codex",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
      next_actions: []
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex", skip_mcp: true }));
    const startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("本地模式 / No MCP")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).queryByRole("combobox", { name: "MCP host" })).not.toBeInTheDocument();
    expect(within(details).getByRole("combobox", { name: "Setup host" })).toHaveValue("codex");
  });

  it("persists Chrome Skill preference and refreshes local-only readiness from the new-task composer", async () => {
    const agentMessage = vi.fn().mockResolvedValueOnce({
      run_id: null,
      action: "local_mode",
      ok: true,
      reply: "Local browser Skill mode selected.",
      local_mode: { skip_mcp: true },
      actions: []
    });
    const getDoctor = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        host: "codex",
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true } },
        next_actions: []
      })
      .mockResolvedValueOnce({
        ok: true,
        host: "codex",
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
        next_actions: []
      });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage,
      getDoctor
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    const composer = screen.getAllByRole("textbox").find((element) => element.tagName.toLowerCase() === "textarea")!;
    await userEvent.type(composer, "use Chrome Skill{enter}");

    await waitFor(() =>
      expect(agentMessage).toHaveBeenCalledWith("use Chrome Skill", {
        include: { plan: true },
        background: true
      })
    );
    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex", skip_mcp: true }));
    expect(window.localStorage.getItem("patchbay.localOnlyMode")).toBe("true");
    const startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("本地模式 / No MCP")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).queryByRole("combobox", { name: "MCP host" })).not.toBeInTheDocument();
    expect(within(details).getByRole("combobox", { name: "Setup host" })).toHaveValue("codex");
  });

  it("restores the persisted setup host on startup", async () => {
    window.localStorage.setItem("patchbay.setupHost", "claude-desktop");
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "claude-desktop",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true } },
      next_actions: []
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor
    });

    render(<Workbench client={client} />);

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "claude-desktop" }));
    const startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("Claude Desktop setup")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    expect(within(details).getByRole("combobox", { name: "MCP host" })).toHaveValue("claude-desktop");
  });

  it("persists local-only setup and reuses it after remount", async () => {
    const agentMessage = vi.fn().mockResolvedValue({
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
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    const { unmount } = render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "本地 setup" }));
    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP"));
    expect(window.localStorage.getItem("patchbay.localOnlyMode")).toBe("true");
    unmount();

    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "codex",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
      next_actions: []
    });
    const nextClient = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor
    });
    render(<Workbench client={nextClient} />);

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex", skip_mcp: true }));
  });

  it("persists setup host choices across remounts", async () => {
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "gemini",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true } },
      next_actions: []
    });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay setup completed for Gemini.",
      setup_host: "gemini",
      setup: {
        doctor: {
          ok: true,
          host: "gemini",
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor,
      agentMessage
    });

    const { unmount } = render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "Setup Gemini" }));
    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("install patchbay for gemini"));
    expect(window.localStorage.getItem("patchbay.setupHost")).toBe("gemini");
    unmount();

    const nextGetDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "gemini",
      root: "C:/repo",
      checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true } },
      next_actions: []
    });
    const nextClient = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      getDoctor: nextGetDoctor
    });
    render(<Workbench client={nextClient} />);

    await waitFor(() => expect(nextGetDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "gemini" }));
    const startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("Gemini setup")).toBeVisible();
  });

  it("rewrites persisted host setup actions to no-MCP setup", async () => {
    window.localStorage.setItem("patchbay.localOnlyMode", "true");
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
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true, skipped: true } },
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
    await userEvent.click(screen.getByRole("button", { name: "Setup Claude Desktop" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("patchbay setup without MCP for claude-desktop"));
    expect(agentMessage).not.toHaveBeenCalledWith("patchbay setup for claude-desktop");
  });

  it("lets the start context leave persisted local-only mode with explicit MCP setup", async () => {
    window.localStorage.setItem("patchbay.localOnlyMode", "true");
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay MCP setup completed.",
      setup_host: "codex",
      setup: {
        doctor: {
          ok: true,
          host: "codex",
          root: "C:/repo",
          checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true }, mcp: { ok: true } },
          next_actions: []
        }
      }
    });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    let startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("本地模式 / No MCP")).toBeVisible();
    await userEvent.click(within(startContext).getByRole("button", { name: "MCP setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("register MCP for Codex"));
    expect(window.localStorage.getItem("patchbay.localOnlyMode")).toBeNull();
    startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("Codex setup")).toBeVisible();
    expect(within(startContext).queryByRole("button", { name: "MCP setup" })).not.toBeInTheDocument();
  });

  it("applies the economy profile from the start context before creating a run", async () => {
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
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      applyConfigProfile,
      getDoctor: vi.fn().mockResolvedValue({
        ok: true,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
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
        next_actions: []
      })
    });

    render(<Workbench client={client} />);

    const startContext = await screen.findByLabelText("启动上下文");
    expect(within(startContext).getByText("经济路由未启用")).toBeVisible();
    await userEvent.click(within(startContext).getByRole("button", { name: "启用经济路由" }));

    await waitFor(() => expect(applyConfigProfile).toHaveBeenCalledWith("economy"));
    expect(await screen.findByText("Economy routing profile applied.")).toBeVisible();
    const updatedContext = await screen.findByLabelText("启动上下文");
    expect(within(updatedContext).getByText("经济路由已启用")).toBeVisible();
    expect(within(updatedContext).getAllByText("reasonix_cli / deepseek-v4-pro").length).toBeGreaterThan(0);
    expect(client.getStatus).not.toHaveBeenCalled();
  });

  it("shows a named economy profile error from the start context and re-enables routing", async () => {
    const applyConfigProfile = vi.fn().mockRejectedValue(new Error("profile unavailable"));
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      applyConfigProfile,
      getDoctor: vi.fn().mockResolvedValue({
        ok: true,
        root: "C:/repo",
        checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
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
        next_actions: []
      })
    });

    render(<Workbench client={client} />);

    const startContext = await screen.findByLabelText("启动上下文");
    await userEvent.click(within(startContext).getByRole("button", { name: "启用经济路由" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Apply economy profile失败：profile unavailable");
    await waitFor(() => expect(within(startContext).getByRole("button", { name: "启用经济路由" })).toBeEnabled());
    expect(client.createRun).not.toHaveBeenCalled();
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

  it("shows setup recommendations and keeps recommendation actions clickable", async () => {
    const recommendation = "Set `commands.reasonix` so the Reasonix/DeepSeek write/fix economy route can actually execute.";
    const agentMessage = vi
      .fn()
      .mockResolvedValueOnce({
        run_id: null,
        action: "setup",
        ok: true,
        reply: "Patchbay setup completed with follow-up steps.",
        setup_host: "codex",
        recommendations: [recommendation],
        next_actions: ["configure reasonix command"],
        setup: {
          ok: true,
          root: "C:/repo",
          recommendations: [recommendation],
          doctor: {
            ok: true,
            root: "C:/repo",
            checks: { repo: { ok: true }, config: { ok: true }, skill: { ok: true } },
            next_actions: [],
            recommendations: [recommendation]
          },
          next_actions: ["configure reasonix command"]
        },
        actions: [
          {
            id: "configure_reasonix_command",
            label: "Configure Reasonix",
            kind: "local_agent",
            message: "configure reasonix command",
            safe: true,
            reason: "Set commands.reasonix before starting write/fix work."
          }
        ]
      })
      .mockResolvedValueOnce({
        run_id: null,
        action: "reasonix_command_configure",
        ok: false,
        reply: "Provide the Reasonix executable path.",
        next_actions: []
      });
    const client = createClient({
      listRuns: vi.fn().mockResolvedValue({ runs: [] }),
      agentMessage
    });

    render(<Workbench client={client} />);

    await screen.findByRole("heading", { name: "新任务" });
    await userEvent.click(screen.getByRole("button", { name: "Setup Codex" }));

    const setupResult = await screen.findByLabelText("Setup result");
    expect(within(setupResult).getByText("建议")).toBeVisible();
    expect(within(setupResult).getByText(recommendation)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Configure Reasonix" }));

    await waitFor(() => expect(agentMessage).toHaveBeenLastCalledWith("configure reasonix command"));
    expect(await screen.findByText("Provide the Reasonix executable path.")).toBeVisible();
  });

  it("runs local-only setup from the readiness panel without creating a run", async () => {
    const setupRouting = {
      profile: "economy",
      economy_configured: true,
      target: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", label: "Reasonix/DeepSeek" },
      summary: "Economy routing profile is active: write reasonix_cli / deepseek-v4-pro, fix reasonix_cli / deepseek-v4-pro.",
      phases: {
        write: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true },
        fix: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true }
      },
      workload_policy: {
        summary: "Simple high-volume write/fix work uses the low-cost Reasonix/DeepSeek route; plan/review stay on supervision models.",
        target_label: "Reasonix/DeepSeek",
        economy_phases: ["write", "fix"],
        supervision_phases: ["plan", "review"],
        phase_roles: { plan: "supervision", write: "economy", fix: "economy", review: "supervision" }
      }
    };
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay local setup completed.",
      routing: setupRouting,
      setup: {
        routing: setupRouting,
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
    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getByText("Simple high-volume write/fix work uses the low-cost Reasonix/DeepSeek route; plan/review stay on supervision models.")).toBeVisible();
    expect(within(routingResult).getByText("write/fix → Reasonix/DeepSeek")).toBeVisible();
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

  it("lets the readiness panel leave persisted local-only mode with explicit MCP setup", async () => {
    window.localStorage.setItem("patchbay.localOnlyMode", "true");
    const getDoctor = vi.fn().mockResolvedValue({
      ok: true,
      host: "codex",
      root: "C:/repo",
      checks: { repo: { ok: true }, mcp: { ok: true, skipped: true } },
      next_actions: []
    });
    const agentMessage = vi.fn().mockResolvedValue({
      run_id: null,
      action: "setup",
      ok: true,
      reply: "Patchbay MCP setup completed for Claude Desktop.",
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

    await waitFor(() => expect(getDoctor).toHaveBeenCalledWith({ include_mcp: false, host: "codex", skip_mcp: true }));
    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    await userEvent.click(screen.getByRole("tab", { name: "就绪" }));
    const details = screen.getByRole("complementary", { name: "诊断详情" });
    await userEvent.selectOptions(within(details).getByRole("combobox", { name: "Setup host" }), "claude-desktop");
    await userEvent.click(within(details).getByRole("button", { name: "MCP setup" }));

    await waitFor(() => expect(agentMessage).toHaveBeenCalledWith("register MCP for Claude Desktop"));
    expect(window.localStorage.getItem("patchbay.localOnlyMode")).toBeNull();
    expect(within(details).getByRole("combobox", { name: "MCP host" })).toHaveValue("claude-desktop");
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
        },
        workload_policy: {
          summary: "Simple high-volume write/fix work uses the low-cost Reasonix/DeepSeek route; plan/review stay on supervision models.",
          target_label: "Reasonix/DeepSeek",
          economy_phases: ["write", "fix"],
          supervision_phases: ["plan", "review"],
          phase_roles: { plan: "supervision", write: "economy", fix: "economy", review: "supervision" }
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
      ],
      action_groups: [
        {
          id: "setup",
          label: "Setup and readiness",
          reason: "Open readiness checks after applying the economy profile.",
          action_ids: ["open_readiness"],
          count: 1
        },
        {
          id: "new_task",
          label: "New task",
          reason: "Start a task with economy write/fix routing enabled.",
          action_ids: ["start_new_task"],
          count: 1
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
    const localActions = await screen.findByLabelText("Agent 建议动作");
    expect(within(localActions).getByText("就绪设置")).toHaveAttribute("title", "Open readiness checks after applying the economy profile.");
    expect(within(localActions).getByText("新任务")).toHaveAttribute("title", "Start a task with economy write/fix routing enabled.");
    expect(screen.getByRole("button", { name: "Open readiness" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Start new task" })).toBeVisible();
    const routingResult = await screen.findByLabelText("Routing result");
    expect(within(routingResult).getByText("经济路由已启用")).toBeVisible();
    expect(
      within(routingResult).getByText("Simple high-volume write/fix work uses the low-cost Reasonix/DeepSeek route; plan/review stay on supervision models.")
    ).toBeVisible();
    expect(within(routingResult).getByText("write/fix → Reasonix/DeepSeek")).toBeVisible();
    expect(within(routingResult).getByText("plan/review → supervision")).toBeVisible();
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
        routing: {
          profile: "economy",
          economy_configured: true,
          target: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix", label: "Reasonix/DeepSeek" },
          summary: "Economy routing profile is active: write reasonix_cli / deepseek-v4-pro, fix reasonix_cli / deepseek-v4-pro.",
          phases: {
            write: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true },
            fix: { configured: { provider: "reasonix_cli", model: "deepseek-v4-pro", command_key: "reasonix" }, configured_economy: true }
          },
          workload_policy: {
            summary: "Simple high-volume write/fix work uses the low-cost Reasonix/DeepSeek route; plan/review stay on supervision models.",
            target_label: "Reasonix/DeepSeek",
            economy_phases: ["write", "fix"],
            supervision_phases: ["plan", "review"],
            phase_roles: { plan: "supervision", write: "economy", fix: "economy", review: "supervision" }
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
    expect(
      within(details).getByText("Simple high-volume write/fix work uses the low-cost Reasonix/DeepSeek route; plan/review stay on supervision models.")
    ).toBeVisible();
    expect(within(details).getByText("write/fix → Reasonix/DeepSeek")).toBeVisible();
    expect(within(details).getByText("plan/review → supervision")).toBeVisible();
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

  it("shows a visible error when autopilot action execution fails", async () => {
    const agentMessage = vi.fn().mockRejectedValue(new Error("writer route unavailable"));
    const client = createClient({
      agentMessage,
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

    expect(await screen.findByRole("alert")).toHaveTextContent("开始实现失败：writer route unavailable");
    await waitFor(() => expect(screen.getByRole("button", { name: /执行/ })).toBeEnabled());
    expect(client.runAction).not.toHaveBeenCalled();
  });

  it("shows a visible error when confirmed gate execution fails", async () => {
    const agentMessage = vi.fn().mockRejectedValue(new Error("approval token expired"));
    const client = createClient({
      agentMessage,
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
    await userEvent.click(screen.getByRole("button", { name: /^确认$/ }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "确认批准计划" })).getByRole("button", { name: "批准" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("批准计划失败：approval token expired");
    expect(screen.queryByRole("dialog", { name: "确认批准计划" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /^确认$/ })).toBeEnabled());
  });

  it("shows a visible error when a safe diagnostic action fails", async () => {
    const listRuns = vi
      .fn()
      .mockResolvedValueOnce({
        runs: [
          { run_id: "run-ready", task: "Ship dashboard", status: "REVIEWED_PASS" },
          {
            run_id: "run-failed",
            task: "Failed run",
            status: "FAILED",
            inbox: {
              key: "failed",
              label: "Failed",
              summary: "Open the failed run for diagnostics.",
              priority: 70,
              safe: true,
              requires_confirmation: false,
              next_action: {
                id: "open_failed_run",
                label: "Open failed run",
                kind: "open_run",
                run_id: "run-failed",
                tab: "Log",
                safe: true,
                reason: "Open the failed run without advancing gates."
              }
            }
          }
        ],
        inbox: {
          total: 2,
          active_count: 0,
          confirmation_required_count: 0,
          safe_action_count: 1,
          focus_run_id: "run-ready",
          summary: "2 runs; 1 failed run can be inspected.",
          groups: [{ key: "failed", label: "Failed", count: 1, run_ids: ["run-failed"] }]
        }
      })
      .mockRejectedValueOnce(new Error("run list unavailable"));
    const client = createClient({ listRuns });

    render(<Workbench client={client} pollIntervalMs={0} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await userEvent.click(screen.getByRole("button", { name: "Run inbox action: Open failed run" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Open failed run失败：run list unavailable");
    expect(client.runAction).not.toHaveBeenCalled();
    expect(client.apply).not.toHaveBeenCalled();
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
    const thread = screen.getByLabelText("Patchbay Agent 对话线程");
    expect(within(thread).getAllByText("等待批准")).toHaveLength(1);
  });

  it("shows a named error when selected-run polling fails", async () => {
    const client = createClient({
      getContext: vi.fn().mockResolvedValueOnce(readyContext).mockRejectedValueOnce(new Error("poll unavailable"))
    });

    render(<Workbench client={client} pollIntervalMs={10} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await waitFor(() => expect(client.getContext).toHaveBeenCalledWith("run-ready", { since_event: 1 }));

    expect(await screen.findByRole("alert")).toHaveTextContent("轮询运行更新失败：poll unavailable");
  });

  it("skips idle selected-run polling while the document is hidden", async () => {
    setDocumentVisibility("hidden");
    const getContext = vi.fn().mockResolvedValue(readyContext);
    const client = createClient({ getContext });

    render(<Workbench client={client} pollIntervalMs={10} />);

    await screen.findByRole("heading", { name: "Ship dashboard" });
    await waitFor(() => expect(getContext).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => window.setTimeout(resolve, 60));

    expect(getContext).toHaveBeenCalledTimes(1);

    setDocumentVisibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));

    await waitFor(() => expect(getContext).toHaveBeenCalledWith("run-ready", { since_event: 1 }));
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
        },
        {
          id: "cancel_background_job",
          label: "Cancel background job",
          kind: "local_agent",
          run_id: "run-ready",
          message: "cancel background job",
          safe: true,
          reason: "Stop the active background worker for this run without approving, applying, or advancing gates."
        }
      ]
    };
    const runningContext: HandoffContext = {
      ...plannedContext,
      run_id: "run-ready",
      status: "RUNNING",
      current_phase: "write",
      background_job: backgroundJob,
      next_actions: [
        {
          name: "poll_context",
          id: "poll_context",
          label: "Poll context",
          safe: true,
          tool: "patchbay_context",
          kind: "local_agent",
          run_id: "run-ready",
          message: "context",
          requires_human_confirmation: false,
          reason: "Refresh the latest handoff context for this background run."
        },
        {
          name: "poll_status",
          id: "poll_status",
          label: "Poll status",
          safe: true,
          tool: "patchbay_status",
          kind: "local_agent",
          run_id: "run-ready",
          message: "status",
          requires_human_confirmation: false,
          reason: "Refresh this background run without approving, continuing, or applying changes."
        },
        {
          name: "poll_events",
          id: "poll_events",
          label: "Poll events",
          safe: true,
          tool: "patchbay_events",
          kind: "local_agent",
          run_id: "run-ready",
          message: "events",
          requires_human_confirmation: false,
          reason: "Read the background run event stream without advancing any phase."
        },
        {
          name: "cancel_background_job",
          id: "cancel_background_job",
          label: "Cancel background job",
          safe: true,
          tool: "patchbay_agent",
          kind: "local_agent",
          run_id: "run-ready",
          message: "cancel background job",
          requires_human_confirmation: false,
          reason: "Stop the active background worker for this run without approving, applying, or advancing gates."
        }
      ],
      action_groups: [
        {
          id: "background_polling",
          label: "Background polling",
          action_ids: ["poll_context", "poll_status", "poll_events"],
          count: 3
        },
        {
          id: "background_control",
          label: "Background control",
          action_ids: ["cancel_background_job"],
          count: 1
        }
      ],
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
        headline: "Patchbay Agent 正在后台执行实现阶段。",
        tone: "running",
        background_job: backgroundJob,
        current_step: { phase: "write", label: "实现", status: "RUNNING", status_label: "运行中", summary: "后台任务正在运行，状态会自动刷新。" },
        next_action: {
          name: "poll_context",
          id: "poll_context",
          label: "Poll context",
          safe: true,
          tool: "patchbay_context",
          kind: "local_agent",
          run_id: "run-ready",
          message: "context",
          requires_human_confirmation: false,
          reason: "Refresh the latest handoff context for this background run."
        },
        conversation_state: {
          task: "Background implementation",
          status: "RUNNING",
          status_label: "运行中",
          phase: "write",
          phase_label: "实现",
          tone: "running",
          next_step: "后台任务正在实现阶段运行。可以安全执行“Poll context”刷新进度，不会推进任何门禁。",
          composer_placeholder: "后台运行中，点击“Poll context”刷新",
          suggestions: [
            {
              id: "poll_context",
              label: "Poll context",
              action: "poll_context",
              safe: true,
              tool: "patchbay_context",
              kind: "local_agent",
              run_id: "run-ready",
              message: "context",
              reason: "Refresh the latest handoff context for this background run."
            },
            {
              id: "poll_status",
              label: "Poll status",
              action: "poll_status",
              safe: true,
              tool: "patchbay_status",
              kind: "local_agent",
              run_id: "run-ready",
              message: "status",
              reason: "Refresh this background run without approving, continuing, or applying changes."
            },
            {
              id: "poll_events",
              label: "Poll events",
              action: "poll_events",
              safe: true,
              tool: "patchbay_events",
              kind: "local_agent",
              run_id: "run-ready",
              message: "events",
              reason: "Read the background run event stream without advancing any phase."
            },
            {
              id: "cancel_background_job",
              label: "Cancel background job",
              action: "cancel_background_job",
              safe: true,
              tool: "patchbay_agent",
              kind: "local_agent",
              run_id: "run-ready",
              message: "cancel background job",
              reason: "Stop the active background worker for this run without approving, applying, or advancing gates."
            }
          ]
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
      getContext: vi.fn().mockResolvedValue(runningContext),
      agentMessage: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        action: "background_cancel",
        ok: true,
        canceled: true,
        reply: "Canceled background job for run run-ready.",
        background_job: { ...backgroundJob, active: false, status: "canceled" }
      })
    });

    render(<Workbench client={client} />);

    expect(await screen.findByText("Patchbay Agent 正在后台执行实现阶段。")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Background job status")).toHaveLength(2);
    expect(screen.getAllByText(/后台运行中/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/pid 4321/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Open background run" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open activity" })).toBeInTheDocument();
    expect(screen.getByText("后台轮询")).toBeInTheDocument();
    expect(screen.getByText("后台控制")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Poll status" }).length).toBeGreaterThan(1);
    expect(screen.getAllByRole("button", { name: "Poll context" }).length).toBeGreaterThan(1);
    expect(screen.getAllByRole("button", { name: "Poll events" }).length).toBeGreaterThan(1);
    expect(screen.getAllByRole("button", { name: "Cancel background job" }).length).toBeGreaterThan(1);
    await userEvent.click(screen.getByRole("button", { name: "Open activity" }));
    expect(screen.getByRole("tab", { selected: true })).toBeInTheDocument();
    const statusCalls = vi.mocked(client.getStatus).mock.calls.length;
    await userEvent.click(screen.getAllByRole("button", { name: "Poll status" }).at(-1)!);
    await waitFor(() => expect(client.getStatus).toHaveBeenCalledTimes(statusCalls + 1));
    const contextCalls = vi.mocked(client.getContext).mock.calls.length;
    await userEvent.click(screen.getAllByRole("button", { name: "Poll context" }).at(-1)!);
    await waitFor(() => expect(client.getContext).toHaveBeenCalledTimes(contextCalls + 1));
    await userEvent.click(screen.getAllByRole("button", { name: "Cancel background job" }).at(-1)!);
    await waitFor(() => expect(client.agentMessage).toHaveBeenCalledWith("cancel background job", { runId: "run-ready" }));
    expect(screen.getByRole("heading", { name: "Background implementation" })).toBeInTheDocument();
    expect(screen.getAllByText(/1.5s/).length).toBeGreaterThan(0);
    expect(screen.getByText("后台任务运行中")).toBeInTheDocument();
    expect(screen.getByText("运行中 · 实现")).toBeInTheDocument();
    expect(screen.getByLabelText("给 Patchbay Agent 输入消息")).toBeDisabled();
    expect(screen.getByRole("button", { name: "发送消息" })).toBeDisabled();
    expect(client.runAction).not.toHaveBeenCalledWith("run-ready", "poll_context");
    expect(client.runAction).not.toHaveBeenCalledWith("run-ready", "cancel_background_job");
    expect(client.apply).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /开始实现/ })).not.toBeInTheDocument();
  });

  it("auto-refreshes active background jobs until completion", async () => {
    setDocumentVisibility("hidden");
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
      next_actions: [
        {
          name: "inspect_events",
          id: "inspect_events",
          label: "Inspect events",
          kind: "diagnostic_tab",
          tool: "diagnostic_tab",
          tab: "Trace",
          safe: true,
          requires_human_confirmation: false,
          reason: "Open event timeline."
        }
      ],
      timeline: [],
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
        action_groups: [
          {
            id: "diagnostics",
            label: "Diagnostics",
            action_ids: ["inspect_events", "inspect_artifacts"],
            count: 2
          },
          {
            id: "new_task",
            label: "New task",
            action_ids: ["start_new_task"],
            count: 1
          }
        ],
        artifacts: ["PLAN.md", "plan.json", "events.jsonl"],
        summary: "Run failed in plan; inspect PLAN.md, plan.json, events.jsonl before taking another action."
      },
      action_groups: [
        {
          id: "diagnostics",
          label: "Diagnostics",
          action_ids: ["inspect_events"],
          count: 1
        }
      ],
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
          suggestions: [
            {
              id: "inspect_events",
              label: "Inspect events",
              action: "inspect_events",
              kind: "diagnostic_tab",
              tab: "Trace",
              safe: true,
              requires_human_confirmation: false,
              reason: "Open event timeline."
            }
          ]
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
          action_groups: [
            {
              id: "diagnostics",
              label: "Diagnostics",
              action_ids: ["inspect_events", "inspect_artifacts"],
              count: 2
            },
            {
              id: "new_task",
              label: "New task",
              action_ids: ["start_new_task"],
              count: 1
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
    expect(within(card).getByText("诊断")).toBeVisible();
    expect(within(card).getByText("新任务")).toBeVisible();
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
