import { describe, expect, it, vi } from "vitest";
import {
  applyRun,
  cleanupRun,
  createRun,
  fetchArtifact,
  fetchConfig,
  fetchContext,
  fetchDiff,
  fetchRuns,
  fetchStatus,
  fetchTrace,
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

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/runs",
      "/api/runs/run-1/status",
      "/api/runs/run-1/context?since_event=2&include_trace=true",
      "/api/runs/run-1/trace?since=3",
      "/api/runs/run-1/diff",
      "/api/runs/run-1/artifact/PLAN.md?tail=60",
      "/api/config"
    ]);
  });

  it("posts phase actions and destructive actions through explicit endpoints", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ ok: true }));
    const client = { fetch: fetchMock };

    await postRunAction("run-1", "write", client);
    await applyRun("run-1", client);
    await cleanupRun("run-1", client);

    expect(fetchMock.mock.calls).toMatchObject([
      ["/api/runs/run-1/actions/write", { method: "POST" }],
      ["/api/runs/run-1/actions/apply", { method: "POST" }],
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
});
