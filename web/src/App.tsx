import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Check,
  ChevronRight,
  CircleDot,
  FileText,
  GitPullRequest,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  User
} from "lucide-react";
import {
  AgentResponse,
  AgentActivity,
  AgentAction,
  AgentMessage,
  createPatchbayClient,
  DoctorReport,
  HandoffContext,
  PatchbayClient,
  ProviderUsage,
  RunMetrics,
  RunStatus,
  RunSummary,
  SuggestedAction,
  TraceEntry
} from "./api";
import "./styles.css";

type TabName = "Overview" | "Readiness" | "Trace" | "Log" | "Diff" | "Artifacts" | "Config" | "Providers";
type ConfirmState = { action: string; title: string; body: string; safe: boolean; confirmLabel?: string } | null;
type LocalMessage = { id: string; body: string; timestamp: string };

const phases = ["plan", "approve", "write", "test", "review", "fix", "apply", "cleanup"];
const phaseLabels: Record<string, string> = {
  plan: "规划",
  approve: "批准",
  write: "实现",
  test: "测试",
  review: "审查",
  fix: "修复",
  apply: "应用",
  cleanup: "清理",
  error: "错误"
};
const actionLabels: Record<string, string> = {
  approve: "批准计划",
  write: "开始实现",
  test: "运行测试",
  review: "开始审查",
  fix: "执行修复",
  apply: "应用补丁",
  cleanup: "清理运行",
  start: "开始",
  success: "完成",
  gate: "门禁",
  queued: "已排队",
  error: "错误",
  failed: "失败"
};
const statusLabels: Record<string, string> = {
  NEW: "待规划",
  PLANNED: "等待批准",
  APPROVED: "等待实现",
  IMPLEMENTING: "实现中",
  IMPLEMENTED: "等待测试",
  TESTING: "测试中",
  TESTED: "等待审查",
  REVIEWING: "审查中",
  REVIEWED_PASS: "审查通过",
  REVIEWED_CHANGES_REQUESTED: "需要修复",
  FIXING: "修复中",
  APPLIED: "已应用",
  FAILED: "失败",
  RUNNING: "运行中",
  QUEUED: "已排队",
  READY: "就绪",
  PASS: "通过",
  SUCCESS: "成功",
  ERROR: "错误",
  CHANGES_REQUESTED: "需要修改"
};
const tabLabels: Record<TabName, string> = {
  Overview: "状态",
  Readiness: "就绪",
  Trace: "活动",
  Log: "日志",
  Diff: "差异",
  Artifacts: "产物",
  Config: "配置",
  Providers: "提供方"
};
const defaultClient = createPatchbayClient();
const busyStatuses = new Set(["IMPLEMENTING", "TESTING", "REVIEWING", "FIXING", "RUNNING"]);

function phaseLabel(phase?: string) {
  if (!phase) return "空闲";
  return phaseLabels[phase] ?? phase;
}

function statusLabel(status?: string | null) {
  if (!status) return "未知";
  return statusLabels[status] ?? status;
}

function isBusyStatus(status?: string | null) {
  return busyStatuses.has(status ?? "");
}

function commandLabel(command?: string) {
  if (!command) return "无";
  return actionLabels[command] ?? phaseLabel(command);
}

function commandReason(command: string, safe: boolean) {
  if (command === "approve") return "Plan is ready for human approval before implementation.";
  if (command === "apply") return safe ? "Tests passed and review returned PASS; human confirmation is still required." : "Apply is blocked until tests pass and review returns PASS.";
  if (command === "fix") return "Review requested changes; run the configured fixer before retesting.";
  if (command === "review") return "Tests completed; run read-only review next.";
  if (command === "test") return "Implementation diff is ready; run configured test evidence next.";
  if (command === "write") return "Plan was approved; writer may work inside the isolated worktree.";
  if (command === "cleanup") return "Run is applied; cleanup can remove the isolated worktree.";
  return `Run the ${command} phase next.`;
}

function compactDuration(ms?: number | null) {
  if (ms === undefined || ms === null) return "未知";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}

function compactNumber(value?: number | null) {
  if (value === undefined || value === null) return "待上报";
  if (value < 1000) return String(value);
  if (value < 1_000_000) return `${(value / 1000).toFixed(value >= 100_000 ? 0 : 1)}k`;
  return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`;
}

function metricEntries(metrics?: RunMetrics | null) {
  return Object.entries(metrics?.phase_durations_ms ?? {}).filter(([, duration]) => duration > 0);
}

function totalAttempts(metrics?: RunMetrics | null) {
  return Object.values(metrics?.phase_attempts ?? {}).reduce((total, value) => total + value, 0);
}

function retryEntries(metrics?: RunMetrics | null) {
  return Object.entries(metrics?.phase_attempts ?? {}).filter(([, attempts]) => attempts > 1);
}

function tokenEntries(metrics?: RunMetrics | null) {
  return Object.entries(metrics?.token_usage?.by_phase ?? {}).filter(([, usage]) => Boolean(usage?.known));
}

function costEntries(metrics?: RunMetrics | null) {
  return Object.entries(metrics?.cost?.by_phase ?? {}).filter(([, usage]) => Boolean(usage?.known));
}

function providerMetricEntries(metrics?: RunMetrics | null) {
  return (metrics?.provider_usage ?? []).filter((item) => Boolean(item.token_usage?.known || item.cost?.known));
}

function providerMetricLabel(item: ProviderUsage) {
  const provider = item.provider || item.model || "provider";
  const heading = item.phase ? `${phaseLabel(item.phase)} / ${provider}` : provider;
  const signals: string[] = [];
  if (item.token_usage?.known || item.total_tokens !== undefined) {
    signals.push(`${compactNumber(item.token_usage?.total_tokens ?? item.total_tokens)} tok`);
  }
  if (item.cost?.known) {
    signals.push(`${item.cost.currency ?? "USD"} ${compactNumber(item.cost.estimated_total ?? 0)}`);
  }
  return signals.length ? `${heading} ${signals.join(" | ")}` : heading;
}

function timeLabel(timestamp?: string) {
  return timestamp ? timestamp.slice(11, 19) : "--:--:--";
}

function dedupeMessages(messages: AgentMessage[]) {
  const order: string[] = [];
  const byId = new Map<string, AgentMessage>();
  messages.forEach((message, index) => {
    const id = message.id || `message-${index}`;
    if (!byId.has(id)) order.push(id);
    byId.set(id, { ...message, id });
  });
  return order.map((id) => byId.get(id)!);
}

function mergeContext(current: HandoffContext | null, next: HandoffContext): HandoffContext {
  if (!current) return next;
  const currentMessages = current.agent_activity?.messages ?? [];
  const nextMessages = next.agent_activity?.messages ?? [];
  const agentActivity = next.agent_activity
    ? {
        ...next.agent_activity,
        messages: dedupeMessages([...currentMessages, ...nextMessages])
      }
    : current.agent_activity;
  return { ...current, ...next, agent_activity: agentActivity };
}

function fallbackActivity(context: HandoffContext | null, status: RunStatus | null): AgentActivity {
  const fallbackActions = (status?.next_commands ?? []).map((name) => {
    const safe = name === "apply" ? Boolean(status?.gate_state?.ready_to_apply && status?.review_result === "PASS" && status?.tests_passed) : true;
    return {
      name,
      safe,
      tool: `patchbay_${name}`,
      requires_human_confirmation: name === "approve" || name === "apply",
      reason: commandReason(name, safe)
    };
  });
  const nextActions = context?.next_actions ?? fallbackActions;
  const nextAction = nextActions.find((action) => action.safe) ?? nextActions[0] ?? null;
  const currentPhase = context?.current_phase ?? status?.current_phase ?? "";
  const currentStatus = context?.status ?? status?.status ?? "";
  const gateState = context?.gate_state ?? status?.gate_state ?? {};
  const busy = isBusyStatus(currentStatus);
  const suggestions = nextActions.map((action) => ({
    id: action.name,
    label: commandLabel(action.name),
    action: action.name,
    safe: action.safe,
    tool: action.tool,
    requires_human_confirmation: action.requires_human_confirmation,
    reason: action.reason
  }));
  return {
    headline: nextAction
      ? `Patchbay Agent 已准备好执行：${commandLabel(nextAction.name)}。`
      : busy
        ? `Patchbay Agent 正在执行${phaseLabel(currentPhase)}阶段。`
        : `Patchbay Agent 当前处于${phaseLabel(currentPhase)}阶段。`,
    tone: busy ? "running" : nextAction ? "ready" : "idle",
    current_step: {
      phase: currentPhase,
      label: phaseLabel(currentPhase),
      status: currentStatus,
      status_label: statusLabel(currentStatus),
      summary: nextAction?.reason ?? (busy ? "后台任务正在运行，状态会自动刷新。" : "暂无可执行动作。")
    },
    next_action: nextAction ? { ...nextAction, label: commandLabel(nextAction.name) } : null,
    conversation_state: {
      task: status?.task,
      status: currentStatus,
      status_label: statusLabel(currentStatus),
      phase: currentPhase,
      phase_label: phaseLabel(currentPhase),
      tone: busy ? "running" : nextAction ? "ready" : "idle",
      next_step: nextAction?.reason ?? (busy ? "后台任务正在运行，完成后会出现下一步。" : "当前没有可执行动作。"),
      composer_placeholder: busy ? "后台任务运行中，完成后可继续" : nextAction ? `输入“继续”或点击“${commandLabel(nextAction.name)}”` : "输入新任务，或写下本地备注",
      suggestions
    },
    gate_cards: [
      { key: "approval", label: "批准", tone: gateState.approved ? "success" : "idle", detail: gateState.approved ? "计划已批准" : "等待批准" },
      { key: "tests", label: "测试", tone: gateState.tests_passed ? "success" : "idle", detail: gateState.tests_passed ? "测试通过" : "等待测试" },
      { key: "review", label: "审查", tone: gateState.review_result === "PASS" ? "success" : gateState.review_result ? "blocked" : "idle", detail: statusLabel(gateState.review_result) },
      { key: "apply", label: "应用", tone: gateState.ready_to_apply ? "ready" : "blocked", detail: gateState.ready_to_apply ? "可以应用" : "等待门禁" }
    ],
    messages: (context?.timeline ?? []).map((entry, index) => ({
      id: `${entry.source ?? "event"}-${entry.index ?? entry.seq ?? index}`,
      kind: entry.source,
      timestamp: entry.timestamp,
      phase: entry.phase,
      title: `${phaseLabel(entry.phase)} · ${commandLabel(entry.action)} · ${statusLabel(entry.status)}`,
      body: entry.detail,
      status: entry.status,
      status_label: statusLabel(entry.status),
      tone:
        entry.status === "PASS" || entry.status === "SUCCESS"
          ? "success"
          : entry.status === "ERROR"
            ? "failed"
            : entry.status === "RUNNING" || entry.status === "QUEUED"
              ? "running"
              : "idle",
      artifacts: entry.artifact_paths,
      provider: entry.provider ?? entry.agent,
      model: entry.model,
      tool: entry.tool ?? entry.next_action
    }))
  };
}

function suggestionsFor(activity: AgentActivity, context: HandoffContext | null): SuggestedAction[] {
  const fromConversation = activity.conversation_state?.suggestions ?? [];
  if (fromConversation.length) return fromConversation;
  return (context?.next_actions ?? []).map((action) => ({
    id: action.name,
    label: commandLabel(action.name),
    action: action.name,
    safe: action.safe,
    tool: action.tool,
    requires_human_confirmation: action.requires_human_confirmation,
    reason: action.reason
  }));
}

function actionFromSuggestion(suggestion: SuggestedAction | AgentAction): SuggestedAction {
  const action = "action" in suggestion ? suggestion.action : suggestion.name;
  return {
    id: "id" in suggestion ? suggestion.id : action,
    label: suggestion.label ?? commandLabel(action),
    action,
    safe: suggestion.safe,
    tool: suggestion.tool,
    requires_human_confirmation: suggestion.requires_human_confirmation,
    reason: suggestion.reason
  };
}

function confirmCopy(action: SuggestedAction, readyToApply: boolean): ConfirmState {
  if (!action.safe) {
    return {
      action: action.action,
      title: "暂不能执行",
      body: action.reason || `当前状态不允许执行“${action.label}”。`,
      safe: false,
      confirmLabel: "知道了"
    };
  }
  if (action.action === "approve") {
    return {
      action: action.action,
      title: "确认批准计划",
      body: "批准后，Patchbay Agent 才会进入实现阶段。",
      safe: true,
      confirmLabel: "批准"
    };
  }
  if (action.action === "apply") {
    return {
      action: action.action,
      title: readyToApply ? "确认应用补丁" : "暂不能应用",
      body: readyToApply ? "将已审查通过的 FINAL.diff 应用到当前工作区。" : "应用必须等待测试通过且审查为 PASS。",
      safe: readyToApply,
      confirmLabel: readyToApply ? "应用" : "知道了"
    };
  }
  if (action.action === "cleanup") {
    return {
      action: action.action,
      title: "确认清理运行",
      body: "移除本次运行的 worktree 和临时资源。",
      safe: true,
      confirmLabel: "清理"
    };
  }
  return null;
}

function resolveComposerIntent(text: string, suggestions: SuggestedAction[], primaryAction: AgentAction | null | undefined) {
  const value = text.trim().toLowerCase();
  if (!value || value.length > 24) return null;
  const findAction = (name: string) => suggestions.find((item) => item.action === name);
  const continueWords = ["继续", "下一步", "确认", "go", "continue", "next"];
  if (continueWords.some((word) => value === word || value.includes(word))) {
    if (primaryAction) return actionFromSuggestion(primaryAction);
    return suggestions[0] ?? null;
  }
  const tokenMap: Array<[string, string[]]> = [
    ["approve", ["批准", "approve"]],
    ["write", ["实现", "写", "write"]],
    ["test", ["测试", "test"]],
    ["review", ["审查", "review"]],
    ["fix", ["修复", "fix"]],
    ["apply", ["应用", "apply"]],
    ["cleanup", ["清理", "cleanup"]]
  ];
  for (const [action, tokens] of tokenMap) {
    if (tokens.some((token) => value === token || value.includes(token))) {
      return findAction(action) ?? { id: action, label: commandLabel(action), action, safe: false, reason: "这不是当前运行允许的下一步。" };
    }
  }
  return null;
}

function confirmationForAction(action: string): "plan_approved" | "apply_approved" | undefined {
  if (action === "approve") return "plan_approved";
  if (action === "apply") return "apply_approved";
  return undefined;
}

function shouldAutopilot(action: string) {
  return ["continue", "write", "test", "review", "fix"].includes(action);
}

export function Workbench({ client = defaultClient, pollIntervalMs = 4000 }: { client?: PatchbayClient; pollIntervalMs?: number }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [newTaskMode, setNewTaskMode] = useState(false);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [context, setContext] = useState<HandoffContext | null>(null);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [rawTrace, setRawTrace] = useState<TraceEntry[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<AgentMessage | null>(null);
  const eventCursor = useRef(0);
  const [diff, setDiff] = useState("");
  const [artifactText, setArtifactText] = useState("");
  const [config, setConfig] = useState<unknown>(null);
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [activeTab, setActiveTab] = useState<TabName>("Overview");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const [error, setError] = useState("");
  const [composer, setComposer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionInFlight, setActionInFlight] = useState(false);
  const [setupInFlight, setSetupInFlight] = useState(false);
  const [profileInFlight, setProfileInFlight] = useState(false);
  const [localMessages, setLocalMessages] = useState<Record<string, LocalMessage[]>>({});
  const [newTaskReply, setNewTaskReply] = useState<AgentResponse | null>(null);

  const patchRunSummary = (runId: string, patch: Partial<RunSummary>) => {
    setRuns((current) => current.map((run) => (run.run_id === runId ? { ...run, ...patch } : run)));
  };

  const loadRuns = async (preferredRunId?: string) => {
    const result = await client.listRuns();
    const nextRuns = result.runs ?? [];
    setRuns(nextRuns);
    if (preferredRunId) {
      setSelectedRun(preferredRunId);
      return nextRuns;
    }
    if (!selectedRun && !newTaskMode && nextRuns[0]) setSelectedRun(nextRuns[0].run_id);
    return nextRuns;
  };

  useEffect(() => {
    void loadRuns().catch((err) => setError(String(err)));
    void client.getDoctor({ include_mcp: false }).then(setDoctor).catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!selectedRun) {
      setStatus(null);
      setContext(null);
      setTrace([]);
      setRawTrace([]);
      setSelectedMessage(null);
      eventCursor.current = 0;
      return;
    }
    let cancelled = false;
    setTrace([]);
    setRawTrace([]);
    setSelectedMessage(null);
    eventCursor.current = 0;

    function appendTimelineEntries(entries: TraceEntry[], total?: number, since = 0, replace = false) {
      setTrace((current) => (replace ? entries : [...current, ...entries]));
      eventCursor.current = total ?? (entries.at(-1)?.index ?? since - 1) + 1;
    }

    async function loadSelectedRun() {
      const [nextStatus, nextContext, nextTrace, nextDiff, nextConfig] = await Promise.all([
        client.getStatus(selectedRun),
        client.getContext(selectedRun),
        client.getTrace(selectedRun),
        client.getDiff(selectedRun),
        client.getConfig()
      ]);
      if (cancelled) return;
      setStatus(nextStatus);
      setContext(nextContext);
      setRawTrace(nextTrace.trace ?? nextTrace.events ?? []);
      appendTimelineEntries(nextContext.timeline ?? [], nextContext.cursors?.event, 0, true);
      setSelectedMessage(nextContext.agent_activity?.messages?.[0] ?? null);
      setDiff(nextDiff.text ?? nextDiff.diff ?? "");
      setConfig(nextConfig);
      const firstArtifact = nextStatus.artifacts?.find((name) => name.endsWith(".log") || name.endsWith(".md"));
      if (firstArtifact) {
        const artifact = await client.getArtifact(selectedRun, firstArtifact, { tail: 80 });
        if (!cancelled) setArtifactText(artifact.text);
      } else {
        setArtifactText("");
      }
    }

    async function loadContextUpdate() {
      const since = eventCursor.current;
      const nextContext = await client.getContext(selectedRun, { since_event: since });
      if (cancelled || !nextContext) return;
      setContext((current) => mergeContext(current, nextContext));
      setStatus((current) =>
        current
          ? {
              ...current,
              status: nextContext.status ?? current.status,
              current_phase: nextContext.current_phase ?? current.current_phase,
              gate_state: nextContext.gate_state ?? current.gate_state
            }
          : current
      );
      patchRunSummary(selectedRun, {
        status: nextContext.status,
        task: nextContext.agent_activity?.conversation_state?.task
      });
      appendTimelineEntries(nextContext.timeline ?? [], nextContext.cursors?.event, since);
    }

    void loadSelectedRun().catch((err) => setError(String(err)));
    const timer =
      pollIntervalMs > 0
        ? window.setInterval(() => {
            void loadContextUpdate().catch((err) => setError(String(err)));
          }, pollIntervalMs)
        : undefined;
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [selectedRun, client, pollIntervalMs]);

  const visibleRuns = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return runs.filter((run) => {
      const matchesStatus = !statusFilter || run.status === statusFilter;
      const text = `${run.run_id} ${run.task ?? ""}`.toLowerCase();
      return matchesStatus && (!needle || text.includes(needle));
    });
  }, [runs, search, statusFilter]);

  useEffect(() => {
    if (newTaskMode) return;
    if (!visibleRuns.length) {
      if (selectedRun) setSelectedRun("");
      return;
    }
    if (!visibleRuns.some((run) => run.run_id === selectedRun)) {
      setSelectedRun(visibleRuns[0].run_id);
    }
  }, [visibleRuns, selectedRun, newTaskMode]);

  const selectedSummary = useMemo(() => runs.find((run) => run.run_id === selectedRun), [runs, selectedRun]);
  const activeContext = context?.run_id === selectedRun ? context : null;
  const activeStatus = status?.run_id === selectedRun ? status : null;
  const activity = activeContext?.agent_activity ?? fallbackActivity(activeContext, activeStatus);
  const conversationState = activity.conversation_state;
  const gateState = activeContext?.gate_state ?? activeStatus?.gate_state ?? {};
  const currentStatus = activeContext?.status ?? activeStatus?.status ?? selectedSummary?.status;
  const currentPhase = activeContext?.current_phase ?? activeStatus?.current_phase ?? "";
  const runBusy = isBusyStatus(currentStatus);
  const interactionBusy = submitting || actionInFlight || runBusy;
  const readyToApply = Boolean(gateState.ready_to_apply && (activeContext?.status ?? activeStatus?.status) === "REVIEWED_PASS");
  const messages = dedupeMessages(activity.messages ?? []);
  const primaryAction = activity.next_action;
  const suggestions = suggestionsFor(activity, activeContext);
  const selectedTask = conversationState?.task ?? activeStatus?.task ?? selectedSummary?.task ?? "";
  const runKey = selectedRun || "__new__";
  const localRunMessages = localMessages[runKey] ?? [];
  const composerPlaceholder = selectedRun
    ? conversationState?.composer_placeholder ?? "输入“继续”，或写下本地备注"
    : "描述一个新任务，Patchbay Agent 会先生成计划";

  const loadContextNow = async (runId = selectedRun) => {
    if (!runId) return;
    const nextContext = await client.getContext(runId);
    setContext(nextContext);
    setTrace(nextContext.timeline ?? []);
    setSelectedMessage(nextContext.agent_activity?.messages?.[0] ?? null);
    eventCursor.current = nextContext.cursors?.event ?? 0;
  };

  const refreshRun = async (runId: string, agentResponse?: AgentResponse) => {
    await loadRuns(runId);
    if (agentResponse?.status) setStatus(agentResponse.status);
    else setStatus(await client.getStatus(runId));
    if (agentResponse?.context) {
      setContext(agentResponse.context);
      setTrace(agentResponse.context.timeline ?? []);
      setSelectedMessage(agentResponse.context.agent_activity?.messages?.[0] ?? null);
      eventCursor.current = agentResponse.context.cursors?.event ?? 0;
    } else {
      await loadContextNow(runId);
    }
    const nextDiff = await client.getDiff(runId);
    setDiff(nextDiff.text ?? nextDiff.diff ?? "");
    patchRunSummary(runId, {
      status: agentResponse?.context?.status ?? agentResponse?.status?.status,
      task: agentResponse?.context?.agent_activity?.conversation_state?.task ?? agentResponse?.status?.task
    });
  };

  const runAction = async (action: string) => {
    if (!selectedRun || interactionBusy) return;
    setError("");
    setActionInFlight(true);
    try {
      if (shouldAutopilot(action)) {
        const response = await client.agentMessage("continue", {
          runId: selectedRun,
          include: { diff: true, review: true },
          background: true
        });
        await refreshRun(selectedRun, response);
        return;
      }
      await client.runAction(selectedRun, action);
      await refreshRun(selectedRun);
    } finally {
      setActionInFlight(false);
    }
  };

  const handleAction = (candidate?: SuggestedAction | AgentAction | string | null) => {
    if (!candidate) return;
    const action =
      typeof candidate === "string"
        ? suggestions.find((item) => item.action === candidate) ?? { id: candidate, label: commandLabel(candidate), action: candidate, safe: candidate !== "apply" || readyToApply }
        : actionFromSuggestion(candidate);
    if (action.action === "apply" && !readyToApply) action.safe = false;
    const confirmation = confirmCopy(action, readyToApply);
    if (confirmation) {
      setConfirm(confirmation);
      return;
    }
    if (!action.safe) {
      setConfirm(confirmCopy(action, readyToApply));
      return;
    }
    void runAction(action.action);
  };

  const confirmAction = async () => {
    if (!confirm || actionInFlight) return;
    if (!confirm.safe) {
      setConfirm(null);
      return;
    }
    if (!selectedRun) return;
    setError("");
    const action = confirm.action;
    setConfirm(null);
    const confirmation = confirmationForAction(action);
    setActionInFlight(true);
    try {
      if (confirmation) {
        const response = await client.agentMessage(action, {
          runId: selectedRun,
          confirmation,
          include: { diff: action === "apply", review: action === "apply" },
          background: action !== "apply"
        });
        await refreshRun(selectedRun, response);
      } else if (action === "cleanup") {
        await client.cleanup(selectedRun);
        await refreshRun(selectedRun);
      } else if (shouldAutopilot(action)) {
        const response = await client.agentMessage("continue", {
          runId: selectedRun,
          include: { diff: true, review: true },
          background: true
        });
        await refreshRun(selectedRun, response);
      } else {
        await client.runAction(selectedRun, action);
        await refreshRun(selectedRun);
      }
    } finally {
      setActionInFlight(false);
    }
  };

  const appendLocalMessage = (body: string) => {
    const timestamp = new Date().toISOString();
    setLocalMessages((current) => ({
      ...current,
      [runKey]: [...(current[runKey] ?? []), { id: `local-${Date.now()}`, body, timestamp }]
    }));
  };

  const runSetupAction = async () => {
    if (setupInFlight) return;
    setError("");
    setSetupInFlight(true);
    try {
      const response = await client.agentMessage("patchbay setup");
      const setupDoctor = response.setup?.doctor ?? response.doctor;
      if (!selectedRun) setNewTaskReply(response);
      if (setupDoctor) {
        setDoctor(setupDoctor);
      } else {
        setDoctor(await client.getDoctor({ include_mcp: false }));
      }
      await loadRuns(selectedRun || undefined);
    } catch (err) {
      setError(String(err));
    } finally {
      setSetupInFlight(false);
    }
  };

  const applyEconomyProfileAction = async () => {
    if (profileInFlight) return;
    setError("");
    setProfileInFlight(true);
    try {
      const response = await client.agentMessage("apply economy profile");
      if (!selectedRun) setNewTaskReply(response);
      const [nextDoctor, nextConfig] = await Promise.all([client.getDoctor({ include_mcp: false }), client.getConfig()]);
      setDoctor(nextDoctor);
      setConfig(nextConfig);
      await loadRuns(selectedRun || undefined);
    } catch (err) {
      setError(String(err));
    } finally {
      setProfileInFlight(false);
    }
  };

  const submitComposer = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = composer.trim();
    if (!text || interactionBusy) return;
    setError("");
    setSubmitting(true);
    try {
      if (!selectedRun) {
        const created = await client.agentMessage(text, { include: { plan: true }, background: true });
        setComposer("");
        setNewTaskReply(null);
        if (!created.run_id) {
          appendLocalMessage(text);
          setNewTaskReply(created);
          if (created.doctor) setDoctor(created.doctor);
          await loadRuns();
          return;
        }
        setNewTaskMode(false);
        await loadRuns(created.run_id);
        return;
      }
      const intent = resolveComposerIntent(text, suggestions, primaryAction);
      setComposer("");
      if (intent) {
        handleAction(intent);
      } else {
        appendLocalMessage(text);
        const response = await client.agentMessage(text, {
          runId: selectedRun,
          include: { diff: true, review: true },
          background: true
        });
        await refreshRun(selectedRun, response);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitComposer();
    }
  };

  const startNewTask = () => {
    setNewTaskMode(true);
    setSelectedRun("");
    setComposer("");
    setError("");
    setNewTaskReply(null);
  };

  return (
    <main className={`workbench ${diagnosticsOpen ? "diagnostics-open" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <GitPullRequest size={20} />
          <div>
            <strong>Patchbay Agent</strong>
            <span>一个任务线程</span>
          </div>
          <button className="icon-button" onClick={startNewTask} aria-label="新任务">
            <Plus size={16} />
          </button>
        </div>
        <label className="search">
          <Search size={15} />
          <input aria-label="搜索运行" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索线程" />
        </label>
        <label className="filter">
          <span>状态</span>
          <select aria-label="状态筛选" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">全部</option>
            <option value="PLANNED">等待批准</option>
            <option value="IMPLEMENTING">实现中</option>
            <option value="REVIEWED_PASS">审查通过</option>
            <option value="REVIEWED_CHANGES_REQUESTED">需要修复</option>
            <option value="FAILED">失败</option>
          </select>
        </label>
        <div className="run-list" aria-label="运行线程">
          {visibleRuns.map((run) => (
            <button
              className={`run-item ${run.run_id === selectedRun ? "selected" : ""}`}
              key={run.run_id}
              onClick={() => {
                setNewTaskMode(false);
                setSelectedRun(run.run_id);
              }}
            >
              <span className="run-task">{run.task || run.run_id}</span>
              <span className="run-meta">
                <span>{statusLabel(run.status)}</span>
                <span>{run.run_id}</span>
              </span>
            </button>
          ))}
        </div>
      </aside>

      <section className="center">
        <header className="topbar">
          <div>
            <h1>{selectedRun ? selectedTask || selectedRun : "新任务"}</h1>
            <p>{selectedRun ? `${statusLabel(currentStatus)} · ${activity.current_step?.label ?? phaseLabel(currentPhase)}` : "用一条消息开始新的 Patchbay 运行"}</p>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" onClick={() => void loadRuns()} aria-label="刷新运行">
              <RefreshCw size={17} />
            </button>
            <button className="detail-button" onClick={() => setDiagnosticsOpen((open) => !open)} aria-expanded={diagnosticsOpen}>
              <ChevronRight size={16} />
              诊断
            </button>
          </div>
        </header>

        {error ? <div className="error">{error}</div> : null}

        <section className="thread" aria-label="Patchbay Agent 对话线程">
          {!selectedRun ? (
            <>
              <div className="empty-thread">
                <Bot size={28} />
                <strong>告诉 Patchbay Agent 要做什么</strong>
                <span>它会先生成计划，后续批准、实现、测试、审查和应用都从这个线程推进。</span>
                <div className="empty-actions">
                  <button className="empty-action" type="button" onClick={() => void runSetupAction()} disabled={setupInFlight}>
                    {setupInFlight ? <RefreshCw size={14} /> : <Settings size={14} />}
                    {setupInFlight ? "运行中" : "运行 setup"}
                  </button>
                  <button
                    className="empty-action secondary"
                    type="button"
                    onClick={() => {
                      setDiagnosticsOpen(true);
                      setActiveTab("Readiness");
                    }}
                  >
                    <ShieldCheck size={14} />
                    就绪
                  </button>
                </div>
              </div>
              {localRunMessages.map((message) => (
                <ChatBubble key={message.id} role="user" title="本地消息" body={message.body} timestamp={message.timestamp} />
              ))}
              {newTaskReply ? <ChatBubble role="assistant" title="Patchbay Agent" body={newTaskReply.reply} tone={newTaskReply.ok === false ? "failed" : "ready"} /> : null}
            </>
          ) : (
            <>
              <ChatBubble role="user" title="任务" body={selectedTask || selectedRun} />
              <ChatBubble
                role="assistant"
                title={activity.headline ?? "Patchbay Agent 正在跟踪这次运行。"}
                body={conversationState?.next_step ?? activity.current_step?.summary}
                tone={activity.tone}
              />
              {messages.map((message) => (
                <AgentEventBubble key={message.id} message={message} selected={selectedMessage?.id === message.id} onSelect={() => setSelectedMessage(message)} />
              ))}
              {localRunMessages.map((message) => (
                <ChatBubble key={message.id} role="user" title="本地消息" body={message.body} timestamp={message.timestamp} />
              ))}
              <NextActionCard action={primaryAction} suggestions={suggestions} busy={runBusy || actionInFlight} onAction={handleAction} />
            </>
          )}
        </section>

        <form className="composer" onSubmit={(event) => void submitComposer(event)}>
          {selectedRun && suggestions.length ? (
            <div className="suggestions" aria-label="建议动作">
              {suggestions.map((suggestion) => (
                <button className={`suggestion ${suggestion.safe ? "" : "blocked"}`} type="button" key={suggestion.id} onClick={() => handleAction(suggestion)} disabled={interactionBusy}>
                  {suggestion.safe ? <Play size={13} /> : <AlertTriangle size={13} />}
                  {suggestion.label}
                </button>
              ))}
            </div>
          ) : null}
          <div className="composer-box">
            <textarea
              aria-label="给 Patchbay Agent 输入消息"
              value={composer}
              rows={2}
              onChange={(event) => setComposer(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder={composerPlaceholder}
              disabled={interactionBusy}
            />
            <button className="send-button" type="submit" disabled={interactionBusy || !composer.trim()} aria-label={selectedRun ? "发送消息" : "创建任务"}>
              <Send size={17} />
            </button>
          </div>
        </form>
      </section>

      <aside className="details" aria-label="诊断详情">
        {diagnosticsOpen ? (
          <>
            <div className="details-head">
              <strong>诊断</strong>
              <button className="icon-button" onClick={() => setDiagnosticsOpen(false)} aria-label="关闭诊断">
                <ChevronRight size={16} />
              </button>
            </div>
            <div className="tabs" role="tablist">
              {(["Overview", "Readiness", "Trace", "Log", "Diff", "Artifacts", "Config", "Providers"] as TabName[]).map((tab) => (
                <button role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? "active" : ""} key={tab} onClick={() => setActiveTab(tab)}>
                  {tabLabels[tab]}
                </button>
              ))}
            </div>
            <DetailPanel
              tab={activeTab}
              message={selectedMessage}
              rawTrace={rawTrace}
              trace={trace}
              diff={diff}
              artifactText={artifactText}
              config={config}
              doctor={doctor}
              onRunSetup={runSetupAction}
              onApplyEconomy={applyEconomyProfileAction}
              setupBusy={setupInFlight}
              profileBusy={profileInFlight}
              status={activeStatus}
              context={activeContext}
              activity={activity}
            />
          </>
        ) : null}
      </aside>

      {confirm ? (
        <div className="modal-backdrop">
          <div className="modal" role="dialog" aria-label={confirm.title}>
            <h2>{confirm.title}</h2>
            <p>{confirm.body}</p>
            <div className="modal-actions">
              <button onClick={() => setConfirm(null)}>{confirm.safe ? "取消" : "关闭"}</button>
              <button className={confirm.safe ? "danger" : ""} onClick={() => void confirmAction()}>
                {confirm.confirmLabel ?? "确认"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function ChatBubble({
  role,
  title,
  body,
  timestamp,
  tone
}: {
  role: "user" | "assistant";
  title: string;
  body?: string;
  timestamp?: string;
  tone?: string;
}) {
  return (
    <article className={`chat-bubble ${role} tone-${tone ?? "idle"}`}>
      <div className="avatar">{role === "user" ? <User size={16} /> : <Bot size={16} />}</div>
      <div className="bubble-body">
        <div className="bubble-title">
          <strong>{title}</strong>
          {timestamp ? <span>{timeLabel(timestamp)}</span> : null}
        </div>
        {body ? <p>{body}</p> : null}
      </div>
    </article>
  );
}

function AgentEventBubble({ message, selected, onSelect }: { message: AgentMessage; selected: boolean; onSelect: () => void }) {
  return (
    <button className={`chat-bubble event tone-${message.tone ?? "idle"} ${selected ? "selected" : ""}`} onClick={onSelect}>
      <div className="avatar">{message.kind === "gate" ? <ShieldCheck size={16} /> : message.kind === "agent" ? <Bot size={16} /> : <MessageSquare size={16} />}</div>
      <div className="bubble-body">
        <div className="bubble-title">
          <strong>{message.title}</strong>
          <span>{timeLabel(message.timestamp)}</span>
        </div>
        {message.body ? <p>{message.body}</p> : null}
        <small>{message.status_label ?? statusLabel(message.status)}</small>
      </div>
    </button>
  );
}

function NextActionCard({
  action,
  suggestions,
  busy,
  onAction
}: {
  action: AgentAction | null | undefined;
  suggestions: SuggestedAction[];
  busy?: boolean;
  onAction: (action: SuggestedAction | AgentAction | string) => void;
}) {
  if (busy) {
    return (
      <div className="next-card running" aria-label="后台任务运行中">
        <CircleDot size={16} />
        <div>
          <strong>后台任务运行中</strong>
          <span>Patchbay Agent 会自动刷新进度，完成后显示下一步。</span>
        </div>
      </div>
    );
  }
  if (!action && !suggestions.length) {
    return (
      <div className="next-card idle">
        <CircleDot size={16} />
        <div>
          <strong>等待下一步</strong>
          <span>当前没有可执行动作。</span>
        </div>
      </div>
    );
  }
  const primary = action ? actionFromSuggestion(action) : suggestions[0];
  return (
    <div className={`next-card ${primary?.safe ? "ready" : "blocked"}`} aria-label="下一步确认">
      {primary?.safe ? <Play size={16} /> : <AlertTriangle size={16} />}
      <div>
        <strong>{primary?.label ?? "下一步"}</strong>
        <span>{primary?.reason || "Patchbay Agent 已准备好继续。"}</span>
      </div>
      {primary ? (
        <button onClick={() => onAction(primary)}>
          {primary.safe ? <Play size={13} /> : <AlertTriangle size={13} />}
          {primary.requires_human_confirmation ? "确认" : "执行"}
        </button>
      ) : null}
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics?: RunMetrics | null }) {
  const phaseDurations = metricEntries(metrics);
  const slowestPhase = phaseDurations.reduce<[string, number] | null>((slowest, entry) => (!slowest || entry[1] > slowest[1] ? entry : slowest), null);
  const retries = retryEntries(metrics);
  const tokenByPhase = tokenEntries(metrics);
  const costByPhase = costEntries(metrics);
  const providerMetrics = providerMetricEntries(metrics);
  const providerCount = metrics?.provider_usage?.filter((item) => item.provider || item.model).length ?? 0;
  return (
    <div className="metrics-panel">
      <div className="metric-row">
        <span>总耗时</span>
        <strong>{metrics?.duration_known ? compactDuration(metrics.total_duration_ms) : "待采集"}</strong>
      </div>
      <div className="metric-row">
        <span>最慢阶段</span>
        <strong>{slowestPhase ? `${phaseLabel(slowestPhase[0])} ${compactDuration(slowestPhase[1])}` : "待采集"}</strong>
      </div>
      <div className="metric-row">
        <span>事件 / Trace</span>
        <strong>
          {metrics?.event_count ?? 0} / {metrics?.trace_count ?? 0}
        </strong>
      </div>
      <div className="metric-row">
        <span>阶段尝试</span>
        <strong>{totalAttempts(metrics) || "待记录"}</strong>
      </div>
      <div className="metric-row">
        <span>提供方轨迹</span>
        <strong>{providerCount || "待记录"}</strong>
      </div>
      <div className="metric-row">
        <span>Token</span>
        <strong>{metrics?.token_usage?.known ? compactNumber(metrics.token_usage.total_tokens) : "待上报"}</strong>
      </div>
      {tokenByPhase.length ? (
        <div className="phase-metrics" aria-label="Token 分布">
          {tokenByPhase.map(([phase, usage]) => (
            <span key={phase}>
              {phaseLabel(phase)} {compactNumber(usage?.total_tokens ?? 0)}
            </span>
          ))}
        </div>
      ) : null}
      <div className="metric-row">
        <span>成本</span>
        <strong>{metrics?.cost?.known ? `${metrics.cost.currency ?? "USD"} ${metrics.cost.estimated_total ?? 0}` : "未上报"}</strong>
      </div>
      {costByPhase.length ? (
        <div className="phase-metrics" aria-label="成本分布">
          {costByPhase.map(([phase, usage]) => (
            <span key={phase}>
              {phaseLabel(phase)} {(usage?.currency ?? metrics?.cost?.currency ?? "USD")} {compactNumber(usage?.estimated_total ?? 0)}
            </span>
          ))}
        </div>
      ) : null}
      {providerMetrics.length ? (
        <div className="phase-metrics" aria-label="Provider 消耗">
          {providerMetrics.map((item, index) => (
            <span key={`${item.phase}-${item.provider}-${item.model}-${index}`}>{providerMetricLabel(item)}</span>
          ))}
        </div>
      ) : null}
      {retries.length ? (
        <div className="metric-signals" aria-label="重试阶段">
          {retries.map(([phase, attempts]) => (
            <span key={phase}>
              {phaseLabel(phase)} {attempts}x
            </span>
          ))}
        </div>
      ) : null}
      {phaseDurations.length ? (
        <div className="phase-metrics" aria-label="阶段耗时">
          {phaseDurations.map(([phase, duration]) => (
            <span key={phase}>
              {phaseLabel(phase)} {compactDuration(duration)}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DoctorPanel({
  report,
  onRunSetup,
  onApplyEconomy,
  setupBusy,
  profileBusy
}: {
  report?: DoctorReport | null;
  onRunSetup?: () => void;
  onApplyEconomy?: () => void;
  setupBusy?: boolean;
  profileBusy?: boolean;
}) {
  const checks = Object.entries(report?.checks ?? {});
  return (
    <div className="doctor-panel">
      {onRunSetup ? (
        <div className="doctor-toolbar">
          <button className="doctor-setup-button" type="button" onClick={onRunSetup} disabled={setupBusy}>
            {setupBusy ? <RefreshCw size={14} /> : <Settings size={14} />}
            {setupBusy ? "运行中" : "运行 setup"}
          </button>
        </div>
      ) : null}
      <div className={`doctor-summary ${report?.ok ? "ready" : "blocked"}`}>
        {report?.ok ? <Check size={16} /> : <AlertTriangle size={16} />}
        <div>
          <strong>{report?.ok ? "环境就绪" : "需要处理"}</strong>
          <span>{report?.root ?? "正在读取 Patchbay doctor 结果"}</span>
        </div>
      </div>
      {report?.next_actions?.length ? (
        <section>
          <h2>下一步</h2>
          <div className="doctor-actions">
            {report.next_actions.map((action) => (
              <span key={action}>{action}</span>
            ))}
          </div>
        </section>
      ) : null}
      {report?.recommendations?.length ? (
        <section>
          <h2>建议</h2>
          <div className="doctor-recommendations">
            {report.recommendations.map((recommendation) => {
              const canApplyEconomy = /config profile apply economy|economy/i.test(recommendation);
              return (
                <div className="doctor-recommendation" key={recommendation}>
                  <span>{recommendation}</span>
                  {canApplyEconomy && onApplyEconomy ? (
                    <button type="button" onClick={onApplyEconomy} disabled={profileBusy}>
                      {profileBusy ? "应用中" : "应用经济路由"}
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}
      <section>
        <h2>检查项</h2>
        <div className="doctor-checks">
          {checks.length ? (
            checks.map(([name, check]) => (
              <div className={`doctor-check ${check.ok ? "ready" : check.skipped ? "idle" : "blocked"}`} key={name}>
                <span>{name}</span>
                <strong>{check.ok ? "通过" : check.skipped ? "跳过" : "需处理"}</strong>
                {check.error || check.note ? <small>{String(check.error ?? check.note)}</small> : null}
              </div>
            ))
          ) : (
            <div className="doctor-check idle">
              <span>doctor</span>
              <strong>加载中</strong>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function DetailPanel({
  tab,
  message,
  rawTrace,
  trace,
  diff,
  artifactText,
  config,
  doctor,
  onRunSetup,
  onApplyEconomy,
  setupBusy,
  profileBusy,
  status,
  context,
  activity
}: {
  tab: TabName;
  message: AgentMessage | null;
  rawTrace: TraceEntry[];
  trace: TraceEntry[];
  diff: string;
  artifactText: string;
  config: unknown;
  doctor: DoctorReport | null;
  onRunSetup?: () => void;
  onApplyEconomy?: () => void;
  setupBusy?: boolean;
  profileBusy?: boolean;
  status: RunStatus | null;
  context: HandoffContext | null;
  activity: AgentActivity;
}) {
  if (tab === "Overview") {
    const currentPhase = context?.current_phase ?? status?.current_phase ?? "";
    const currentStatus = context?.status ?? status?.status ?? "";
    const metrics = context?.run_metrics ?? status?.run_metrics;
    return (
      <div className="overview-panel">
        <section>
          <h2>效率</h2>
          <MetricsGrid metrics={metrics} />
        </section>
        <section>
          <h2>阶段</h2>
          <div className="phase-list">
            {phases.map((phase) => {
              const isCurrent = currentPhase === phase;
              const isDone = phase === "apply" ? currentStatus === "APPLIED" : phases.indexOf(phase) < phases.indexOf(currentPhase);
              return (
                <div className={`phase-row ${isCurrent ? "current" : ""} ${isDone ? "done" : ""}`} key={phase}>
                  {isDone ? <Check size={13} /> : <CircleDot size={11} />}
                  <span>{phaseLabel(phase)}</span>
                </div>
              );
            })}
          </div>
        </section>
        <section>
          <h2>门禁状态</h2>
          <div className="gate-list">
            {(activity.gate_cards ?? []).map((card) => (
              <div className={`gate-row tone-${card.tone ?? "idle"}`} key={card.key}>
                <span>{card.label}</span>
                <strong>{card.detail}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>
    );
  }
  if (tab === "Readiness") {
    return (
      <DoctorPanel
        report={doctor}
        onRunSetup={onRunSetup}
        onApplyEconomy={onApplyEconomy}
        setupBusy={setupBusy}
        profileBusy={profileBusy}
      />
    );
  }
  if (tab === "Trace") {
    return (
      <div className="diagnostic-body">
        <details className="provider-fold">
          <summary>Provider / model</summary>
          <pre>{JSON.stringify({ provider: message?.provider, model: message?.model, tool: message?.tool }, null, 2)}</pre>
        </details>
        <pre>{JSON.stringify({ selected_message: message ?? {}, timeline: trace, raw_trace: rawTrace }, null, 2)}</pre>
      </div>
    );
  }
  if (tab === "Diff") return <pre>{diff}</pre>;
  if (tab === "Log") return <pre>{artifactText}</pre>;
  if (tab === "Artifacts") {
    return (
      <div className="artifacts-panel">
        {(context?.artifacts ?? activity.artifacts ?? []).map((artifact) => (
          <div className="artifact-row" key={artifact.name}>
            <FileText size={15} />
            <div>
              <strong>{artifact.name}</strong>
              <span>{artifact.purpose}</span>
            </div>
          </div>
        ))}
        <pre>{artifactText}</pre>
      </div>
    );
  }
  if (tab === "Providers") {
    const providers = Object.entries(status?.effective_phase_providers ?? {});
    return (
      <div className="provider-list">
        {providers.map(([phase, provider]) => (
          <div className="provider-item" key={phase}>
            <span>{phaseLabel(phase)}</span>
            <strong>{provider.provider || "-"}</strong>
            <small>{provider.model || provider.command_key || "默认"}</small>
          </div>
        ))}
        {(context?.provider_trail ?? []).map((item, index) => (
          <div className="provider-item trail" key={`${item.phase}-${index}`}>
            <span>{phaseLabel(item.phase)}</span>
            <strong>{item.provider || "-"}</strong>
            <small>{item.model || item.status || "已记录"}</small>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="config-view">
      <Settings size={18} />
      <pre>{JSON.stringify(config, null, 2)}</pre>
    </div>
  );
}

export default Workbench;
