import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  FileText,
  GitPullRequest,
  MessageSquare,
  Play,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Trash2
} from "lucide-react";
import {
  AgentActivity,
  AgentMessage,
  createPatchbayClient,
  HandoffContext,
  PatchbayClient,
  RunStatus,
  RunSummary,
  TraceEntry
} from "./api";
import "./styles.css";

type TabName = "Trace" | "Log" | "Diff" | "Artifacts" | "Config" | "Providers";
type ConfirmState = { action: "apply" | "cleanup"; title: string; body: string } | null;

const phases = ["plan", "approve", "write", "test", "review", "fix", "apply", "cleanup"];
const phaseActions = ["approve", "write", "test", "review", "fix"];
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
  PASS: "通过",
  READY: "就绪",
  SUCCESS: "成功",
  ERROR: "错误",
  CHANGES_REQUESTED: "需要修改"
};
const tabLabels: Record<TabName, string> = {
  Trace: "活动",
  Log: "日志",
  Diff: "差异",
  Artifacts: "产物",
  Config: "配置",
  Providers: "提供方"
};
const defaultClient = createPatchbayClient();

function phaseLabel(phase?: string) {
  if (!phase) return "空闲";
  return phaseLabels[phase] ?? phase;
}

function statusLabel(status?: string | null) {
  if (!status) return "未知";
  return statusLabels[status] ?? status;
}

function commandLabel(command?: string) {
  if (!command) return "无";
  return actionLabels[command] ?? phaseLabel(command);
}

function timeLabel(timestamp?: string) {
  return timestamp ? timestamp.slice(11, 19) : "--:--:--";
}

function mergeContext(current: HandoffContext | null, next: HandoffContext): HandoffContext {
  if (!current) return next;
  const currentMessages = current.agent_activity?.messages ?? [];
  const nextMessages = next.agent_activity?.messages ?? [];
  const agentActivity = next.agent_activity
    ? {
        ...next.agent_activity,
        messages: nextMessages.length ? [...currentMessages, ...nextMessages] : currentMessages
      }
    : current.agent_activity;
  return { ...current, ...next, agent_activity: agentActivity };
}

function fallbackActivity(context: HandoffContext | null, status: RunStatus | null): AgentActivity {
  const nextAction = context?.next_actions?.find((action) => action.safe) ?? context?.next_actions?.[0] ?? null;
  const currentPhase = context?.current_phase ?? status?.current_phase ?? "";
  const currentStatus = context?.status ?? status?.status ?? "";
  const gateState = context?.gate_state ?? status?.gate_state ?? {};
  return {
    headline: nextAction
      ? `Patchbay Agent 已准备好执行：${commandLabel(nextAction.name)}。`
      : `Patchbay Agent 当前处于${phaseLabel(currentPhase)}阶段。`,
    tone: nextAction ? "ready" : "idle",
    current_step: {
      phase: currentPhase,
      label: phaseLabel(currentPhase),
      status: currentStatus,
      status_label: statusLabel(currentStatus),
      summary: nextAction?.reason ?? "暂无可执行动作。"
    },
    next_action: nextAction ? { ...nextAction, label: commandLabel(nextAction.name) } : null,
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
      tone: entry.status === "PASS" || entry.status === "SUCCESS" ? "success" : entry.status === "ERROR" ? "failed" : "idle",
      artifacts: entry.artifact_paths,
      provider: entry.provider ?? entry.agent,
      model: entry.model,
      tool: entry.tool ?? entry.next_action
    }))
  };
}

export function Workbench({ client = defaultClient, pollIntervalMs = 4000 }: { client?: PatchbayClient; pollIntervalMs?: number }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [context, setContext] = useState<HandoffContext | null>(null);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [rawTrace, setRawTrace] = useState<TraceEntry[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<AgentMessage | null>(null);
  const eventCursor = useRef(0);
  const [diff, setDiff] = useState("");
  const [artifactText, setArtifactText] = useState("");
  const [config, setConfig] = useState<unknown>(null);
  const [activeTab, setActiveTab] = useState<TabName>("Trace");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const [error, setError] = useState("");

  const loadRuns = async () => {
    const result = await client.listRuns();
    setRuns(result.runs ?? []);
    if (!selectedRun && result.runs?.[0]) setSelectedRun(result.runs[0].run_id);
  };

  useEffect(() => {
    void loadRuns().catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!selectedRun) return;
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
    if (!visibleRuns.length) {
      if (selectedRun) setSelectedRun("");
      return;
    }
    if (!visibleRuns.some((run) => run.run_id === selectedRun)) {
      setSelectedRun(visibleRuns[0].run_id);
    }
  }, [visibleRuns, selectedRun]);

  const selectedSummary = useMemo(() => runs.find((run) => run.run_id === selectedRun), [runs, selectedRun]);
  const activity = context?.agent_activity ?? fallbackActivity(context, status);
  const gateState = context?.gate_state ?? status?.gate_state ?? {};
  const readyToApply = Boolean(gateState.ready_to_apply);
  const messages = activity.messages ?? [];
  const primaryAction = activity.next_action;
  const currentPhase = context?.current_phase ?? status?.current_phase ?? "";
  const currentStatus = selectedSummary?.status ?? context?.status ?? status?.status;
  const headerMeta = selectedRun
    ? `${statusLabel(currentStatus)} / ${activity.current_step?.label ?? phaseLabel(currentPhase)}`
    : "选择一次运行，查看 Patchbay Agent 的统一活动流。";

  const loadContextNow = async () => {
    if (!selectedRun) return;
    const nextContext = await client.getContext(selectedRun);
    setContext(nextContext);
    setTrace(nextContext.timeline ?? []);
    setSelectedMessage(nextContext.agent_activity?.messages?.[0] ?? null);
    eventCursor.current = nextContext.cursors?.event ?? 0;
  };

  const runAction = async (action: string) => {
    if (!selectedRun) return;
    setError("");
    await client.runAction(selectedRun, action);
    await loadRuns();
    setStatus(await client.getStatus(selectedRun));
    await loadContextNow();
  };

  const handleAction = (action?: string | null) => {
    if (!action) return;
    if (action === "apply") {
      setConfirm({ action: "apply", title: "确认应用", body: "将已审查通过的 FINAL.diff 应用到当前工作区。" });
      return;
    }
    if (action === "cleanup") {
      setConfirm({ action: "cleanup", title: "确认清理", body: "移除本次运行的 worktree 和临时资源。" });
      return;
    }
    void runAction(action);
  };

  const confirmAction = async () => {
    if (!confirm || !selectedRun) return;
    setError("");
    if (confirm.action === "apply") await client.apply(selectedRun);
    if (confirm.action === "cleanup") await client.cleanup(selectedRun);
    setConfirm(null);
    await loadRuns();
    setStatus(await client.getStatus(selectedRun));
    await loadContextNow();
  };

  return (
    <main className="workbench">
      <aside className="sidebar">
        <div className="brand">
          <GitPullRequest size={20} />
          <div>
            <strong>Patchbay Agent</strong>
            <span>多 Agent 协作，一个工作界面</span>
          </div>
        </div>
        <label className="search">
          <Search size={15} />
          <input aria-label="搜索运行" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索运行" />
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
        <div className="run-list">
          {visibleRuns.map((run) => (
            <button className={`run-item ${run.run_id === selectedRun ? "selected" : ""}`} key={run.run_id} onClick={() => setSelectedRun(run.run_id)}>
              <span className="run-id">{run.run_id}</span>
              <span className="run-task">{run.task}</span>
              <span className="status-pill">{statusLabel(run.status)}</span>
            </button>
          ))}
        </div>
      </aside>

      <section className="center">
        <header className="topbar">
          <div>
            <h1>{selectedSummary?.task || selectedRun || "未选择运行"}</h1>
            <p>{headerMeta}</p>
          </div>
          <button className="icon-button" onClick={() => void loadRuns()} aria-label="刷新运行">
            <RefreshCw size={17} />
          </button>
        </header>

        {error ? <div className="error">{error}</div> : null}

        <section className={`agent-hero tone-${activity.tone ?? "idle"}`}>
          <div className="agent-mark">
            <Bot size={24} />
          </div>
          <div className="agent-copy">
            <span>{activity.current_step?.label ?? phaseLabel(currentPhase)}</span>
            <strong>{activity.headline}</strong>
            <p>{activity.current_step?.summary}</p>
          </div>
          <button
            className="primary-action"
            disabled={!primaryAction?.safe}
            onClick={() => handleAction(primaryAction?.name)}
          >
            <Play size={15} />
            {primaryAction?.label ?? "等待下一步"}
          </button>
        </section>

        <section className="gate-strip" aria-label="门禁状态">
          {(activity.gate_cards ?? []).map((card) => (
            <div className={`gate-card tone-${card.tone ?? "idle"}`} key={card.key}>
              <span>{card.label}</span>
              <strong>{card.detail}</strong>
            </div>
          ))}
        </section>

        <section className="phase-strip" aria-label="阶段进度">
          {phases.map((phase) => {
            const currentStatusValue = context?.status ?? status?.status;
            const isCurrent = currentPhase === phase;
            const isDone = phase === "apply" ? currentStatusValue === "APPLIED" : phases.indexOf(phase) < phases.indexOf(currentPhase);
            return (
              <div className={`phase ${isCurrent ? "current" : ""} ${isDone ? "done" : ""}`} key={phase}>
                {isDone ? <Check size={13} /> : <CircleDot size={11} />}
                <b>{phaseLabel(phase)}</b>
              </div>
            );
          })}
        </section>

        <section className="actions" aria-label="阶段操作">
          {phaseActions.map((action) => (
            <button
              key={action}
              onClick={() => void runAction(action)}
              disabled={
                context?.next_actions?.length
                  ? !context.next_actions.some((next) => next.name === action && next.safe)
                  : !status?.next_commands?.includes(action)
              }
            >
              <Play size={14} />
              {actionLabels[action] ?? `执行 ${phaseLabel(action)}`}
            </button>
          ))}
          <button className="danger" disabled={!readyToApply} onClick={() => handleAction("apply")}>
            <AlertTriangle size={14} />
            应用已审查 diff
          </button>
          <button className="danger ghost" onClick={() => handleAction("cleanup")}>
            <Trash2 size={14} />
            清理运行
          </button>
        </section>

        <section className="conversation" aria-label="Agent 活动流">
          {messages.length ? (
            messages.map((message) => (
              <button
                className={`message tone-${message.tone ?? "idle"} ${selectedMessage?.id === message.id ? "selected" : ""}`}
                key={message.id}
                onClick={() => setSelectedMessage(message)}
              >
                <span className="message-time">{timeLabel(message.timestamp)}</span>
                <span className="message-icon">
                  {message.kind === "gate" ? <ShieldCheck size={16} /> : message.kind === "agent" ? <Bot size={16} /> : <MessageSquare size={16} />}
                </span>
                <span className="message-main">
                  <strong>{message.title}</strong>
                  {message.body ? <small>{message.body}</small> : null}
                </span>
                <span className="message-status">{message.status_label ?? statusLabel(message.status)}</span>
              </button>
            ))
          ) : (
            <div className="empty-state">暂无活动。Patchbay Agent 会在这里记录计划、实现、测试和审查进展。</div>
          )}
        </section>
      </section>

      <aside className={`details ${diagnosticsOpen ? "open" : ""}`}>
        <button className="diagnostic-toggle" onClick={() => setDiagnosticsOpen((open) => !open)} aria-expanded={diagnosticsOpen}>
          {diagnosticsOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          诊断
        </button>
        <div className="tabs" role="tablist">
          {(["Trace", "Log", "Diff", "Artifacts", "Config", "Providers"] as TabName[]).map((tab) => (
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
          status={status}
        />
      </aside>

      {confirm ? (
        <div className="modal-backdrop">
          <div className="modal" role="dialog" aria-label={confirm.title}>
            <h2>{confirm.title}</h2>
            <p>{confirm.body}</p>
            <div className="modal-actions">
              <button onClick={() => setConfirm(null)}>取消</button>
              <button className="danger" onClick={() => void confirmAction()}>
                确认
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
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
  status
}: {
  tab: TabName;
  message: AgentMessage | null;
  rawTrace: TraceEntry[];
  trace: TraceEntry[];
  diff: string;
  artifactText: string;
  config: unknown;
  status: RunStatus | null;
}) {
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
  if (tab === "Log" || tab === "Artifacts") return <pre>{artifactText}</pre>;
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
      </div>
    );
  }
  return (
    <div className="config-view">
      <Settings size={18} />
      <pre>{JSON.stringify(config, null, 2)}</pre>
      <FileText size={1} />
    </div>
  );
}

export default Workbench;
