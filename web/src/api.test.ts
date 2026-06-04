import { describe, expect, it, vi } from "vitest";
import {
  applyRun,
  applyConfigProfile,
  cleanupRun,
  createProvider,
  createRun,
  fetchArtifact,
  fetchConfig,
  fetchConfigProfile,
  fetchContext,
  fetchDiff,
  fetchDoctor,
  fetchRuns,
  fetchStatus,
  fetchTrace,
  postAgentMessage,
  postRunAction
} from "./api";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("Patchbay API client", () => {
  it("maps workbench reads to the planned local endpoints", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/runs")) return jsonResponse({ runs: [] });
      if (url.endsWith("/api/runs/run-1/status")) return jsonResponse({ run_id: "run-1" });
      if (url.endsWith("/api/runs/run-1/context?since_event=2&include_trace=true")) return jsonResponse({ run_id: "run-1" });
      if (url.endsWith("/api/runs/run-1/trace?since=3")) return jsonResponse({ events: [] });
      if (url.endsWith("/api/runs/run-1/diff")) return jsonResponse({ diff: "diff --git" });
      if (url.endsWith("/api/runs/run-1/artifact/PLAN.md?tail=60")) return jsonResponse({ text: "plan" });
      if (url.endsWith("/api/config")) return jsonResponse({ phases: {} });
      if (url.endsWith("/api/config/profile")) return jsonResponse({ profile: "custom" });
      if (url.endsWith("/api/doctor")) return jsonResponse({ ok: false, checks: {} });
      throw new Error(`unexpected URL ${url}`);
    });

    const client = { fetch: fetchMock };

    await fetchRuns(client);
    await fetchStatus("run-1", client);
    await fetchContext("run-1", { since_event: 2, include_trace: true }, client);
    await fetchTrace("run-1", { since: 3 }, client);
    await fetchDiff("run-1", client);
    await fetchArtifact("run-1", "PLAN.md", { tail: 60 }, client);
    await fetchConfig(client);
    await fetchConfigProfile(client);
    await fetchDoctor({}, client);

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/runs",
      "/api/runs/run-1/status",
      "/api/runs/run-1/context?since_event=2&include_trace=true",
      "/api/runs/run-1/trace?since=3",
      "/api/runs/run-1/diff",
      "/api/runs/run-1/artifact/PLAN.md?tail=60",
      "/api/config",
      "/api/config/profile",
      "/api/doctor"
    ]);
  });

  it("posts phase actions and destructive actions through explicit endpoints", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ ok: true }));
    const client = { fetch: fetchMock };

    await postRunAction("run-1", "write", client);
    await applyRun("run-1", "apply_approved", client);
    await cleanupRun("run-1", client);

    expect(fetchMock.mock.calls).toMatchObject([
      ["/api/runs/run-1/actions/write", { method: "POST" }],
      [
        "/api/runs/run-1/actions/apply",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirmation: "apply_approved" })
        }
      ],
      ["/api/runs/run-1/actions/cleanup", { method: "POST" }]
    ]);
  });

  it("creates a plan run from the composer endpoint", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ run_id: "run-new" }));
    const client = { fetch: fetchMock };

    await createRun("build a chat workbench", { background: true }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: "build a chat workbench", background: true })
      })
    );
  });

  it("posts conversational agent messages with run and confirmation context", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ run_id: "run-1", ok: true }));
    const client = { fetch: fetchMock };

    await postAgentMessage("approve", { runId: "run-1", confirmation: "plan_approved", include: { plan: true }, background: true }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agent/message",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "approve",
          run_id: "run-1",
          confirmation: "plan_approved",
          include: { plan: true },
          background: true
        })
      })
    );
  });

  it("passes doctor query options and local command payloads explicitly", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ ok: true }));
    const client = { fetch: fetchMock };

    await fetchDoctor({ include_mcp: false, skill_path: "C:/tmp/skills", host: "claude-desktop", skip_mcp: true }, client);
    await postAgentMessage("apply economy profile", {}, client);
    await postAgentMessage("continue", { maxFixRounds: 2 }, client);

    const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls[0][0]).toBe("/api/doctor?include_mcp=false&skill_path=C%3A%2Ftmp%2Fskills&host=claude-desktop&skip_mcp=true");
    expect(calls[1]).toEqual([
      "/api/agent/message",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "apply economy profile",
          run_id: "",
          confirmation: "none",
          include: {},
          background: false
        })
      })
    ]);
    expect(JSON.parse(String(calls[2][1]?.body))).toMatchObject({
      message: "continue",
      max_fix_rounds: 2
    });
  });

  it("uses explicit config profile endpoints for economy routing", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ profile: "economy" }));
    const client = { fetch: fetchMock };

    await fetchConfigProfile(client);
    await applyConfigProfile("economy", client);

    const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls[0][0]).toBe("/api/config/profile");
    expect(calls[1]).toEqual([
      "/api/config/profile/apply",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: "economy" })
      }
    ]);
  });

  it("creates custom providers and can activate economy routing", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ provider: "cheap_writer", activated_economy: true }));
    const client = { fetch: fetchMock };

    await createProvider(
      {
        provider_id: "cheap_writer",
        roles: ["write", "fix"],
        command: "deepseek-writer",
        args: ["--json"],
        prompt_mode: "stdin",
        output_contract: "writer_diff",
        activate_economy: true,
        economy_model: "deepseek-chat",
        economy_label: "DeepSeek cheap writer"
      },
      client
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/providers",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: "cheap_writer",
          roles: ["write", "fix"],
          command: "deepseek-writer",
          args: ["--json"],
          prompt_mode: "stdin",
          output_contract: "writer_diff",
          activate_economy: true,
          economy_model: "deepseek-chat",
          economy_label: "DeepSeek cheap writer"
        })
      })
    );
  });
});
