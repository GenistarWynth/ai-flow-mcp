export type RunSummary = {
  run_id: string;
  status?: string;
  task?: string;
  updated_at?: string;
  run_dir?: string;
};

export type GateState = {
  approved?: boolean;
  tests_passed?: boolean;
  review_result?: string | null;
  ready_to_apply?: boolean;
};

export type PhaseProvider = {
  provider?: string;
  model?: string;
  command_key?: string;
};

export type RunStatus = {
  run_id: string;
  task?: string;
  status?: string;
  current_phase?: string;
  tests_passed?: boolean;
  review_result?: string | null;
  gate_state?: GateState;
  next_commands?: string[];
  artifacts?: string[];
  effective_phase_providers?: Record<string, PhaseProvider>;
};

export type TraceEntry = {
  index?: number;
  seq?: number;
  source?: string;
  timestamp?: string;
  agent?: string;
  provider?: string;
  model?: string;
  phase?: string;
  action?: string;
  tool?: string;
  path?: string;
  status?: string;
  detail?: string;
  next_action?: string;
  artifact_paths?: string[];
  duration_ms?: number;
  raw?: unknown;
};

export type NextAction = {
  name: string;
  safe: boolean;
  tool: string;
  requires_human_confirmation: boolean;
  reason: string;
};

export type HandoffArtifact = {
  name: string;
  purpose: string;
  path: string;
};

export type ProviderTrailEntry = {
  phase?: string;
  provider?: string;
  model?: string;
  status?: string;
  timestamp?: string;
};

export type HandoffContext = {
  run_id: string;
  handoff_summary?: string;
  status?: string;
  current_phase?: string;
  gate_state?: GateState;
  next_actions?: NextAction[];
  provider_trail?: ProviderTrailEntry[];
  artifacts?: HandoffArtifact[];
  timeline?: TraceEntry[];
  cursors?: { event?: number; trace?: number };
};

export type PatchbayClient = {
  listRuns(): Promise<{ count?: number; runs: RunSummary[] }>;
  getStatus(runId: string): Promise<RunStatus>;
  getContext(runId: string, options?: { since_event?: number; since_trace?: number; include_trace?: boolean }): Promise<HandoffContext>;
  getTrace(runId: string, options?: { since?: number; phase?: string }): Promise<{ total?: number; trace?: TraceEntry[]; events?: TraceEntry[] }>;
  getDiff(runId: string): Promise<{ text?: string; diff?: string }>;
  getArtifact(runId: string, artifact: string, options?: { tail?: number }): Promise<{ text: string }>;
  getConfig(): Promise<unknown>;
  runAction(runId: string, action: string): Promise<unknown>;
  apply(runId: string): Promise<unknown>;
  cleanup(runId: string): Promise<unknown>;
};

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type ClientOptions = { fetch?: FetchLike };

const defaultClient: ClientOptions = {
  fetch: (...args) => fetch(...args)
};

async function requestJson<T>(url: string, client: ClientOptions = defaultClient, init?: RequestInit): Promise<T> {
  const doFetch = client.fetch ?? defaultClient.fetch;
  if (!doFetch) throw new Error("fetch is not available");
  const response = await doFetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Patchbay API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

export function fetchRuns(client?: ClientOptions) {
  return requestJson<{ count?: number; runs: RunSummary[] }>("/api/runs", client);
}

export function fetchStatus(runId: string, client?: ClientOptions) {
  return requestJson<RunStatus>(`/api/runs/${encodeURIComponent(runId)}/status`, client);
}

export function fetchContext(
  runId: string,
  options: { since_event?: number; since_trace?: number; include_trace?: boolean } = {},
  client?: ClientOptions
) {
  return requestJson<HandoffContext>(`/api/runs/${encodeURIComponent(runId)}/context${query(options)}`, client);
}

export function fetchTrace(runId: string, options: { since?: number; phase?: string } = {}, client?: ClientOptions) {
  return requestJson<{ total?: number; trace?: TraceEntry[]; events?: TraceEntry[] }>(
    `/api/runs/${encodeURIComponent(runId)}/trace${query(options)}`,
    client
  );
}

export function fetchDiff(runId: string, client?: ClientOptions) {
  return requestJson<{ text?: string; diff?: string }>(`/api/runs/${encodeURIComponent(runId)}/diff`, client);
}

export function fetchArtifact(runId: string, artifact: string, options: { tail?: number } = {}, client?: ClientOptions) {
  return requestJson<{ text: string }>(
    `/api/runs/${encodeURIComponent(runId)}/artifact/${encodeURIComponent(artifact)}${query(options)}`,
    client
  );
}

export function fetchConfig(client?: ClientOptions) {
  return requestJson<unknown>("/api/config", client);
}

export function postRunAction(runId: string, action: string, client?: ClientOptions) {
  return requestJson<unknown>(`/api/runs/${encodeURIComponent(runId)}/actions/${encodeURIComponent(action)}`, client, { method: "POST" });
}

export function applyRun(runId: string, client?: ClientOptions) {
  return requestJson<unknown>(`/api/runs/${encodeURIComponent(runId)}/actions/apply`, client, { method: "POST" });
}

export function cleanupRun(runId: string, client?: ClientOptions) {
  return requestJson<unknown>(`/api/runs/${encodeURIComponent(runId)}/actions/cleanup`, client, { method: "POST" });
}

export function createPatchbayClient(client?: ClientOptions): PatchbayClient {
  return {
    listRuns: () => fetchRuns(client),
    getStatus: (runId) => fetchStatus(runId, client),
    getContext: (runId, options) => fetchContext(runId, options, client),
    getTrace: (runId, options) => fetchTrace(runId, options, client),
    getDiff: (runId) => fetchDiff(runId, client),
    getArtifact: (runId, artifact, options) => fetchArtifact(runId, artifact, options, client),
    getConfig: () => fetchConfig(client),
    runAction: (runId, action) => postRunAction(runId, action, client),
    apply: (runId) => applyRun(runId, client),
    cleanup: (runId) => cleanupRun(runId, client)
  };
}
