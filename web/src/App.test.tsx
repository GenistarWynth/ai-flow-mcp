import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Workbench } from "./App";
import type { PatchbayClient } from "./api";

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
  it("renders runs, phase progress, timeline fields, and provider details", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    expect(await screen.findByText("Patchbay 可视化工作台")).toBeInTheDocument();
    expect(await screen.findByText("Ship dashboard")).toBeInTheDocument();
    expect(screen.getByText("Needs fix")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "run-ready" })).toBeInTheDocument();
    expect(await screen.findByText(/当前阶段：应用/)).toBeInTheDocument();
    expect(screen.getByText("门禁状态")).toBeInTheDocument();
    expect(await screen.findByText("patchbay_review")).toBeInTheDocument();
    expect(screen.getAllByText("审查")).not.toHaveLength(0);
    expect(screen.getByText(".ai/runs/run-ready/REVIEW.md")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "提供方" }));

    expect(screen.getAllByText("reasonix_cli")).not.toHaveLength(0);
    expect(screen.getAllByText("codex_cli")).not.toHaveLength(0);
    expect(client.getTrace).toHaveBeenCalledWith("run-ready");
  });

  it("filters the run list by search and status", async () => {
    const client = createClient();

    render(<Workbench client={client} />);

    await screen.findByText("Ship dashboard");
    await userEvent.selectOptions(screen.getByLabelText("状态筛选"), "REVIEWED_CHANGES_REQUESTED");
    await userEvent.type(screen.getByLabelText("搜索运行"), "fix");

    expect(screen.queryByText("Ship dashboard")).not.toBeInTheDocument();
    expect(screen.getByText("Needs fix")).toBeInTheDocument();
  });

  it("polls trace incrementally after the initial load", async () => {
    const client = createClient({
      getTrace: vi
        .fn()
        .mockResolvedValueOnce({
          total: 2,
          events: [
            {
              index: 0,
              timestamp: "2026-05-24T10:02:00Z",
              agent: "codex_cli",
              phase: "review",
              action: "start",
              tool: "patchbay_review",
              path: ".ai/runs/run-ready/REVIEW.md",
              status: "RUNNING",
              detail: "reviewing"
            },
            {
              index: 1,
              timestamp: "2026-05-24T10:03:00Z",
              agent: "codex_cli",
              phase: "review",
              action: "success",
              tool: "patchbay_review",
              path: ".ai/runs/run-ready/REVIEW.md",
              status: "PASS",
              detail: "ready"
            }
          ]
        })
        .mockResolvedValueOnce({
          total: 3,
          events: [
            {
              index: 2,
              timestamp: "2026-05-24T10:04:00Z",
              agent: "patchbay",
              phase: "apply",
              action: "gate",
              status: "READY",
              detail: "ready to apply"
            }
          ]
        })
    });

    render(<Workbench client={client} pollIntervalMs={20} />);

    expect(await screen.findByText("ready")).toBeInTheDocument();
    await waitFor(() => {
      expect(client.getTrace).toHaveBeenLastCalledWith("run-ready", { since: 2 });
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
    const client = createClient({
      getStatus: vi.fn().mockResolvedValue({
        run_id: "run-ready",
        status: "REVIEWED_PASS",
        current_phase: "apply",
        gate_state: { ready_to_apply: false },
        next_commands: [],
        artifacts: [],
        effective_phase_providers: {}
      })
    });

    render(<Workbench client={client} />);

    expect(await screen.findByRole("button", { name: /应用已审查 diff/i })).toBeDisabled();
  });
});
