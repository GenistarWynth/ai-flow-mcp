import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, FileText, GitPullRequest, Play, RefreshCw, Search, Settings, Trash2 } from "lucide-react";
import { createPatchbayClient, PatchbayClient, RunStatus, RunSummary, TraceEntry } from "./api";
import "./styles.css";

type TabName = "Trace" | "Log" | "Diff" | "Artifacts" | "Config" | "Providers";
type ConfirmState = { action: "apply" | "cleanup"; title: string; body: string } | null;

const phases = ["plan", "approve", "write", "test", "review", "fix", "apply", "cleanup"];
const actions = ["approve", "write", "test", "review", "fix"];
const phaseLabels: Record<string, string> = {
  plan: "计划",
  approve: "批准",
  write: "编写",
  test: "测试",
  review: "审查",
  fix: "修复",
  apply: "应用",
  cleanup: "清理"
};
const actionLabels: Record<string, string> = {
  approve: "批准",
  write: "执行编写",
  test: "运行测试",
  review: "执行审查",
  fix: "执行修复",
  start: "开始",
  success: "完成",
  gate: "门禁",
  error: "错误",
  failed: "失败"
};
const statusLabels: Record<string, string> = {
  PLANNED: "已计划",
  APPROVED: "已批准",
  IMPLEMENTING: "编写中",
  IMPLEMENTED: "已编写",
  TESTED: "已测试",
  REVIEWED_PASS: "审查通过",
  REVIEWED_CHANGES_REQUESTED: "需修复",
  APPLIED: "已应用",
  FAILED: "失败",
  RUNNING: "运行中",
  PASS: "通过",
  READY: "就绪",
  SUCCESS: "成功",
  ERROR: "错误"
};
const tabLabels: Record<TabName, string> = {
  Trace: "轨迹",
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

export function Workbench({ client = defaultClient, pollIntervalMs = 4000 }: { client?: PatchbayClient; pollIntervalMs?: number }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<TraceEntry | null>(null);
  const traceCursor = useRef(0);
  const [diff, setDiff] = useState("");
  const [artifactText, setArtifactText] = useState("");
  const [config, setConfig] = useState<unknown>(null);
  const [activeTab, setActiveTab] = useState<TabName>("Trace");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
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
    setSelectedTrace(null);
    traceCursor.current = 0;
    function appendTraceEntries(entries: TraceEntry[], total?: number, since = 0, replace = false) {
      setTrace((current) => {
        const nextEntries = replace ? entries : [...current, ...entries];
        setSelectedTrace((selected) => selected ?? nextEntries[0] ?? null);
        return nextEntries;
      });
      traceCursor.current = total ?? (entries.at(-1)?.index ?? since - 1) + 1;
    }
    async function loadSelectedRun() {
      const [nextStatus, nextTrace, nextDiff, nextConfig] = await Promise.all([
        client.getStatus(selectedRun),
        client.getTrace(selectedRun),
        client.getDiff(selectedRun),
        client.getConfig()
      ]);
      if (cancelled) return;
      const entries = nextTrace.trace ?? nextTrace.events ?? [];
      setStatus(nextStatus);
      appendTraceEntries(entries, nextTrace.total, 0, true);
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
    async function loadTraceUpdate() {
      const since = traceCursor.current;
      const nextTrace = await client.getTrace(selectedRun, { since });
      if (cancelled) return;
      appendTraceEntries(nextTrace.trace ?? nextTrace.events ?? [], nextTrace.total, since);
    }
    void loadSelectedRun().catch((err) => setError(String(err)));
    const timer = pollIntervalMs > 0 ? window.setInterval(() => {
      void loadTraceUpdate().catch((err) => setError(String(err)));
    }, pollIntervalMs) : undefined;
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
  const readyToApply = Boolean(status?.gate_state?.ready_to_apply);
  const nextCommandText = status?.next_commands?.length ? status.next_commands.map(commandLabel).join("、") : "无";
  const headerMeta = selectedRun
    ? `状态：${statusLabel(selectedSummary?.status ?? status?.status)} / 当前阶段：${phaseLabel(status?.current_phase)} / 可执行：${nextCommandText}`
    : "请选择一次运行，查看各 Agent 的阶段与工具调用。";
  const gateState = status?.gate_state ?? {};

  const runAction = async (action: string) => {
    if (!selectedRun) return;
    setError("");
    await client.runAction(selectedRun, action);
    await loadRuns();
    setStatus(await client.getStatus(selectedRun));
  };

  const confirmAction = async () => {
    if (!confirm || !selectedRun) return;
    setError("");
    if (confirm.action === "apply") await client.apply(selectedRun);
    if (confirm.action === "cleanup") await client.cleanup(selectedRun);
    setConfirm(null);
    await loadRuns();
  };

  return (
    <main className="workbench">
      <aside className="sidebar">
        <div className="brand">
          <GitPullRequest size={20} />
          <div>
            <strong>Patchbay 可视化工作台</strong>
            <span>本机编排与轨迹控制台</span>
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
            <option value="PLANNED">已计划</option>
            <option value="IMPLEMENTING">编写中</option>
            <option value="REVIEWED_PASS">审查通过</option>
            <option value="REVIEWED_CHANGES_REQUESTED">需修复</option>
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
            <h1>{selectedRun || "未选择运行"}</h1>
            <p>{headerMeta}</p>
          </div>
          <button className="icon-button" onClick={() => void loadRuns()} aria-label="刷新运行">
            <RefreshCw size={17} />
          </button>
        </header>

        {error ? <div className="error">{error}</div> : null}

        <section className="gate-strip" aria-label="门禁状态">
          <div>
            <span>门禁状态</span>
            <strong>{readyToApply ? "可应用" : "等待通过"}</strong>
          </div>
          <div>
            <span>批准</span>
            <strong>{gateState.approved ? "已批准" : "未批准"}</strong>
          </div>
          <div>
            <span>测试</span>
            <strong>{gateState.tests_passed || status?.tests_passed ? "通过" : "未通过"}</strong>
          </div>
          <div>
            <span>审查</span>
            <strong>{statusLabel(gateState.review_result ?? status?.review_result)}</strong>
          </div>
        </section>

        <section className="phase-strip">
          {phases.map((phase) => {
            const isCurrent = status?.current_phase === phase;
            const isDone = phase === "apply" ? status?.status === "APPLIED" : phases.indexOf(phase) < phases.indexOf(status?.current_phase ?? "");
            return (
              <div className={`phase ${isCurrent ? "current" : ""} ${isDone ? "done" : ""}`} key={phase}>
                {isDone ? <Check size={14} /> : <span />}
                <b>{phaseLabel(phase)}</b>
              </div>
            );
          })}
        </section>

        <section className="actions">
          {actions.map((action) => (
            <button key={action} onClick={() => void runAction(action)} disabled={!status?.next_commands?.includes(action)}>
              <Play size={14} />
              {actionLabels[action] ?? `执行 ${phaseLabel(action)}`}
            </button>
          ))}
          <button className="danger" disabled={!readyToApply} onClick={() => setConfirm({ action: "apply", title: "确认应用", body: "将已审查通过的 FINAL.diff 应用到当前工作区。" })}>
            <AlertTriangle size={14} />
            应用已审查 diff
          </button>
          <button className="danger ghost" onClick={() => setConfirm({ action: "cleanup", title: "确认清理", body: "移除本次运行的 worktree 和临时资源。" })}>
            <Trash2 size={14} />
            清理运行
          </button>
        </section>

        <section className="timeline">
          <div className="trace-head" aria-hidden="true">
            <span>时间</span>
            <span>智能体</span>
            <span>阶段</span>
            <span>动作</span>
            <span>工具</span>
            <span>路径</span>
            <span>状态</span>
            <span>摘要</span>
          </div>
          {trace.map((entry, index) => (
            <button className="trace-row" key={`${entry.index ?? entry.seq ?? index}-${entry.timestamp ?? index}`} onClick={() => setSelectedTrace(entry)}>
              <span className="time">{entry.timestamp?.slice(11, 19) ?? "--:--:--"}</span>
              <span className="agent">智能体：{entry.agent ?? "patchbay"}</span>
              <span className="phase-name">{phaseLabel(entry.phase)}</span>
              <span className="action-name">{commandLabel(entry.action)}</span>
              <span className="tool">{entry.tool}</span>
              <span className="path">{entry.path}</span>
              <span className={`trace-status ${entry.status ?? ""}`}>{statusLabel(entry.status)}</span>
              <span className="detail">{entry.detail}</span>
            </button>
          ))}
        </section>
      </section>

      <aside className="details">
        <div className="tabs" role="tablist">
          {(["Trace", "Log", "Diff", "Artifacts", "Config", "Providers"] as TabName[]).map((tab) => (
            <button role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? "active" : ""} key={tab} onClick={() => setActiveTab(tab)}>
              {tabLabels[tab]}
            </button>
          ))}
        </div>
        <DetailPanel tab={activeTab} trace={selectedTrace} diff={diff} artifactText={artifactText} config={config} status={status} />
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

function DetailPanel({ tab, trace, diff, artifactText, config, status }: { tab: TabName; trace: TraceEntry | null; diff: string; artifactText: string; config: unknown; status: RunStatus | null }) {
  if (tab === "Trace") return <pre>{JSON.stringify(trace ?? {}, null, 2)}</pre>;
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
