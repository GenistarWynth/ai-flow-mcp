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

export type FailureRecovery = {
  stage?: string;
  error?: string;
  suggested_next_action?: string;
  safe_actions?: string[];
  actions?: AgentHealthAction[];
  artifacts?: string[];
  summary?: string;
};

export type PhaseProvider = {
  provider?: string;
  model?: string;
  command_key?: string;
};

export type CommandStatus = {
  required?: boolean;
  ready?: boolean;
  status?: "ready" | "missing_config" | "not_found" | string;
  provider?: string;
  command_key?: string;
  command?: string;
  executable?: string;
  resolved?: string;
  recommendation?: string;
};

export type PhaseStrategy = PhaseProvider & {
  tier?: "economy" | "supervision" | string;
  reason?: string;
  economy_route?: boolean;
  command_status?: CommandStatus;
  error?: string;
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

export type RoutingEvidencePhase = {
  configured?: PhaseProvider;
  command_status?: CommandStatus | null;
  observed?: ProviderUsage[];
  configured_economy?: boolean;
  observed_economy?: boolean;
  status?: string;
};

export type RoutingCoverage = {
  required_phases?: string[];
  required_total?: number;
  configured_economy_total?: number;
  observed_total?: number;
  observed_economy_total?: number;
  observed_other_total?: number;
  observed_economy_ratio?: number;
  observed_economy_percent?: number;
  complete?: boolean;
  label?: string;
};

export type EconomyHealth = {
  status?: "healthy" | "pending_evidence" | "drift" | "not_configured" | "command_not_ready" | string;
  severity?: "ok" | "info" | "warning" | string;
  configured?: boolean;
  target?: PhaseProvider;
  required_phases?: string[];
  missing_config_phases?: string[];
  command_not_ready_phases?: string[];
  drift_phases?: string[];
  missing_evidence?: string[];
  observed_economy_phases?: string[];
  summary?: string;
  recommendation?: string;
  next_action?: string;
};

export type RoutingEvidence = {
  profile?: string;
  target?: PhaseProvider;
  economy_configured?: boolean;
  economy_command_ready?: boolean | null;
  command_not_ready_phases?: string[];
  configured_economy_phases?: string[];
  observed_phases?: string[];
  observed_economy_phases?: string[];
  observed_non_economy_phases?: string[];
  missing_evidence?: string[];
  coverage?: RoutingCoverage;
  economy_health?: EconomyHealth;
  phases?: Record<string, RoutingEvidencePhase>;
  phase_strategy?: Record<string, PhaseStrategy>;
  actions?: AgentHealthAction[];
  summary?: string;
  recommendation?: string;
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
  routing_evidence?: RoutingEvidence;
};

export type RunStatus = {
  run_id: string;
  task?: string;
  status?: string;
  current_phase?: string;
  error?: string | null;
  suggested_next_action?: string | null;
  failure_recovery?: FailureRecovery | null;
  tests_passed?: boolean;
  review_result?: string | null;
  gate_state?: GateState;
  next_commands?: string[];
  artifacts?: string[];
  effective_phase_providers?: Record<string, PhaseProvider>;
  routing_evidence?: RoutingEvidence;
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
  host?: string;
  checks?: Record<string, DoctorCheck>;
  next_actions?: string[];
  recommendations?: string[];
  actions?: AgentHealthAction[];
};

export type ConfigProfileStatus = {
  config?: string;
  profile?: string;
  economy?: {
    matches?: boolean;
    intent?: string;
    write?: PhaseProvider;
    fix?: PhaseProvider;
    command_ready?: boolean;
    command_status?: Record<string, CommandStatus>;
    error?: string;
  };
  phase_strategy?: Record<string, PhaseStrategy>;
  recommendation?: string;
  status?: ConfigProfileStatus;
  summary?: string;
  updated?: Record<string, unknown>;
  next_actions?: string[];
  actions?: AgentHealthAction[];
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
  actions?: AgentHealthAction[];
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

export type AgentHealthAction = {
  id: string;
  label: string;
  kind?: "local_agent" | "diagnostic_tab" | "open_run" | "focus_composer" | string;
  message?: string;
  command?: string;
  host?: string;
  tab?: RunReferenceView["tab"];
  run_id?: string;
  safe?: boolean;
  reason?: string;
};

export type AgentHealthCard = AgentGateCard & {
  recommendation?: string;
  next_action?: string;
  action?: AgentHealthAction | null;
  coverage_percent?: number | null;
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
  health_cards?: AgentHealthCard[];
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
  run_reference?: (RunSummary & { suggested_message?: string; safe_actions?: string[]; next_actions?: string[]; requested_view?: RunReferenceView | null }) | null;
  requested_view?: RunReferenceView | null;
  doctor?: DoctorReport;
  setup?: SetupResult;
  setup_host?: string;
  recovery?: FailureRecovery;
  profile?: Record<string, unknown>;
  routing?: RoutingEvidence;
  metrics?: {
    run_metrics?: RunMetrics;
    routing_evidence?: RoutingEvidence;
    [key: string]: unknown;
  };
  capabilities?: { name: string; summary: string }[];
  actions?: AgentHealthAction[];
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

export type RunReferenceView = {
  tab?: "Overview" | "Readiness" | "Trace" | "Log" | "Diff" | "Artifacts" | "Config" | "Providers";
  reason?: string;
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
  failure_recovery?: FailureRecovery | null;
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
  getConfigProfile(): Promise<ConfigProfileStatus>;
  applyConfigProfile(profile?: "economy" | string): Promise<ConfigProfileStatus>;
  getDoctor(options?: { include_mcp?: boolean; skill_path?: string; host?: string }): Promise<DoctorReport>;
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

export function fetchConfigProfile(client?: ClientOptions) {
  return requestJson<ConfigProfileStatus>("/api/config/profile", client);
}

export function applyConfigProfile(profile: "economy" | string = "economy", client?: ClientOptions) {
  return requestJson<ConfigProfileStatus>("/api/config/profile/apply", client, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile })
  });
}

export function fetchDoctor(options: { include_mcp?: boolean; skill_path?: string; host?: string } = {}, client?: ClientOptions) {
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
    getConfigProfile: () => fetchConfigProfile(client),
    applyConfigProfile: (profile) => applyConfigProfile(profile, client),
    getDoctor: (options) => fetchDoctor(options, client),
    runAction: (runId, action) => postRunAction(runId, action, client),
    apply: (runId) => applyRun(runId, client),
    cleanup: (runId) => cleanupRun(runId, client)
  };
}
