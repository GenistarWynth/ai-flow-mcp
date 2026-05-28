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

export type ProviderUsage = {
  phase?: string;
  provider?: string;
  model?: string;
  events?: number;
  duration_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  cached_tokens?: number;
  total_tokens?: number;
  cost?: {
    known?: boolean;
    currency?: string;
    estimated_total?: number | null;
  };
  token_usage?: {
    known?: boolean;
    input_tokens?: number | null;
    output_tokens?: number | null;
    cached_tokens?: number | null;
    total_tokens?: number | null;
  };
};

export type RunMetrics = {
  duration_known?: boolean;
  duration_source?: string;
  total_duration_ms?: number | null;
  phase_durations_ms?: Record<string, number>;
  phase_attempts?: Record<string, number>;
  event_count?: number;
  trace_count?: number;
  provider_usage?: ProviderUsage[];
  cost?: {
    known?: boolean;
    currency?: string;
    estimated_total?: number | null;
    by_phase?: Record<string, {
      known?: boolean;
      currency?: string;
      estimated_total?: number;
    }>;
  };
  token_usage?: {
    known?: boolean;
    input_tokens?: number | null;
    output_tokens?: number | null;
    cached_tokens?: number | null;
    total_tokens?: number | null;
    by_phase?: Record<string, {
      known?: boolean;
      input_tokens?: number;
      output_tokens?: number;
      cached_tokens?: number;
      total_tokens?: number;
    }>;
  };
};

export type RunStatus = {
  run_id: string;
  task?: string;
  status?: string;
  current_phase?: string;
  error?: string | null;
  suggested_next_action?: string | null;
  tests_passed?: boolean;
  review_result?: string | null;
  gate_state?: GateState;
  next_commands?: string[];
  artifacts?: string[];
  effective_phase_providers?: Record<string, PhaseProvider>;
  run_metrics?: RunMetrics;
};

export type DoctorCheck = {
  ok?: boolean;
  skipped?: boolean;
  note?: string;
  error?: string | null;
  [key: string]: unknown;
};

export type DoctorReport = {
  ok?: boolean;
  root?: string;
  checks?: Record<string, DoctorCheck>;
  next_actions?: string[];
  recommendations?: string[];
};

export type SetupResult = {
  ok?: boolean;
  dry_run?: boolean;
  setup_host?: string;
  root?: string;
  doctor?: DoctorReport;
  mcp?: {
    host?: string;
    command?: string;
    executed?: boolean;
    dry_run?: boolean;
    note?: string;
    error?: string | null;
    [key: string]: unknown;
  };
  next_actions?: string[];
  [key: string]: unknown;
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

export type AgentTone = "idle" | "running" | "ready" | "blocked" | "success" | "failed";

export type AgentStep = {
  phase?: string;
  label?: string;
  status?: string;
  status_label?: string;
  summary?: string;
};

export type AgentGateCard = {
  key: string;
  label: string;
  status?: string;
  tone?: AgentTone;
  detail?: string;
};

export type AgentMessage = {
  id: string;
  kind?: string;
  timestamp?: string;
  phase?: string;
  title?: string;
  body?: string;
  status?: string;
  status_label?: string;
  tone?: AgentTone;
  artifacts?: string[];
  provider?: string;
  model?: string;
  tool?: string;
};

export type AgentAction = NextAction & {
  label?: string;
};

export type SuggestedAction = {
  id: string;
  label: string;
  action: string;
  safe: boolean;
  tool?: string;
  requires_human_confirmation?: boolean;
  reason?: string;
};

export type ConversationState = {
  task?: string;
  status?: string;
  status_label?: string;
  phase?: string;
  phase_label?: string;
  tone?: AgentTone;
  next_step?: string;
  composer_placeholder?: string;
  suggestions?: SuggestedAction[];
};

export type AgentActivity = {
  headline?: string;
  tone?: AgentTone;
  current_step?: AgentStep;
  next_action?: AgentAction | null;
  conversation_state?: ConversationState;
  gate_cards?: AgentGateCard[];
  messages?: AgentMessage[];
  artifacts?: HandoffArtifact[];
};

export type AgentResponse = {
  run_id: string | null;
  action?: string;
  ok?: boolean;
  reply?: string;
  status?: RunStatus | null;
  context?: HandoffContext | null;
  runs?: { count?: number; runs?: RunSummary[] };
  recent_run?: RunSummary | null;
  doctor?: DoctorReport;
  setup?: SetupResult;
  setup_host?: string;
  capabilities?: { name: string; summary: string }[];
  next_actions?: string[];
  recommendations?: string[];
  diff?: string | null;
  background?: boolean;
  job?: Record<string, unknown>;
  requires_confirmation?: {
    type?: string;
    required_action?: string;
    confirmation?: "plan_approved" | "apply_approved";
  } | null;
  error?: string | null;
};

export type AgentMessageOptions = {
  runId?: string;
  confirmation?: "none" | "plan_approved" | "apply_approved";
  include?: Record<string, unknown>;
  maxFixRounds?: number;
  background?: boolean;
};

export type HandoffContext = {
  run_id: string;
  handoff_summary?: string;
  status?: string;
  current_phase?: string;
  gate_state?: GateState;
  run_metrics?: RunMetrics;
  next_actions?: NextAction[];
  provider_trail?: ProviderTrailEntry[];
  artifacts?: HandoffArtifact[];
  timeline?: TraceEntry[];
  agent_activity?: AgentActivity;
  cursors?: { event?: number; trace?: number };
};

export type PatchbayClient = {
  agentMessage(message: string, options?: AgentMessageOptions): Promise<AgentResponse>;
  createRun(task: string, options?: { background?: boolean }): Promise<{ run_id: string; [key: string]: unknown }>;
  listRuns(): Promise<{ count?: number; runs: RunSummary[] }>;
  getStatus(runId: string): Promise<RunStatus>;
  getContext(runId: string, options?: { since_event?: number; since_trace?: number; include_trace?: boolean }): Promise<HandoffContext>;
  getTrace(runId: string, options?: { since?: number; phase?: string }): Promise<{ total?: number; trace?: TraceEntry[]; events?: TraceEntry[] }>;
  getDiff(runId: string): Promise<{ text?: string; diff?: string }>;
  getArtifact(runId: string, artifact: string, options?: { tail?: number }): Promise<{ text: string }>;
  getConfig(): Promise<unknown>;
  getDoctor(options?: { include_mcp?: boolean; skill_path?: string }): Promise<DoctorReport>;
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

export function createRun(task: string, options: { background?: boolean } = {}, client?: ClientOptions) {
  return requestJson<{ run_id: string; [key: string]: unknown }>("/api/runs", client, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, background: Boolean(options.background) })
  });
}

export function postAgentMessage(message: string, options: AgentMessageOptions = {}, client?: ClientOptions) {
  return requestJson<AgentResponse>("/api/agent/message", client, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      run_id: options.runId ?? "",
      confirmation: options.confirmation ?? "none",
      include: options.include ?? {},
      max_fix_rounds: options.maxFixRounds,
      background: Boolean(options.background)
    })
  });
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

export function fetchDoctor(options: { include_mcp?: boolean; skill_path?: string } = {}, client?: ClientOptions) {
  return requestJson<DoctorReport>(`/api/doctor${query(options)}`, client);
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
    agentMessage: (message, options) => postAgentMessage(message, options, client),
    createRun: (task, options) => createRun(task, options, client),
    listRuns: () => fetchRuns(client),
    getStatus: (runId) => fetchStatus(runId, client),
    getContext: (runId, options) => fetchContext(runId, options, client),
    getTrace: (runId, options) => fetchTrace(runId, options, client),
    getDiff: (runId) => fetchDiff(runId, client),
    getArtifact: (runId, artifact, options) => fetchArtifact(runId, artifact, options, client),
    getConfig: () => fetchConfig(client),
    getDoctor: (options) => fetchDoctor(options, client),
    runAction: (runId, action) => postRunAction(runId, action, client),
    apply: (runId) => applyRun(runId, client),
    cleanup: (runId) => cleanupRun(runId, client)
  };
}
