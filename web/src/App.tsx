import { FormEvent, Fragment, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Check,
  ChevronRight,
  CircleDot,
  Copy,
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
  User,
  XCircle
} from "lucide-react";
import {
  ActionGroup,
  AgentResponse,
  AgentActivity,
  AgentAction,
  AgentHealthAction,
  AgentHealthCard,
  AgentMessage,
  BackgroundJob,
  ConfigProfileStatus,
  createPatchbayClient,
  DoctorCheck,
  DoctorReport,
  EfficiencySummary,
  FailureRecovery,
  GateDiagnosis,
  HandoffContext,
  NextAction,
  PatchbayClient,
  PhaseProvider,
  PhaseStrategy,
  ProviderUsage,
  RoutingEvidence,
  RunMetrics,
  RunReferenceView,
  RunStatus,
  RunsInbox,
  RunSummary,
  SuggestedAction,
  TierUsage,
  TraceEntry
} from "./api";
import "./styles.css";

type TabName = "Overview" | "Readiness" | "Trace" | "Log" | "Diff" | "Artifacts" | "Config" | "Providers";
type ConfirmState = { action: string; title: string; body: string; safe: boolean; confirmLabel?: string; runId?: string } | null;
type LocalMessage = { id: string; body: string; timestamp: string; role?: "user" | "assistant"; response?: AgentResponse; hideBubble?: boolean };
type DoctorProfileStatus = {
  profile?: string;
  recommendation?: string;
  economy?: {
    matches?: boolean;
    target?: PhaseProvider;
    intent?: string;
    write?: PhaseProvider;
    fix?: PhaseProvider;
  };
  phase_strategy?: Record<string, PhaseStrategy>;
};
type LocalReplyAction = {
  id: string;
  sourceId?: string;
  label: string;
  message: string;
  icon: "play" | "settings" | "shield" | "search";
  host?: string;
  runId?: string;
  tab?: RunReferenceView["tab"];
  phaseAction?: "approve" | "apply" | "continue";
  safe?: boolean;
  requiresConfirmation?: boolean;
  reason?: string;
  skipMcp?: boolean;
};
type SetupHostOption = {
  id: string;
  label: string;
  message: string;
};
type EconomyProviderDraft = {
  providerId: string;
  command: string;
  model: string;
  label: string;
};

const phases = ["plan", "approve", "write", "test", "review", "fix", "apply", "cleanup"];
const strategyPhases = ["plan", "write", "fix", "review"];
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
const diagnosticTabs = new Set<TabName>(["Trace", "Log", "Diff", "Artifacts", "Config", "Providers"]);
const defaultClient = createPatchbayClient();
const busyStatuses = new Set(["IMPLEMENTING", "TESTING", "REVIEWING", "FIXING", "RUNNING"]);
const setupHostOptions: SetupHostOption[] = [
  { id: "codex", label: "Codex", message: "patchbay setup" },
  { id: "claude-code", label: "Claude Code", message: "patchbay setup for claude-code" },
  { id: "claude-desktop", label: "Claude Desktop", message: "patchbay setup for claude-desktop" },
  { id: "gemini", label: "Gemini", message: "install patchbay for gemini" }
];
const setupHostLabels = new Map(setupHostOptions.map((host) => [host.id, host.label]));
const setupHostAliases: Record<string, string[]> = {
  codex: ["codex desktop", "codex 桌面"],
  "claude-code": ["claude code", "claude 代码"],
  "claude-desktop": ["claude desktop", "claude 桌面"],
  gemini: ["gemini cli", "gemini 命令行"]
};

function phaseLabel(phase?: string) {
  if (!phase) return "空闲";
  return phaseLabels[phase] ?? phase;
}

function setupHostLabel(host?: string | null) {
  if (!host) return "Codex";
  return setupHostLabels.get(host) ?? host;
}

function setupHostById(host?: string | null) {
  return setupHostOptions.find((option) => option.id === host) ?? setupHostOptions[0];
}

function setupHostFromText(raw: string) {
  const text = raw.toLowerCase();
  return (
    setupHostOptions.find((host) => text.includes(host.id) || text.includes(host.label.toLowerCase())) ??
    setupHostOptions.find((host) => setupHostAliases[host.id]?.some((alias) => text.includes(alias))) ??
    null
  );
}

function setupMessageToHost(message: string) {
  return setupHostOptions.find((host) => host.message === message) ?? setupHostFromText(message) ?? setupHostOptions[0];
}

function setupWithoutMcpMessage(host?: SetupHostOption) {
  return host && host.id !== "codex" ? `patchbay setup without MCP for ${host.id}` : "patchbay setup without MCP";
}

function setupHostFromAction(action: AgentHealthAction, fallback: SetupHostOption) {
  if (action.host) return setupHostById(action.host);
  if (action.message) {
    const host = setupHostOptions.find((option) => option.message === action.message);
    if (host) return host;
  }
  return fallback;
}

function setupHostFromLocalReplyAction(action: Pick<LocalReplyAction, "host" | "message">) {
  if (action.host) return setupHostById(action.host);
  return setupMessageToHost(action.message);
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

function localReplyActions(response: AgentResponse | null): LocalReplyAction[] {
  const seen = new Set<string>();
  const result: LocalReplyAction[] = [];
  for (const action of response?.actions ?? []) {
    const mapped = enrichLocalReplyAction(mapStructuredLocalReplyAction(action), response);
    if (!mapped || seen.has(mapped.id)) continue;
    seen.add(mapped.id);
    result.push({ ...mapped, sourceId: action.id || action.message || action.command || mapped.id });
  }
  const actions = response?.next_actions ?? [];
  for (const raw of actions) {
    const mapped = enrichLocalReplyAction(mapLocalReplyAction(raw), response);
    if (!mapped || seen.has(mapped.id)) continue;
    seen.add(mapped.id);
    result.push({ ...mapped, sourceId: raw });
  }
  const primaryAction = mapPrimaryNextLocalReplyAction(response);
  if (primaryAction && !seen.has(primaryAction.id)) {
    seen.add(primaryAction.id);
    result.push({ ...primaryAction, sourceId: primaryAction.sourceId ?? primaryAction.id });
  }
  const gateAction = mapGateNextLocalReplyAction(response);
  if (gateAction && !seen.has(gateAction.id)) {
    seen.add(gateAction.id);
    result.push({ ...gateAction, sourceId: gateAction.sourceId ?? gateAction.id });
  }
  return result;
}

function localReplyActionGroups(response: AgentResponse | null, actions: LocalReplyAction[]) {
  const groups = response?.action_groups ?? [];
  if (!groups.length) {
    return actions.length ? [{ id: "suggested", label: "建议动作", reason: undefined, actions }] : [];
  }
  const bySource = new Map<string, LocalReplyAction>();
  for (const action of actions) {
    for (const key of localReplyActionKeys(action)) {
      bySource.set(key, action);
    }
  }
  const used = new Set<string>();
  const result: { id: string; label: string; reason?: string; actions: LocalReplyAction[] }[] = [];
  for (const group of groups) {
    const grouped = (group.action_ids ?? []).map((id) => bySource.get(id)).filter(Boolean) as LocalReplyAction[];
    const unique = grouped.filter((action) => {
      if (used.has(action.id)) return false;
      used.add(action.id);
      return true;
    });
    if (unique.length) {
      result.push({ id: group.id, label: localReplyActionGroupLabel(group), reason: group.reason, actions: unique });
    }
  }
  const remaining = actions.filter((action) => !used.has(action.id));
  if (remaining.length) result.push({ id: "suggested", label: "建议动作", actions: remaining });
  return result;
}

function localReplyActionKeys(action: LocalReplyAction) {
  return dedupeStrings([action.sourceId, action.id, action.message, action.label]);
}

function localReplyActionGroupLabel(group: ActionGroup) {
  const labels: Record<string, string> = {
    background_polling: "后台轮询",
    background_control: "后台控制",
    routing: "经济路由",
    setup: "就绪设置",
    diagnostics: "诊断",
    gate: "门禁动作",
    new_task: "新任务",
    commands: "命令",
    local: "本地 Agent"
  };
  return labels[group.id] ?? group.label ?? "建议动作";
}

function groupedHealthActions(actions: AgentHealthAction[] | undefined, groups: ActionGroup[] | undefined) {
  const safeActions = (actions ?? []).filter((item) => item.safe !== false);
  if (!safeActions.length) return [];
  if (!groups?.length) return [{ id: "suggested", label: "建议动作", reason: undefined, actions: safeActions }];
  const byId = new Map<string, AgentHealthAction>();
  for (const action of safeActions) {
    for (const key of healthActionKeys(action)) {
      byId.set(key, action);
    }
  }
  const used = new Set<string>();
  const result: { id: string; label: string; reason?: string; actions: AgentHealthAction[] }[] = [];
  for (const group of groups) {
    const grouped = (group.action_ids ?? []).map((id) => byId.get(id)).filter(Boolean) as AgentHealthAction[];
    const unique = grouped.filter((action) => {
      const key = healthActionKey(action);
      if (used.has(key)) return false;
      used.add(key);
      return true;
    });
    if (unique.length) result.push({ id: group.id, label: localReplyActionGroupLabel(group), reason: group.reason, actions: unique });
  }
  const remaining = safeActions.filter((action) => !used.has(healthActionKey(action)));
  if (remaining.length) result.push({ id: "suggested", label: "建议动作", actions: remaining });
  return result;
}

function healthActionKeys(action: AgentHealthAction) {
  return dedupeStrings([action.id, action.message, action.command, action.label]);
}

function healthActionKey(action: AgentHealthAction) {
  return healthActionKeys(action)[0] ?? action.label;
}

function enrichLocalReplyAction(action: LocalReplyAction | null, response?: AgentResponse | null): LocalReplyAction | null {
  if (!action || action.id !== "open-latest-run") return action;
  const runId = action.runId ?? response?.run_reference?.run_id ?? response?.recent_run?.run_id ?? response?.run_id ?? undefined;
  const tab = action.tab ?? requestedTabFromAgentResponse(response) ?? undefined;
  return { ...action, runId: runId || undefined, tab };
}

function localReplyCommandActions(response: AgentResponse | null): AgentHealthAction[] {
  const seen = new Set<string>();
  const result: AgentHealthAction[] = [];
  for (const action of response?.actions ?? []) {
    if (action.safe === false || action.kind !== "command" || !action.command) continue;
    const key = action.id || action.command;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(action);
  }
  return result;
}

function localReplyCommandActionGroups(response: AgentResponse | null, commands: AgentHealthAction[]) {
  if (!commands.length) return [];
  const groups = response?.action_groups ?? [];
  if (!groups.length) {
    return [{ id: "commands", label: "命令", reason: undefined, actions: commands }];
  }
  const byKey = new Map<string, AgentHealthAction>();
  for (const action of commands) {
    for (const key of healthActionKeys(action)) {
      byKey.set(key, action);
    }
  }
  const used = new Set<string>();
  const result: { id: string; label: string; reason?: string; actions: AgentHealthAction[] }[] = [];
  for (const group of groups) {
    const grouped = (group.action_ids ?? []).map((id) => byKey.get(id)).filter(Boolean) as AgentHealthAction[];
    const unique = grouped.filter((action) => {
      const key = healthActionKey(action);
      if (used.has(key)) return false;
      used.add(key);
      return true;
    });
    if (unique.length) result.push({ id: group.id, label: localReplyActionGroupLabel(group), reason: group.reason, actions: unique });
  }
  const remaining = commands.filter((action) => !used.has(healthActionKey(action)));
  if (remaining.length) result.push({ id: "commands", label: "命令", actions: remaining });
  return result;
}

function dedupeStrings(items: Array<string | null | undefined>) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of items) {
    const value = item?.trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

function mapPrimaryNextLocalReplyAction(response: AgentResponse | null): LocalReplyAction | null {
  if (!response?.run_id) return null;
  const action = response.next_action ?? response.run_reference?.next_action ?? null;
  return mapNextActionLocalReplyAction(action, { idPrefix: "next" });
}

function mapGateNextLocalReplyAction(response: AgentResponse | null): LocalReplyAction | null {
  if (!response?.run_id) return null;
  return mapNextActionLocalReplyAction(response.gate_diagnosis?.next_action ?? null, { idPrefix: "gate", requireConfirmation: true });
}

function mapNextActionLocalReplyAction(
  action: AgentHealthAction | null | undefined,
  options: { idPrefix: string; requireConfirmation?: boolean }
): LocalReplyAction | null {
  if (!action?.message) return null;
  if (options.requireConfirmation && !action.requires_confirmation) return null;
  const message = action.message.toLowerCase();
  const phaseAction = message.includes("apply") ? "apply" : message.includes("approve") ? "approve" : message.includes("continue") ? "continue" : null;
  if (!phaseAction) return null;
  const requiresConfirmation = Boolean(action.requires_confirmation);
  return {
    id: `${options.idPrefix}-${phaseAction}`,
    label: action.label || commandLabel(phaseAction),
    message: action.message,
    icon: phaseAction === "approve" ? "shield" : "play",
    phaseAction,
    safe: requiresConfirmation || action.safe !== false,
    requiresConfirmation,
    reason: action.reason
  };
}

function isReasonixConfigureText(raw = "") {
  const text = raw.toLowerCase();
  if (text.includes("configure reasonix command") || text.includes("commands.reasonix")) return true;
  return (
    text.includes("reasonix") &&
    includesAny(text, ["配置", "设置", "设为", "指定", "安装", "使用"]) &&
    includesAny(text, ["命令", "路径", "可执行", "程序"])
  );
}

function isConfigureReasonixAction(action: Pick<AgentHealthAction, "id" | "message">) {
  return action.id === "configure_reasonix_command" || isReasonixConfigureText(action.message);
}

function isNoMcpSetupText(raw = "") {
  const text = raw.toLowerCase();
  const compact = text.replace(/[’']/g, "").replace(/[\s\-_]+/g, "");
  return includesAny(text, [
    "--skip-mcp",
    "skip mcp",
    "without mcp",
    "no mcp",
    "omit mcp",
    "avoid mcp",
    "do not use mcp",
    "dont use mcp",
    "don't use mcp",
    "do not register mcp",
    "dont register mcp",
    "don't register mcp",
    "不注册 mcp",
    "不要注册 mcp",
    "不要用 mcp",
    "不要用这个 mcp",
    "别用 mcp",
    "跳过 mcp",
    "不用 mcp",
    "不要 mcp"
  ]) || includesAny(compact, [
    "skipmcp",
    "withoutmcp",
    "nomcp",
    "omitmcp",
    "avoidmcp",
    "donotusemcp",
    "dontusemcp",
    "localonly",
    "skillonly",
    "不注册mcp",
    "不要注册mcp",
    "不要用mcp",
    "不要用这个mcp",
    "别用mcp",
    "跳过mcp",
    "不用mcp",
    "不要mcp"
  ]);
}

function isSkillOnlySetupText(raw = "") {
  const text = raw.toLowerCase();
  return text.includes("skill") && !text.includes("mcp") && includesAny(text, ["configure", "install", "setup", "安装"]);
}

function isMcpOnlySetupText(raw = "") {
  const text = raw.toLowerCase();
  return (
    !isNoMcpSetupText(text) &&
    text.includes("mcp") &&
    !text.includes("skill") &&
    includesAny(text, ["configure", "install", "register", "setup", "注册", "安装"])
  );
}

function mapScopedSetupAction(raw: string): LocalReplyAction | null {
  const setupHost = setupHostFromText(raw.toLowerCase());
  if (isSkillOnlySetupText(raw)) {
    return {
      id: "install-skill-only",
      label: raw || "Install Codex Skill",
      message: raw || "install Codex Skill",
      icon: "settings",
      host: setupHost?.id ?? "codex"
    };
  }
  if (isMcpOnlySetupText(raw)) {
    return {
      id: "register-mcp-only",
      label: raw || "Register MCP",
      message: raw,
      icon: "settings",
      host: setupHost?.id
    };
  }
  if (isNoMcpSetupText(raw)) {
    return {
      id: "setup-without-mcp",
      label: raw || "Setup without MCP",
      message: raw,
      icon: "settings",
      host: setupHost?.id
    };
  }
  return null;
}

function providerCommandSource(action: Pick<AgentHealthAction, "id" | "command">) {
  if (action.id !== "configure_economy_provider_command" && !action.command) return "";
  const command = action.command ?? "";
  return command.match(/--set-key\s+(providers\.[a-z0-9_-]+\.command)/i)?.[1] ?? command.match(/\b(providers\.[a-z0-9_-]+\.command)\b/i)?.[1] ?? "";
}

function isProviderCommandConfigureAction(action: Pick<AgentHealthAction, "id" | "command">) {
  return action.id === "configure_economy_provider_command" || Boolean(providerCommandSource(action));
}

function isCancelBackgroundAction(action: Pick<AgentHealthAction, "id" | "message">) {
  const text = `${action.id ?? ""} ${action.message ?? ""}`.toLowerCase();
  return text.includes("cancel_background_job") || text.includes("cancel background") || text.includes("stop background");
}

function reasonixCommandMessage(path: string) {
  const trimmed = path.trim();
  if (!trimmed) return "configure reasonix command";
  const quoted = /^[`'"].*[`'"]$/.test(trimmed);
  const value = /\s/.test(trimmed) && !quoted ? `"${trimmed}"` : trimmed;
  return `configure reasonix command to ${value}`;
}

function providerCommandMessage(action: Pick<AgentHealthAction, "command">, path: string) {
  const trimmed = path.trim();
  const source = providerCommandSource({ id: "configure_economy_provider_command", command: action.command });
  if (!trimmed) return source ? `why is ${source} missing` : "show economy profile";
  const quoted = /^[`'"].*[`'"]$/.test(trimmed);
  const value = /\s/.test(trimmed) && !quoted ? `"${trimmed}"` : trimmed;
  return source ? `patchbay config --set-key ${source} --set-value ${value}` : `configure economy provider command to ${value}`;
}

function providerCommandLabel(action: Pick<AgentHealthAction, "command">) {
  const source = providerCommandSource({ id: "configure_economy_provider_command", command: action.command });
  const provider = source.match(/^providers\.([^.]+)\.command$/)?.[1]?.replace(/_/g, " ");
  return provider ? `${provider} command` : "Provider command";
}

function mapStructuredLocalReplyAction(action: AgentHealthAction): LocalReplyAction | null {
  if (action.safe === false) return null;
  if (action.kind === "open_run" || action.id === "open_latest_run") {
    return {
      id: "open-latest-run",
      label: action.label || "打开最近运行",
      message: "open latest run",
      icon: "search",
      runId: action.run_id,
      tab: action.tab,
      reason: action.reason
    };
  }
  if (action.kind === "focus_composer" || action.id === "start_new_task") {
    return { id: "start", label: action.label || "开始任务", message: "start", icon: "play", reason: action.reason };
  }
  if (action.kind === "diagnostic_tab" && action.tab && diagnosticTabs.has(action.tab as TabName)) {
    return {
      id: action.id || `diagnostic-${action.tab}`,
      label: action.label || `Open ${action.tab}`,
      message: "diagnostic_tab",
      icon: "search",
      tab: action.tab,
      reason: action.reason
    };
  }
  if (action.kind === "local_agent" && action.message) {
    const mapped = mapLocalReplyAction(action.message);
    const skipMcp = isNoMcpSetupText(action.message);
    return {
      ...(mapped ?? { id: action.id, label: action.label, message: action.message, icon: "play" as const }),
      label: action.label || mapped?.label || action.message,
      host: action.host ?? mapped?.host,
      reason: action.reason ?? mapped?.reason,
      skipMcp
    };
  }
  return null;
}

function includesAny(text: string, needles: string[]) {
  return needles.some((needle) => text.includes(needle));
}

function requestedTabFromLocalReply(text: string): RunReferenceView["tab"] | null {
  if (/\bdiffs?\b/.test(text) || /\bpatch(?:es)?\b/.test(text) || includesAny(text, ["补丁", "变更", "差异", "改动"])) return "Diff";
  if (includesAny(text, ["events", "trace", "事件", "轨迹", "跟踪", "活动"])) return "Trace";
  if (includesAny(text, ["log", "logs", "日志", "失败", "错误", "报错", "原因", "为什么"])) return "Log";
  if (includesAny(text, ["artifact", "artifacts", "plan", "review", "产物", "计划", "审查", "评审"])) return "Artifacts";
  return null;
}

function requestedTabFromAgentResponse(response?: AgentResponse | null): TabName | null {
  const requestedView = response?.requested_view ?? response?.run_reference?.requested_view;
  const tab = requestedView?.tab;
  if (tab && diagnosticTabs.has(tab as TabName)) return tab as TabName;
  return null;
}

function requestedDisplayTabFromAgentResponse(response?: AgentResponse | null): TabName | null {
  const requestedView = response?.requested_view ?? response?.run_reference?.requested_view;
  if (requestedView?.tab === "Overview") return "Overview";
  return requestedTabFromAgentResponse(response);
}

function isRunStatusPayload(status: AgentResponse["status"], runId: string): status is RunStatus {
  if (!status || status.run_id !== runId) return false;
  return Boolean(status.task || status.gate_state || status.next_commands || status.artifacts || "tests_passed" in status || "review_result" in status);
}

function isLatestRunReadOnlyResponse(response: AgentResponse): response is AgentResponse & { run_id: string } {
  if (!response.run_id) return false;
  if (!new Set(["artifact", "context", "diff", "events", "metrics", "status"]).has(response.action ?? "")) return false;
  if (response.recent_run?.run_id === response.run_id || response.run_reference?.run_id === response.run_id) return true;
  return (response.actions ?? []).some((action) => action.kind === "open_run" && action.run_id === response.run_id && action.safe !== false);
}

function selectsLocalOnlyMode(response?: AgentResponse | null) {
  return response?.action === "local_mode" || response?.local_mode?.skip_mcp === true;
}

function previewArtifactName(status?: RunStatus | null) {
  return status?.artifacts?.find((name) => name.endsWith(".log") || name.endsWith(".md")) ?? null;
}

function hostFromAgentResponse(response?: AgentResponse | null) {
  return response?.setup_host ?? response?.setup?.setup_host ?? response?.setup?.doctor?.host ?? response?.doctor?.host ?? null;
}

function mapLocalReplyAction(raw: string): LocalReplyAction | null {
  const text = raw.toLowerCase();
  const requestedTab = requestedTabFromLocalReply(text);
  if (requestedTab) {
    return { id: "open-latest-run", label: raw || "打开最近运行", message: "open latest run", icon: "search", tab: requestedTab };
  }
  if (includesAny(text, ["open latest", "select latest", "latest run", "recent run", "打开最近", "查看最近运行", "最近运行", "最新运行"])) {
    return { id: "open-latest-run", label: raw || "打开最近运行", message: "open latest run", icon: "search" };
  }
  if (
    text.includes("apply economy profile") ||
    text.includes("config profile apply economy") ||
    text.includes("use economy routing") ||
    text.includes("use economy route") ||
    includesAny(text, ["应用经济路由", "启用经济路由", "经济路由", "便宜模型", "低成本模型"])
  ) {
    return { id: "apply-economy", label: "经济路由", message: "apply economy profile", icon: "play" };
  }
  if (isReasonixConfigureText(raw)) {
    return { id: "configure_reasonix_command", label: "Configure Reasonix", message: "configure reasonix command", icon: "settings" };
  }
  if (includesAny(text, ["readiness", "doctor", "diagnose", "就绪", "诊断", "检查", "检查环境", "环境自检"])) {
    const readinessHost = setupHostFromText(text);
    const skipMcp = isNoMcpSetupText(raw);
    return {
      id: readinessHost ? `readiness-${readinessHost.id}` : "readiness",
      label: readinessHost ? `${readinessHost.label} readiness` : "就绪",
      message: "readiness",
      icon: "shield",
      host: readinessHost?.id,
      skipMcp
    };
  }
  const scopedSetup = mapScopedSetupAction(raw);
  if (scopedSetup) return scopedSetup;
  if (includesAny(text, ["setup", "install", "安装", "初始化", "配置 patchbay", "帮我配置", "帮助我配置"])) {
    const setupHost = setupHostFromText(text);
    if (setupHost) {
      return { id: `setup-${setupHost.id}`, label: setupHost.label, message: setupHost.message, icon: "settings" };
    }
    return { id: "setup", label: "运行 setup", message: "patchbay setup", icon: "settings" };
  }
  if (includesAny(text, ["runs", "status", "运行列表", "运行状态", "查看运行", "最近任务", "任务列表", "状态"])) {
    return { id: "runs", label: "运行列表", message: "status", icon: "search" };
  }
  if (text === "start" || text.includes("start")) {
    return { id: "start", label: "开始任务", message: "start", icon: "play" };
  }
  return null;
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

function backgroundJobTone(job?: BackgroundJob | null) {
  if (!job) return "idle";
  if (job.status === "canceled") return "failed";
  if (job.status === "failed" || (typeof job.exit_code === "number" && job.exit_code !== 0)) return "failed";
  if (job.active || job.status === "running") return "running";
  if (job.status === "finished") return "success";
  return "idle";
}

function isBackgroundJobActive(job?: BackgroundJob | null) {
  return Boolean(job?.active || job?.status === "running");
}

function backgroundJobStatusLabel(job?: BackgroundJob | null) {
  if (job?.status === "canceled") return "后台已取消";
  const tone = backgroundJobTone(job);
  if (tone === "failed") return "后台失败";
  if (tone === "running") return "后台运行中";
  if (tone === "success") return "后台完成";
  return "后台任务";
}

function backgroundJobTitle(job?: BackgroundJob | null) {
  if (!job) return "";
  const phase = phaseLabel(job.phase ?? job.action);
  return `${backgroundJobStatusLabel(job)} · ${phase}`;
}

function backgroundJobDetail(job?: BackgroundJob | null) {
  if (!job) return "";
  const details = [
    job.kind,
    job.pid ? `pid ${job.pid}` : null,
    typeof job.duration_ms === "number" ? compactDuration(job.duration_ms) : null,
    typeof job.exit_code === "number" ? `exit ${job.exit_code}` : null
  ].filter(Boolean);
  return details.join(" · ");
}

function inboxTone(key?: string) {
  if (key === "running") return "running";
  if (key === "needs_approval" || key === "ready_to_apply") return "blocked";
  if (key === "failed") return "failed";
  if (key === "ready_to_continue") return "ready";
  if (key === "applied") return "success";
  return "idle";
}

function inboxLabel(run: RunSummary) {
  const label = run.inbox?.label;
  if (label) return label;
  if (run.background_job?.active) return "Running";
  return statusLabel(run.status);
}

function inboxDetail(run: RunSummary) {
  const action = run.inbox?.next_action;
  const detail = action?.label || run.inbox?.summary || run.next_commands?.[0] || "";
  if (run.inbox?.requires_confirmation) return `${detail} · needs confirmation`;
  return detail;
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

function tierMetricEntries(metrics?: RunMetrics | null) {
  return Object.entries(metrics?.tier_usage ?? {}).filter(([, usage]) =>
    Boolean(usage?.duration_known || usage?.token_usage?.known || usage?.cost?.known)
  );
}

function providerMetricEntries(metrics?: RunMetrics | null) {
  return (metrics?.provider_usage ?? []).filter((item) => Boolean(item.token_usage?.known || item.cost?.known));
}

function tierMetricName(tier: string, usage: TierUsage) {
  if (tier === "economy") return "经济层";
  if (tier === "supervision") return "监督层";
  if (tier === "execution") return "执行层";
  return usage.label || tier;
}

function tierMetricLabel(tier: string, usage: TierUsage) {
  const signals: string[] = [];
  if (usage.token_usage?.known) {
    const percent = usage.token_usage.token_percent;
    signals.push(`${compactNumber(usage.token_usage.total_tokens)} tok${percent !== undefined && percent !== null ? ` / ${percent}%` : ""}`);
  }
  if (usage.cost?.known) {
    const percent = usage.cost.cost_percent;
    signals.push(`${usage.cost.currency ?? "USD"} ${compactNumber(usage.cost.estimated_total ?? 0)}${percent !== undefined && percent !== null ? ` / ${percent}%` : ""}`);
  }
  if (usage.duration_known) {
    const percent = usage.duration_percent;
    signals.push(`${compactDuration(usage.duration_ms)}${percent !== undefined && percent !== null ? ` / ${percent}%` : ""}`);
  }
  return `${tierMetricName(tier, usage)} ${signals.join(" | ")}`;
}

function efficiencyStatusLabel(status?: string) {
  if (status === "verified_economy") return "Verified economy";
  if (status === "missing_usage") return "Usage missing";
  if (status === "pending_evidence") return "Pending evidence";
  if (status === "command_not_ready") return "Command not ready";
  if (status === "drift") return "Routing drift";
  if (status === "not_configured") return "Not configured";
  return status || "Unknown";
}

function efficiencyTone(summary?: EfficiencySummary | null) {
  if (summary?.status === "verified_economy") return "ready";
  if (summary?.status === "command_not_ready" || summary?.status === "drift" || summary?.status === "not_configured") return "blocked";
  return "custom";
}

function percentSuffix(value?: number | null) {
  return value !== undefined && value !== null ? ` / ${value}%` : "";
}

function efficiencyShareSignals(summary?: EfficiencySummary | null) {
  const known = summary?.usage_known ?? {};
  const share = summary?.economy_share ?? {};
  const signals: string[] = [];
  if (known.tokens) {
    signals.push(`economy tokens ${compactNumber(share.total_tokens)}${percentSuffix(share.token_percent)}`);
  }
  if (known.cost) {
    signals.push(`economy cost ${share.currency ?? "USD"} ${compactNumber(share.estimated_cost ?? 0)}${percentSuffix(share.cost_percent)}`);
  }
  if (known.duration) {
    signals.push(`economy time ${compactDuration(share.duration_ms)}${percentSuffix(share.duration_percent)}`);
  }
  return signals;
}

function EfficiencySummaryCard({ summary }: { summary?: EfficiencySummary | null }) {
  if (!summary?.summary) return null;
  const signals = efficiencyShareSignals(summary);
  return (
    <div className={`metric-efficiency ${efficiencyTone(summary)}`} aria-label="Efficiency summary">
      <div className="metric-efficiency-head">
        <span>Cost efficiency</span>
        <strong>{efficiencyStatusLabel(summary.status)}</strong>
      </div>
      <p>{summary.summary}</p>
      {signals.length ? (
        <div className="metric-efficiency-signals">
          {signals.map((signal) => (
            <span key={signal}>{signal}</span>
          ))}
        </div>
      ) : null}
      {summary.recommendation ? <em>{summary.recommendation}</em> : null}
    </div>
  );
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

function traceStatusTone(status?: string, action?: string) {
  const value = `${status ?? ""} ${action ?? ""}`.toUpperCase();
  if (value.includes("ERROR") || value.includes("FAILED") || value.includes("FAIL")) return "failed";
  if (value.includes("PASS") || value.includes("SUCCESS") || value.includes("DONE") || value.includes("COMPLETE")) return "success";
  if (value.includes("RUNNING") || value.includes("START") || value.includes("QUEUED")) return "running";
  return "idle";
}

function traceHeading(entry: TraceEntry) {
  const parts = [entry.phase ? phaseLabel(entry.phase) : "", entry.action ? commandLabel(entry.action) : "", entry.status ? statusLabel(entry.status) : ""].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  return entry.tool || entry.provider || entry.agent || entry.source || "Activity";
}

function traceMeta(entry: TraceEntry) {
  const provider = entry.provider || entry.agent;
  const model = entry.model;
  const meta = [
    entry.timestamp ? timeLabel(entry.timestamp) : "",
    provider && model ? `${provider} / ${model}` : provider || model || "",
    entry.tool || "",
    entry.path || "",
    typeof entry.duration_ms === "number" ? compactDuration(entry.duration_ms) : ""
  ];
  return dedupeStrings(meta);
}

function selectedMessageTraceEntry(message: AgentMessage | null): TraceEntry | null {
  if (!message) return null;
  return {
    source: "selected",
    timestamp: message.timestamp,
    provider: message.provider,
    model: message.model,
    phase: message.phase,
    action: message.kind,
    tool: message.tool,
    status: message.status,
    detail: message.body,
    artifact_paths: message.artifacts
  };
}

function traceEntryKey(entry: TraceEntry, index: number, prefix: string) {
  return `${prefix}-${entry.index ?? entry.seq ?? index}-${entry.timestamp ?? ""}-${entry.phase ?? ""}-${entry.action ?? ""}`;
}

function TraceEntryCard({ entry, index }: { entry: TraceEntry; index: number }) {
  const meta = traceMeta(entry);
  const artifacts = entry.artifact_paths ?? [];
  return (
    <article className={`trace-entry-card tone-${traceStatusTone(entry.status, entry.action)}`} aria-label="Trace event">
      <div className="trace-entry-index">{entry.index ?? entry.seq ?? index + 1}</div>
      <div className="trace-entry-main">
        <div className="trace-entry-head">
          <strong>{traceHeading(entry)}</strong>
          {entry.source ? <span>{entry.source}</span> : null}
        </div>
        {meta.length ? (
          <div className="trace-entry-meta">
            {meta.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        ) : null}
        {entry.detail ? <p>{entry.detail}</p> : null}
        {entry.next_action ? <em>next: {entry.next_action}</em> : null}
        {artifacts.length ? (
          <div className="trace-entry-artifacts">
            {artifacts.map((artifact) => (
              <span key={artifact}>{artifact}</span>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function TraceEntryList({ title, entries, prefix }: { title: string; entries: TraceEntry[]; prefix: string }) {
  if (!entries.length) {
    return (
      <section className="trace-section">
        <div className="trace-section-head">
          <h2>{title}</h2>
          <span>0</span>
        </div>
        <div className="trace-empty">No entries returned.</div>
      </section>
    );
  }
  return (
    <section className="trace-section">
      <div className="trace-section-head">
        <h2>{title}</h2>
        <span>{entries.length}</span>
      </div>
      <div className="trace-entry-list">
        {entries.map((entry, index) => (
          <TraceEntryCard entry={entry} index={index} key={traceEntryKey(entry, index, prefix)} />
        ))}
      </div>
    </section>
  );
}

function TracePanel({ message, trace, rawTrace }: { message: AgentMessage | null; trace: TraceEntry[]; rawTrace: TraceEntry[] }) {
  const selected = selectedMessageTraceEntry(message);
  const selectedEntries = selected ? [selected] : [];
  const providerCount = new Set([...trace, ...rawTrace].map((entry) => entry.provider || entry.agent).filter(Boolean)).size;
  return (
    <div className="diagnostic-body trace-panel">
      <section className="trace-summary" aria-label="Trace timeline">
        <div>
          <h2>活动摘要</h2>
          <p>Run timeline and provider trace are summarized for inspection. Raw JSON remains available below.</p>
        </div>
        <div className="trace-stat-grid">
          <span>{selectedEntries.length} selected</span>
          <span>{trace.length} timeline</span>
          <span>{rawTrace.length} trace</span>
          <span>{providerCount} providers</span>
        </div>
      </section>
      <TraceEntryList title="Selected message" entries={selectedEntries} prefix="selected" />
      <TraceEntryList title="Run timeline" entries={trace} prefix="timeline" />
      <TraceEntryList title="Provider trace" entries={rawTrace} prefix="raw" />
      <details className="trace-raw-json">
        <summary>Raw trace JSON</summary>
        <pre>{JSON.stringify({ selected_message: message ?? {}, timeline: trace, raw_trace: rawTrace }, null, 2)}</pre>
      </details>
    </div>
  );
}

type DiagnosticArtifact = {
  name: string;
  purpose?: string;
  path?: string;
  priority?: boolean;
};
type DiffFileSummary = {
  path: string;
  oldPath?: string;
  additions: number;
  deletions: number;
  hunks: number;
};
type ConfigRecord = Record<string, unknown>;

function diagnosticRecovery(context: HandoffContext | null, status: RunStatus | null) {
  return context?.failure_recovery ?? status?.failure_recovery ?? null;
}

function diagnosticArtifacts(context: HandoffContext | null, status: RunStatus | null, activity: AgentActivity, recovery?: FailureRecovery | null) {
  const byName = new Map<string, DiagnosticArtifact>();
  const priorityNames = new Set(recovery?.artifacts ?? []);
  const add = (artifact: DiagnosticArtifact | string | undefined | null, priority = false) => {
    if (!artifact) return;
    const item = typeof artifact === "string" ? { name: artifact } : artifact;
    if (!item.name) return;
    const current = byName.get(item.name) ?? { name: item.name };
    byName.set(item.name, {
      ...current,
      ...item,
      priority: current.priority || priority || priorityNames.has(item.name)
    });
  };
  recovery?.artifacts?.forEach((artifact) => add(artifact, true));
  context?.artifacts?.forEach((artifact) => add(artifact));
  activity.artifacts?.forEach((artifact) => add(artifact));
  status?.artifacts?.forEach((artifact) => add(artifact));
  return Array.from(byName.values()).sort((left, right) => Number(Boolean(right.priority)) - Number(Boolean(left.priority)));
}

function artifactPreviewLines(text: string) {
  return text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function diagnosticSignalLines(text: string) {
  return artifactPreviewLines(text)
    .filter((line) => /(error|failed|failure|exception|traceback|changes requested|not found|timeout|denied|invalid|无法|失败|错误|异常|超时|未找到|拒绝)/i.test(line))
    .slice(0, 4);
}

function FailureDiagnosticSummary({
  recovery,
  status,
  artifactText
}: {
  recovery?: FailureRecovery | null;
  status?: RunStatus | null;
  artifactText: string;
}) {
  const summary = recovery?.summary || status?.error || "No failure summary reported.";
  const nextAction = recovery?.suggested_next_action || status?.suggested_next_action || "";
  const signals = diagnosticSignalLines([recovery?.error, status?.error, artifactText].filter(Boolean).join("\n"));
  if (!recovery && !status?.error && !status?.suggested_next_action && !signals.length) return null;
  return (
    <section className="diagnostic-summary" aria-label="Failure diagnostic summary">
      <div className="diagnostic-summary-head">
        <AlertTriangle size={15} />
        <strong>失败摘要</strong>
        <span>{phaseLabel(recovery?.stage ?? status?.current_phase)}</span>
      </div>
      <p>{summary}</p>
      {recovery?.error && recovery.error !== summary ? <em>{recovery.error}</em> : null}
      {nextAction ? (
        <div className="diagnostic-next">
          <span>建议下一步</span>
          <strong>{nextAction}</strong>
        </div>
      ) : null}
      {signals.length ? (
        <div className="diagnostic-signal-list" aria-label="Log failure signals">
          {signals.map((line, index) => (
            <code key={`${index}-${line}`}>{line}</code>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function ArtifactInventory({ artifacts }: { artifacts: DiagnosticArtifact[] }) {
  if (!artifacts.length) {
    return <div className="trace-empty">No artifacts reported.</div>;
  }
  return (
    <section className="artifact-inventory" aria-label="Artifact inventory">
      <div className="trace-section-head">
        <h2>产物索引</h2>
        <span>{artifacts.length}</span>
      </div>
      <div className="artifact-list">
        {artifacts.map((artifact) => (
          <div className={`artifact-row ${artifact.priority ? "priority" : ""}`} key={artifact.name}>
            <FileText size={15} />
            <div>
              <strong>{artifact.name}</strong>
              <span>{artifact.purpose || artifact.path || (artifact.priority ? "优先失败产物" : "运行产物")}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function LogPanel({
  artifactText,
  recovery,
  status,
  artifacts
}: {
  artifactText: string;
  recovery?: FailureRecovery | null;
  status: RunStatus | null;
  artifacts: DiagnosticArtifact[];
}) {
  const previewLines = artifactPreviewLines(artifactText);
  const priorityArtifacts = artifacts.filter((artifact) => artifact.priority);
  return (
    <div className="diagnostic-body log-panel">
      <FailureDiagnosticSummary recovery={recovery} status={status} artifactText={artifactText} />
      {priorityArtifacts.length ? (
        <section className="diagnostic-priority-artifacts" aria-label="Priority failure artifacts">
          <div className="trace-section-head">
            <h2>优先检查</h2>
            <span>{priorityArtifacts.length}</span>
          </div>
          <div className="recovery-artifacts">
            {priorityArtifacts.map((artifact) => (
              <span key={artifact.name}>{artifact.name}</span>
            ))}
          </div>
        </section>
      ) : null}
      <section className="artifact-preview-card">
        <div className="trace-section-head">
          <h2>日志预览</h2>
          <span>{previewLines.length}</span>
        </div>
        {artifactText ? <pre>{artifactText}</pre> : <div className="trace-empty">未加载日志产物。</div>}
      </section>
    </div>
  );
}

function ArtifactsPanel({
  artifactText,
  artifacts,
  recovery,
  status
}: {
  artifactText: string;
  artifacts: DiagnosticArtifact[];
  recovery?: FailureRecovery | null;
  status: RunStatus | null;
}) {
  return (
    <div className="diagnostic-body artifacts-panel">
      <FailureDiagnosticSummary recovery={recovery} status={status} artifactText={artifactText} />
      <ArtifactInventory artifacts={artifacts} />
      <section className="artifact-preview-card">
        <div className="trace-section-head">
          <h2>当前预览</h2>
          <span>{artifactPreviewLines(artifactText).length}</span>
        </div>
        {artifactText ? <pre>{artifactText}</pre> : <div className="trace-empty">未加载产物预览。</div>}
      </section>
    </div>
  );
}

function normalizeDiffPath(path: string) {
  return path.replace(/^a\//, "").replace(/^b\//, "");
}

function diffFileSummaries(diff: string): DiffFileSummary[] {
  const files: DiffFileSummary[] = [];
  let current: DiffFileSummary | null = null;
  const ensureCurrent = (path = "working tree") => {
    if (!current) {
      current = { path, additions: 0, deletions: 0, hunks: 0 };
      files.push(current);
    }
    return current;
  };
  for (const line of diff.split(/\r?\n/)) {
    const header = line.match(/^diff --git\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))/);
    if (header) {
      const oldPath = normalizeDiffPath(header[1] || header[2] || "changed file");
      const path = normalizeDiffPath(header[3] || header[4] || oldPath);
      current = { path, oldPath, additions: 0, deletions: 0, hunks: 0 };
      files.push(current);
      continue;
    }
    if (line.startsWith("+++ ")) {
      const nextPath = normalizeDiffPath(line.slice(4).trim().replace(/^"|"$/g, ""));
      if (nextPath && nextPath !== "/dev/null") ensureCurrent(nextPath).path = nextPath;
      continue;
    }
    if (line.startsWith("--- ")) {
      const oldPath = normalizeDiffPath(line.slice(4).trim().replace(/^"|"$/g, ""));
      if (oldPath && oldPath !== "/dev/null") ensureCurrent(oldPath).oldPath = oldPath;
      continue;
    }
    if (line.startsWith("@@")) {
      ensureCurrent().hunks += 1;
      continue;
    }
    if (line.startsWith("+") && !line.startsWith("+++")) {
      ensureCurrent().additions += 1;
      continue;
    }
    if (line.startsWith("-") && !line.startsWith("---")) {
      ensureCurrent().deletions += 1;
    }
  }
  return files;
}

function DiffPanel({ diff }: { diff: string }) {
  const files = diffFileSummaries(diff);
  const additions = files.reduce((total, file) => total + file.additions, 0);
  const deletions = files.reduce((total, file) => total + file.deletions, 0);
  const hunks = files.reduce((total, file) => total + file.hunks, 0);
  const fileLabel = `${files.length} ${files.length === 1 ? "file" : "files"}`;
  return (
    <div className="diagnostic-body diff-panel">
      <section className="diff-summary" aria-label="Diff summary">
        <div>
          <h2>差异摘要</h2>
          <p>{diff ? "Reviewed diff is summarized by file. Raw patch text remains available below." : "当前运行还没有加载 diff。"}</p>
        </div>
        <div className="diff-stat-grid">
          <span>{fileLabel}</span>
          <span>+{additions}</span>
          <span>-{deletions}</span>
          <span>{hunks} hunks</span>
        </div>
      </section>
      <section className="diff-section" aria-label="Changed files">
        <div className="trace-section-head">
          <h2>文件变更</h2>
          <span>{files.length}</span>
        </div>
        {files.length ? (
          <div className="diff-file-list">
            {files.map((file) => (
              <article className="diff-file-card" key={`${file.oldPath ?? file.path}-${file.path}`}>
                <FileText size={15} />
                <div>
                  <strong>{file.path}</strong>
                  {file.oldPath && file.oldPath !== file.path ? <small>{file.oldPath} → {file.path}</small> : null}
                  <div className="diff-file-stats">
                    <span className="added">+{file.additions}</span>
                    <span className="deleted">-{file.deletions}</span>
                    <span>{file.hunks} hunks</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="trace-empty">No diff loaded.</div>
        )}
      </section>
      <details className="diff-raw-text">
        <summary>Raw diff</summary>
        {diff ? <pre>{diff}</pre> : <div className="trace-empty">No raw diff available.</div>}
      </details>
    </div>
  );
}

function asRecord(value: unknown): ConfigRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as ConfigRecord : null;
}

function stringValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "";
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean).join(" ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function configResolved(config: unknown) {
  const root = asRecord(config);
  return asRecord(root?.resolved) ?? root;
}

function configPath(config: unknown) {
  return stringValue(asRecord(config)?.config);
}

const configPhaseOrder = ["plan", "write", "fix", "review", "test", "apply"];

function configPhaseEntries(config: unknown) {
  const resolved = configResolved(config);
  const phaseRecord = asRecord(resolved?.phases);
  if (!phaseRecord) return [];
  return configPhaseOrder
    .map((phase) => {
      const item = asRecord(phaseRecord[phase]);
      if (!item) return null;
      const provider = stringValue(item.provider);
      const model = stringValue(item.model);
      const commandKey = stringValue(item.command_key);
      const timeout = stringValue(item.timeout);
      const phaseCommands = stringList(item.commands);
      const detail = [
        commandKey ? `command ${commandKey}` : "",
        timeout ? `${timeout}s` : "",
        phaseCommands.length ? `${phaseCommands.length} commands` : ""
      ].filter(Boolean).join(" · ");
      return {
        phase,
        route: provider || model || commandKey ? routeSummary({ provider, model, command_key: commandKey }) : "默认",
        detail
      };
    })
    .filter(Boolean) as { phase: string; route: string; detail: string }[];
}

function configCommandEntries(config: unknown) {
  const commands = asRecord(configResolved(config)?.commands);
  return Object.entries(commands ?? {})
    .map(([key, value]) => ({ key, value: stringValue(value) || "未配置" }))
    .filter((entry) => entry.key);
}

function configProviderEntries(config: unknown) {
  const providers = asRecord(configResolved(config)?.providers);
  return Object.entries(providers ?? {})
    .map(([id, raw]) => {
      const item = asRecord(raw);
      if (!item) return null;
      const roles = stringList(item.roles).join("/");
      const command = stringValue(item.command);
      const args = stringList(item.args).join(" ");
      return {
        id,
        detail: [roles, [command, args].filter(Boolean).join(" ")].filter(Boolean).join(" · ") || "自定义 provider"
      };
    })
    .filter(Boolean) as { id: string; detail: string }[];
}

function configTestCommands(config: unknown) {
  const resolved = configResolved(config);
  const testPhase = asRecord(asRecord(resolved?.phases)?.test);
  const allowlist = asRecord(resolved?.commands_allowlist);
  return dedupeStrings([...stringList(testPhase?.commands), ...stringList(allowlist?.test)]);
}

function configWorkflowEntries(config: unknown) {
  const workflow = asRecord(configResolved(config)?.workflow);
  const labels: Record<string, string> = {
    require_plan_approval: "计划批准门禁",
    fail_on_dirty_workspace: "脏工作区保护",
    apply_to_current_workspace_only_after_review_pass: "审查通过后应用",
    allow_apply_without_tests: "允许无测试应用"
  };
  return Object.entries(labels)
    .map(([key, label]) => {
      const value = workflow?.[key];
      if (value === undefined) return null;
      const detail = typeof value === "boolean" ? (value ? "开启" : "关闭") : stringValue(value);
      return { key, label, detail };
    })
    .filter(Boolean) as { key: string; label: string; detail: string }[];
}

function ConfigPanel({ config }: { config: unknown }) {
  const phaseEntries = configPhaseEntries(config);
  const commandEntries = configCommandEntries(config);
  const providerEntries = configProviderEntries(config);
  const testCommands = configTestCommands(config);
  const workflowEntries = configWorkflowEntries(config);
  const path = configPath(config);
  return (
    <div className="diagnostic-body config-view">
      <section className="config-summary" aria-label="Config summary">
        <div>
          <h2>配置摘要</h2>
          {path ? <p>{path}</p> : <p>当前配置来自默认值或本地项目配置。</p>}
        </div>
        <div className="config-stat-grid">
          <span>{phaseEntries.length} phases</span>
          <span>{commandEntries.length} commands</span>
          <span>{providerEntries.length} providers</span>
          <span>{testCommands.length} tests</span>
        </div>
      </section>
      <section className="config-section" aria-label="Configured phase routes">
        <div className="trace-section-head">
          <h2>阶段路由</h2>
          <span>{phaseEntries.length}</span>
        </div>
        <div className="config-row-list">
          {phaseEntries.length ? phaseEntries.map((entry) => (
            <div className="config-row" key={entry.phase}>
              <span>{phaseLabel(entry.phase)}</span>
              <strong>{entry.route}</strong>
              {entry.detail ? <small>{entry.detail}</small> : null}
            </div>
          )) : <div className="trace-empty">未发现阶段配置。</div>}
        </div>
      </section>
      {providerEntries.length ? (
        <section className="config-section" aria-label="Custom providers">
          <div className="trace-section-head">
            <h2>自定义 provider</h2>
            <span>{providerEntries.length}</span>
          </div>
          <div className="config-row-list">
            {providerEntries.map((entry) => (
              <div className="config-row" key={entry.id}>
                <span>{entry.id}</span>
                <strong>{entry.detail}</strong>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <section className="config-section" aria-label="Configured commands">
        <div className="trace-section-head">
          <h2>命令</h2>
          <span>{commandEntries.length}</span>
        </div>
        <div className="config-chip-list">
          {commandEntries.length ? commandEntries.map((entry) => (
            <span className={entry.value === "未配置" ? "blocked" : ""} key={entry.key}>
              {entry.key}: {entry.value}
            </span>
          )) : <div className="trace-empty">未发现命令配置。</div>}
        </div>
      </section>
      <section className="config-section" aria-label="Allowed test commands">
        <div className="trace-section-head">
          <h2>测试 allowlist</h2>
          <span>{testCommands.length}</span>
        </div>
        <div className="config-chip-list">
          {testCommands.length ? testCommands.map((command) => <span key={command}>{command}</span>) : <div className="trace-empty">未配置测试命令。</div>}
        </div>
      </section>
      {workflowEntries.length ? (
        <section className="config-section" aria-label="Workflow safeguards">
          <div className="trace-section-head">
            <h2>安全开关</h2>
            <span>{workflowEntries.length}</span>
          </div>
          <div className="config-row-list">
            {workflowEntries.map((entry) => (
              <div className="config-row compact" key={entry.key}>
                <span>{entry.label}</span>
                <strong>{entry.detail}</strong>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <details className="config-raw-json">
        <summary>Raw config JSON</summary>
        <pre>{JSON.stringify(config, null, 2)}</pre>
      </details>
    </div>
  );
}

async function copyTextToClipboard(text: string) {
  try {
    if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) return false;
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
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

function normalizeMessageText(value?: string | null) {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function localMessageCoveredByActivity(message: LocalMessage, activityMessages: AgentMessage[]) {
  const localBody = normalizeMessageText(message.body);
  if (!localBody) return false;
  return activityMessages.some((activityMessage) => {
    const body = normalizeMessageText(activityMessage.body);
    if (!body) return false;
    return body === localBody || body.includes(localBody) || localBody.includes(body);
  });
}

function localMessageHasDetails(message: LocalMessage) {
  return Boolean(
    message.response?.gate_diagnosis ||
      message.response?.setup ||
      message.response?.routing ||
      message.response?.metrics?.routing_evidence ||
      message.response?.efficiency_summary ||
      message.response?.metrics?.efficiency_summary ||
      message.response?.recovery ||
      (message.response?.actions?.length ?? 0) > 0 ||
      (message.response?.next_actions?.length ?? 0) > 0
  );
}

function visibleLocalMessages(localMessages: LocalMessage[], activityMessages: AgentMessage[]) {
  return localMessages
    .map((message) => {
      if (!localMessageCoveredByActivity(message, activityMessages)) return message;
      return localMessageHasDetails(message) ? { ...message, hideBubble: true } : null;
    })
    .filter(Boolean) as LocalMessage[];
}

function fallbackActivity(context: HandoffContext | null, status: RunStatus | null): AgentActivity {
  const fallbackActions: NextAction[] = (status?.next_commands ?? []).map((name) => {
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
  const failed = currentStatus === "FAILED";
  const recoveryHint = failed ? status?.suggested_next_action || status?.error || "运行遇到错误，请打开诊断查看日志。" : "";
  const suggestions = nextActions.map((action) => ({
    id: action.name,
    label: commandLabel(action.name),
    action: action.name,
    safe: action.safe,
    tool: action.tool,
    requires_human_confirmation: action.requires_human_confirmation,
    reason: action.reason,
    alternative_action: action.alternative_action
  }));
  return {
    headline: nextAction
      ? `Patchbay Agent 已准备好执行：${commandLabel(nextAction.name)}。`
      : failed
        ? `Patchbay Agent 在${phaseLabel(currentPhase)}阶段遇到错误。`
      : busy
        ? `Patchbay Agent 正在执行${phaseLabel(currentPhase)}阶段。`
        : `Patchbay Agent 当前处于${phaseLabel(currentPhase)}阶段。`,
    tone: failed ? "failed" : busy ? "running" : nextAction ? "ready" : "idle",
    background_job: context?.background_job ?? status?.background_job ?? null,
    current_step: {
      phase: currentPhase,
      label: phaseLabel(currentPhase),
      status: currentStatus,
      status_label: statusLabel(currentStatus),
      summary: nextAction?.reason ?? (failed ? recoveryHint : busy ? "后台任务正在运行，状态会自动刷新。" : "暂无可执行动作。")
    },
    next_action: nextAction ? { ...nextAction, label: commandLabel(nextAction.name) } : null,
    conversation_state: {
      task: status?.task,
      status: currentStatus,
      status_label: statusLabel(currentStatus),
      phase: currentPhase,
      phase_label: phaseLabel(currentPhase),
      tone: failed ? "failed" : busy ? "running" : nextAction ? "ready" : "idle",
      next_step: nextAction?.reason ?? (failed ? recoveryHint : busy ? "后台任务正在运行，完成后会出现下一步。" : "当前没有可执行动作。"),
      composer_placeholder: failed
        ? "输入“修复”或打开诊断查看错误"
        : busy
          ? "后台任务运行中，完成后可继续"
          : nextAction
            ? `输入“继续”或点击“${commandLabel(nextAction.name)}”`
            : "输入新任务，或写下本地备注",
      suggestions
    },
    gate_cards: [
      { key: "approval", label: "批准", tone: gateState.approved ? "success" : "idle", detail: gateState.approved ? "计划已批准" : "等待批准" },
      { key: "tests", label: "测试", tone: gateState.tests_passed ? "success" : "idle", detail: gateState.tests_passed ? "测试通过" : "等待测试" },
      { key: "review", label: "审查", tone: gateState.review_result === "PASS" ? "success" : gateState.review_result ? "blocked" : "idle", detail: statusLabel(gateState.review_result) },
      { key: "apply", label: "应用", tone: gateState.ready_to_apply ? "ready" : "blocked", detail: gateState.ready_to_apply ? "可以应用" : "等待门禁" }
    ],
    health_cards: economyHealthCard(status),
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
    id: action.id ?? action.name,
    label: action.label ?? commandLabel(action.name),
    action: action.name,
    safe: action.safe,
    tool: action.tool,
    kind: action.kind,
    message: action.message,
    command: action.command,
    host: action.host,
    run_id: action.run_id,
    tab: action.tab,
    requires_human_confirmation: action.requires_human_confirmation,
    reason: action.reason,
    alternative_action: action.alternative_action
  }));
}

function suggestionGroupsFor(suggestions: SuggestedAction[], groups: ActionGroup[] | undefined) {
  if (!suggestions.length) return [];
  if (!groups?.length) return [{ id: "suggested", label: "建议动作", reason: undefined, suggestions }];
  const byKey = new Map<string, SuggestedAction>();
  for (const suggestion of suggestions) {
    for (const key of suggestionActionKeys(suggestion)) {
      byKey.set(key, suggestion);
    }
  }
  const used = new Set<string>();
  const result: { id: string; label: string; reason?: string; suggestions: SuggestedAction[] }[] = [];
  for (const group of groups) {
    const grouped = (group.action_ids ?? []).map((id) => byKey.get(id)).filter(Boolean) as SuggestedAction[];
    const unique = grouped.filter((suggestion) => {
      const key = suggestionActionKey(suggestion);
      if (used.has(key)) return false;
      used.add(key);
      return true;
    });
    if (unique.length) {
      result.push({ id: group.id, label: localReplyActionGroupLabel(group), reason: group.reason, suggestions: unique });
    }
  }
  const remaining = suggestions.filter((suggestion) => !used.has(suggestionActionKey(suggestion)));
  if (remaining.length) result.push({ id: "suggested", label: "建议动作", suggestions: remaining });
  return result;
}

function suggestionActionKeys(suggestion: SuggestedAction) {
  return dedupeStrings([suggestion.id, suggestion.action, suggestion.message, suggestion.label]);
}

function suggestionActionKey(suggestion: SuggestedAction) {
  return suggestionActionKeys(suggestion)[0] ?? suggestion.label;
}

function actionFromSuggestion(suggestion: SuggestedAction | AgentAction): SuggestedAction {
  const action = "action" in suggestion ? suggestion.action : suggestion.name;
  const result: SuggestedAction = {
    id: "id" in suggestion && suggestion.id ? suggestion.id : action,
    label: suggestion.label ?? commandLabel(action),
    action,
    safe: suggestion.safe,
    tool: suggestion.tool,
    requires_human_confirmation: suggestion.requires_human_confirmation,
    reason: suggestion.reason,
    alternative_action: suggestion.alternative_action
  };
  if ("kind" in suggestion) result.kind = suggestion.kind;
  if ("message" in suggestion) result.message = suggestion.message;
  if ("command" in suggestion) result.command = suggestion.command;
  if ("host" in suggestion) result.host = suggestion.host;
  if ("run_id" in suggestion) result.run_id = suggestion.run_id;
  if ("tab" in suggestion) result.tab = suggestion.tab;
  return result;
}

function healthActionFromSuggestion(suggestion: SuggestedAction): AgentHealthAction | null {
  const pollMessages: Record<string, string> = {
    poll_context: "context",
    poll_status: "status",
    poll_events: "events"
  };
  const message = suggestion.message ?? pollMessages[suggestion.action] ?? pollMessages[suggestion.id];
  const kind = suggestion.kind ?? (message ? "local_agent" : suggestion.tab ? "diagnostic_tab" : undefined);
  if (!kind && !message && !suggestion.tab && !suggestion.run_id) return null;
  return {
    id: suggestion.id || suggestion.action,
    label: suggestion.label || commandLabel(suggestion.action),
    kind,
    message,
    command: suggestion.command,
    host: suggestion.host,
    run_id: suggestion.run_id,
    tab: suggestion.tab,
    safe: suggestion.safe,
    reason: suggestion.reason
  };
}

function canRunSuggestionWhileBusy(suggestion: SuggestedAction) {
  if (suggestion.safe === false) return false;
  const message = suggestion.message ?? (suggestion.action === "poll_context" ? "context" : suggestion.action === "poll_status" ? "status" : suggestion.action === "poll_events" ? "events" : "");
  if (isCancelBackgroundAction({ id: suggestion.id || suggestion.action, message })) return true;
  if (suggestion.kind === "diagnostic_tab" || suggestion.kind === "open_run") return true;
  if (suggestion.kind === "local_agent" && ["context", "status", "events"].includes(message)) return true;
  return ["poll_context", "poll_status", "poll_events"].includes(suggestion.action);
}

function doctorProfileStatus(report?: DoctorReport | null): DoctorProfileStatus | null {
  const profile = report?.checks?.config?.profile;
  return profile && typeof profile === "object" ? (profile as DoctorProfileStatus) : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}

function doctorCheckIsReady(check: DoctorCheck): boolean {
  if (check.skipped) return true;
  if (typeof check.ready === "boolean") return check.ready;
  return Boolean(check.ok);
}

function doctorCheckTone(check: DoctorCheck) {
  if (check.skipped) return "idle";
  return doctorCheckIsReady(check) ? "ready" : "blocked";
}

function doctorCheckStatusLabel(check: DoctorCheck) {
  if (check.skipped) return "跳过";
  if (typeof check.status === "string") {
    if (check.status === "installed") return "通过";
    if (check.status === "outdated") return "需更新";
    if (check.status === "not_installed") return "未安装";
    if (check.status === "missing_source") return "源缺失";
  }
  return doctorCheckIsReady(check) ? "通过" : "需处理";
}

function doctorCheckDetails(check: DoctorCheck): string[] {
  const details: string[] = [];
  const primary = check.error ?? check.note;
  const contract = check.contract && typeof check.contract === "object" ? check.contract as { kind?: unknown; entrypoint?: unknown } : null;
  if (primary) details.push(String(primary));
  if (typeof check.status === "string" && check.status !== "installed") {
    details.push(`status: ${check.status}`);
  }
  if (contract?.kind) details.push(`contract: ${String(contract.kind)}`);
  if (contract?.entrypoint) details.push(`entrypoint: ${String(contract.entrypoint)}`);
  const missing = stringList(check.missing_installed_files);
  if (missing.length) details.push(`missing installed files: ${missing.join(", ")}`);
  const changed = stringList(check.changed_installed_files);
  if (changed.length) details.push(`changed installed files: ${changed.join(", ")}`);
  const extra = stringList(check.extra_installed_files);
  if (extra.length) details.push(`extra installed files: ${extra.join(", ")}`);
  if (check.installed && check.installed_matches_source === false && !missing.length && !changed.length && !extra.length) {
    details.push("installed Skill differs from bundled source");
  }
  return details;
}

function routeSummary(route?: PhaseProvider) {
  if (!route) return "未配置";
  if (route.label) return route.label;
  const provider = route.provider || "-";
  const model = route.model || route.command_key || "默认";
  return `${provider} / ${model}`;
}

function healthStatusLabel(status?: string) {
  if (status === "healthy") return "健康";
  if (status === "pending_evidence") return "待观测";
  if (status === "drift") return "漂移";
  if (status === "not_configured") return "未配置";
  if (status === "command_not_ready") return "命令未就绪";
  return status || "未知";
}

function strategyTierLabel(tier?: string) {
  if (tier === "economy") return "经济";
  if (tier === "supervision") return "监督";
  if (tier === "custom") return "自定义";
  return tier || "自定义";
}

function strategyReason(phase: string) {
  if (phase === "write") return "大量实现工作交给低成本 writer。";
  if (phase === "fix") return "迭代修复工作交给低成本 writer。";
  if (phase === "review") return "应用前由独立强模型审查。";
  return "计划拆解和约束判断使用强模型。";
}

function strategyFromRouting(routing?: RoutingEvidence | null, providers?: Record<string, PhaseProvider>): Record<string, PhaseStrategy> {
  const strategy: Record<string, PhaseStrategy> = {};
  for (const phase of strategyPhases) {
    const isWriterPhase = phase === "write" || phase === "fix";
    const configured = isWriterPhase ? routing?.phases?.[phase]?.configured : undefined;
    const economyRoute = isWriterPhase ? Boolean(routing?.phases?.[phase]?.configured_economy) : false;
    const tier = isWriterPhase ? (economyRoute ? "economy" : "custom") : "supervision";
    strategy[phase] = {
      ...(providers?.[phase] ?? configured ?? {}),
      tier,
      reason: economyRoute || !isWriterPhase ? strategyReason(phase) : "Write/fix is not on the configured economy route.",
      economy_route: economyRoute
    };
  }
  return strategy;
}

function phaseStrategyEntries(strategy?: Record<string, PhaseStrategy> | null, routing?: RoutingEvidence | null, providers?: Record<string, PhaseProvider>) {
  if (!strategy && !routing && !Object.keys(providers ?? {}).length) return [];
  const source = strategy ?? routing?.phase_strategy ?? strategyFromRouting(routing, providers);
  return strategyPhases
    .map((phase) => [phase, source[phase]] as const)
    .filter(([, item]) => Boolean(item && (item.provider || item.model || item.command_key || item.tier || item.error)));
}

function routeEvidenceLabel(phase: string, routing?: RoutingEvidence | null) {
  const item = routing?.phases?.[phase];
  if (!item) return "";
  if (item.command_status?.required && item.command_status.ready === false) {
    if (item.command_status.status === "missing_config") return "命令未配置";
    if (item.command_status.status === "not_found") return "命令未找到";
    return "命令未就绪";
  }
  if (item.observed_economy) return "已观测";
  if (item.configured_economy) return "待观测";
  if (item.observed?.length) return "观测到自定义";
  return "未观测";
}

function routingCoverageLabel(routing?: RoutingEvidence | null) {
  const coverage = routing?.coverage;
  if (!coverage) return "";
  const required = coverage.required_total ?? 2;
  const observed = coverage.observed_economy_total ?? routing?.observed_economy_phases?.length ?? 0;
  const percent = coverage.observed_economy_percent;
  if (typeof percent === "number") return `${percent}% · ${observed}/${required}`;
  return coverage.label || `${observed}/${required}`;
}

function economyHealthLabel(routing?: RoutingEvidence | null) {
  const health = routing?.economy_health;
  if (!health?.status) return "";
  if (health.status === "drift") return `${healthStatusLabel(health.status)} · ${(health.drift_phases ?? []).join("/") || "write/fix"}`;
  if (health.status === "not_configured") return `${healthStatusLabel(health.status)} · ${(health.missing_config_phases ?? []).join("/") || "write/fix"}`;
  if (health.status === "command_not_ready") return `${healthStatusLabel(health.status)} · ${(health.command_not_ready_phases ?? routing?.command_not_ready_phases ?? []).join("/") || "write/fix"}`;
  return healthStatusLabel(health.status);
}

function healthActionFromNext(nextAction?: string, target?: PhaseProvider): AgentHealthAction | null {
  const targetLabel = target ? routeSummary(target) : "Reasonix/DeepSeek";
  if (nextAction === "configure_reasonix_command") {
    return {
      id: "configure_reasonix_command",
      label: "Configure Reasonix",
      kind: "local_agent",
      message: "configure reasonix command",
      command: "patchbay config --set-key commands.reasonix --set-value reasonix",
      safe: true,
      reason: `Set the default Reasonix executable so the ${targetLabel} write/fix economy route can actually run.`
    };
  }
  if (nextAction === "apply_economy_profile") {
    return {
      id: "apply_economy_profile",
      label: "Apply economy profile",
      kind: "local_agent",
      message: "apply economy profile",
      safe: true,
      reason: `Routes write/fix to the ${targetLabel} economy profile.`
    };
  }
  if (nextAction === "inspect_routing_events") {
    return {
      id: "inspect_routing_events",
      label: "Inspect routing events",
      kind: "diagnostic_tab",
      tab: "Trace",
      safe: true,
      reason: "Open provider events to inspect write/fix routing drift."
    };
  }
  if (nextAction === "wait_for_routing_evidence") {
    return {
      id: "wait_for_routing_evidence",
      label: "Watch provider events",
      kind: "diagnostic_tab",
      tab: "Trace",
      safe: true,
      reason: "Open events while write/fix provider evidence arrives."
    };
  }
  if (nextAction === "inspect_economy_provider_command") {
    return {
      id: "inspect_economy_provider_command",
      label: "Inspect provider command",
      kind: "local_agent",
      message: "readiness",
      safe: true,
      reason: `Inspect the configured command for the ${targetLabel} economy provider.`
    };
  }
  return null;
}

function preferredSafeRoutingAction(actions?: AgentHealthAction[] | null, status?: string) {
  const safeActions = (actions ?? []).filter((action) => action.safe !== false);
  if (!safeActions.length) return null;
  if (status === "command_not_ready") {
    const commandAction =
      safeActions.find((action) => action.id === "configure_economy_provider_command") ??
      safeActions.find((action) => action.kind === "command" && Boolean(action.command));
    if (commandAction) return commandAction;
  }
  return safeActions[0];
}

function profileStatusToRouting(result: ConfigProfileStatus): RoutingEvidence {
  const status = result.status ?? result;
  const economy = status.economy ?? {};
  const write = economy.write ?? {};
  const fix = economy.fix ?? {};
  const target = economy.target ?? { provider: "reasonix_cli", model: "deepseek-v4-pro" };
  const configuredEconomy = Boolean(economy.matches);
  const commandStatus = economy.command_status ?? {};
  const matchesTarget = (route: PhaseProvider) =>
    route.provider === target.provider &&
    (!target.model || route.model === target.model) &&
    (!target.command_key || route.command_key === target.command_key);
  return {
    profile: status.profile ?? result.profile ?? (configuredEconomy ? "economy" : "custom"),
    target,
    workload_policy: result.workload_policy ?? status.workload_policy,
    economy_configured: configuredEconomy,
    economy_command_ready: typeof economy.command_ready === "boolean" ? economy.command_ready : null,
    phase_strategy: status.phase_strategy ?? result.phase_strategy,
    phases: {
      write: {
        configured: write,
        configured_economy: matchesTarget(write),
        command_status: commandStatus.write
      },
      fix: {
        configured: fix,
        configured_economy: matchesTarget(fix),
        command_status: commandStatus.fix
      }
    },
    summary: configuredEconomy
      ? `Economy routing profile is active: write ${routeSummary(write)}, fix ${routeSummary(fix)}.`
      : `Economy routing profile is not active: write ${routeSummary(write)}, fix ${routeSummary(fix)}.`,
    recommendation: status.recommendation ?? result.recommendation
  };
}

function economyHealthCard(status: RunStatus | null) {
  const routing = status?.run_metrics?.routing_evidence ?? status?.routing_evidence;
  const health = routing?.economy_health;
  if (!health?.status) return [];
  return [
    {
      key: "economy_route",
      label: "Economy route",
      status: health.status,
      tone: (health.severity === "warning" ? "blocked" : health.severity === "ok" ? "success" : "ready") as AgentHealthCard["tone"],
      detail: health.summary ?? routing?.summary ?? "",
      recommendation: health.recommendation,
      next_action: health.next_action,
      action:
        preferredSafeRoutingAction(routing?.actions, health.status) ??
        healthActionFromNext(health.next_action, health.target ?? routing?.target),
      coverage_percent: routing?.coverage?.observed_economy_percent ?? null
    }
  ];
}

function confirmCopy(action: SuggestedAction, readyToApply: boolean): ConfirmState {
  if (action.action === "approve") {
    return {
      action: action.action,
      title: "确认批准计划",
      body: "批准后，Patchbay Agent 才会进入实现阶段。",
      safe: true,
      confirmLabel: "批准"
    };
  }
  if (action.action === "apply" && action.safe) {
    return {
      action: action.action,
      title: readyToApply ? "确认应用补丁" : "暂不能应用",
      body: readyToApply ? "将已审查通过的 FINAL.diff 应用到当前工作区。" : "应用必须等待测试通过且审查为 PASS。",
      safe: readyToApply,
      confirmLabel: readyToApply ? "应用" : "知道了"
    };
  }
  if (action.action === "continue" && action.requires_human_confirmation) {
    return {
      action: action.action,
      title: "确认继续运行",
      body: action.reason || "Patchbay Agent 会在后台推进下一阶段。",
      safe: true,
      confirmLabel: "继续"
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
  if (!action.safe) {
    return {
      action: action.action,
      title: "暂不能执行",
      body: action.reason || `当前状态不允许执行“${action.label}”。`,
      safe: false,
      confirmLabel: "知道了"
    };
  }
  return null;
}

function resolveComposerIntent(text: string, suggestions: SuggestedAction[], primaryAction: AgentAction | null | undefined) {
  const value = text.trim().toLowerCase();
  if (!value || value.length > 24) return null;
  const normalized = value.replace(/[?？!！.。]/g, "").trim();
  const questionTerms = ["why", "what", "how", "blocked", "blocking", "blocker", "gate", "status", "原因", "为什么", "哪个", "哪些", "门禁", "阻塞", "状态"];
  if (value.includes("?") || value.includes("？") || questionTerms.some((term) => value.includes(term))) return null;
  const localAgentTerms = ["economy", "profile", "routing", "reasonix", "deepseek", "经济路由", "便宜模型", "低成本"];
  if (localAgentTerms.some((term) => value.includes(term))) return null;
  const findAction = (name: string) => suggestions.find((item) => item.action === name);
  const continueWords = ["继续", "下一步", "确认", "go", "continue", "next"];
  if (continueWords.some((word) => normalized === word)) {
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

function canonicalPhaseAction(action?: string) {
  const value = action?.trim();
  if (!value) return "";
  if (value === "approve_and_run") return "approve";
  return value;
}

function isPhaseAction(action?: string) {
  return ["approve", "apply", "cleanup", "continue", "write", "test", "review", "fix"].includes(canonicalPhaseAction(action));
}

function shouldAutopilot(action: string) {
  return ["continue", "write", "test", "review", "fix"].includes(action);
}

function inboxFocusRunId(runs: RunSummary[], inbox?: RunsInbox | null) {
  const focusRunId = inbox?.focus_run_id ?? inbox?.focus?.run_id ?? "";
  if (focusRunId && runs.some((run) => run.run_id === focusRunId)) return focusRunId;
  return runs[0]?.run_id ?? "";
}

function readyToApplyRun(run: RunSummary) {
  return Boolean(run.gate_state?.ready_to_apply || run.inbox?.key === "ready_to_apply");
}

function inboxSuggestedAction(run: RunSummary): SuggestedAction | null {
  const action = run.inbox?.next_action;
  if (!action) return null;
  const phaseAction = canonicalPhaseAction(action.message || action.id);
  if (!isPhaseAction(phaseAction)) return null;
  const readyToApply = readyToApplyRun(run);
  const requiresConfirmation = Boolean(action.requires_confirmation) || action.safe === false;
  return {
    id: action.id || phaseAction,
    label: action.label || commandLabel(phaseAction),
    action: phaseAction,
    safe: phaseAction === "apply" ? readyToApply : true,
    requires_human_confirmation: requiresConfirmation,
    reason: action.reason,
    run_id: run.run_id
  };
}

export function Workbench({ client = defaultClient, pollIntervalMs = 4000 }: { client?: PatchbayClient; pollIntervalMs?: number }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runsInbox, setRunsInbox] = useState<RunsInbox | null>(null);
  const [selectedRun, setSelectedRun] = useState("");
  const [newTaskMode, setNewTaskMode] = useState(false);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [context, setContext] = useState<HandoffContext | null>(null);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [rawTrace, setRawTrace] = useState<TraceEntry[]>([]);
  const [selectedMessage, setSelectedMessage] = useState<AgentMessage | null>(null);
  const eventCursor = useRef(0);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const [diff, setDiff] = useState("");
  const [artifactText, setArtifactText] = useState("");
  const [config, setConfig] = useState<unknown>(null);
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [activeTab, setActiveTab] = useState<TabName>("Overview");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [inboxFilter, setInboxFilter] = useState("");
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const [error, setError] = useState("");
  const [composer, setComposer] = useState("");
  const [readinessHost, setReadinessHost] = useState<SetupHostOption>(setupHostOptions[0]);
  const [submitting, setSubmitting] = useState(false);
  const [actionInFlight, setActionInFlight] = useState(false);
  const [setupInFlight, setSetupInFlight] = useState(false);
  const [profileInFlight, setProfileInFlight] = useState(false);
  const [localMessages, setLocalMessages] = useState<Record<string, LocalMessage[]>>({});
  const [newTaskReply, setNewTaskReply] = useState<AgentResponse | null>(null);
  const [localOnlyMode, setLocalOnlyMode] = useState(false);
  const refreshSeq = useRef(0);

  const patchRunSummary = (runId: string, patch: Partial<RunSummary>) => {
    setRuns((current) => current.map((run) => (run.run_id === runId ? { ...run, ...patch } : run)));
  };

  const loadRuns = async (preferredRunId?: string, options: { autoSelect?: boolean } = {}) => {
    const result = await client.listRuns();
    const nextRuns = result?.runs ?? [];
    const nextInbox = result?.inbox ?? null;
    setRuns(nextRuns);
    setRunsInbox(nextInbox);
    if (preferredRunId) {
      setSelectedRun(preferredRunId);
      return nextRuns;
    }
    if (options.autoSelect !== false && !selectedRun && !newTaskMode) {
      const nextSelected = inboxFocusRunId(nextRuns, nextInbox);
      if (nextSelected) setSelectedRun(nextSelected);
    }
    return nextRuns;
  };

  useEffect(() => {
    void loadRuns().catch((err) => setError(String(err)));
    void client.getDoctor({ include_mcp: false, host: setupHostOptions[0].id }).then(setDoctor).catch((err) => setError(String(err)));
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
    let backgroundWasActive = false;
    setTrace([]);
    setRawTrace([]);
    setSelectedMessage(null);
    eventCursor.current = 0;
    const runRefreshSeq = ++refreshSeq.current;

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
      backgroundWasActive = isBackgroundJobActive(nextContext.background_job ?? nextContext.agent_activity?.background_job ?? nextStatus.background_job);
      setStatus(nextStatus);
      setContext(nextContext);
      setRawTrace(nextTrace.trace ?? nextTrace.events ?? []);
      appendTimelineEntries(nextContext.timeline ?? [], nextContext.cursors?.event, 0, true);
      setSelectedMessage(nextContext.agent_activity?.messages?.[0] ?? null);
      setDiff(nextDiff.text ?? nextDiff.diff ?? "");
      setConfig(nextConfig);
      const firstArtifact = previewArtifactName(nextStatus);
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
      if (cancelled || refreshSeq.current !== runRefreshSeq || !nextContext) return;
      const nextBackgroundJob = nextContext.background_job ?? nextContext.agent_activity?.background_job;
      const backgroundActive = isBackgroundJobActive(nextBackgroundJob);
      setContext((current) => mergeContext(current, nextContext));
      setStatus((current) =>
        current
          ? {
              ...current,
              status: nextContext.status ?? current.status,
              current_phase: nextContext.current_phase ?? current.current_phase,
              gate_state: nextContext.gate_state ?? current.gate_state,
              background_job: nextContext.background_job ?? nextContext.agent_activity?.background_job ?? current.background_job
            }
          : current
      );
      patchRunSummary(selectedRun, {
        status: nextContext.status,
        task: nextContext.agent_activity?.conversation_state?.task,
        background_job: nextBackgroundJob
      });
      appendTimelineEntries(nextContext.timeline ?? [], nextContext.cursors?.event, since);
      if (backgroundActive || backgroundWasActive) {
        const [latestStatus] = await Promise.all([client.getStatus(selectedRun), loadRuns(selectedRun, { autoSelect: false })]);
        if (cancelled || refreshSeq.current !== runRefreshSeq) return;
        const latestBackgroundJob = latestStatus.background_job ?? nextBackgroundJob;
        backgroundWasActive = isBackgroundJobActive(latestBackgroundJob);
        setStatus(latestStatus);
        patchRunSummary(selectedRun, {
          status: latestStatus.status,
          task: latestStatus.task,
          background_job: latestBackgroundJob
        });
      }
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
      const matchesInbox = !inboxFilter || run.inbox?.key === inboxFilter;
      const text = `${run.run_id} ${run.task ?? ""}`.toLowerCase();
      return matchesStatus && matchesInbox && (!needle || text.includes(needle));
    });
  }, [runs, search, statusFilter, inboxFilter]);

  useEffect(() => {
    if (newTaskMode) return;
    if (!visibleRuns.length) {
      if (selectedRun) setSelectedRun("");
      return;
    }
    if (!visibleRuns.some((run) => run.run_id === selectedRun)) {
      setSelectedRun(inboxFocusRunId(visibleRuns, runsInbox));
    }
  }, [visibleRuns, selectedRun, newTaskMode, runsInbox]);

  const selectedSummary = useMemo(() => runs.find((run) => run.run_id === selectedRun), [runs, selectedRun]);
  const activeContext = context?.run_id === selectedRun ? context : null;
  const activeStatus = status?.run_id === selectedRun ? status : null;
  const activity = activeContext?.agent_activity ?? fallbackActivity(activeContext, activeStatus);
  const backgroundJob = activeContext?.background_job ?? activity.background_job ?? activeStatus?.background_job ?? selectedSummary?.background_job ?? null;
  const conversationState = activity.conversation_state;
  const gateState = activeContext?.gate_state ?? activeStatus?.gate_state ?? {};
  const loadedStatus = activeContext?.status ?? activeStatus?.status;
  const currentStatus = activeContext?.status ?? activeStatus?.status ?? selectedSummary?.status;
  const currentPhase = activeContext?.current_phase ?? activeStatus?.current_phase ?? "";
  const runBusy = isBusyStatus(currentStatus) || Boolean(backgroundJob?.active);
  const interactionBusy = submitting || actionInFlight || runBusy;
  const readyToApply = Boolean(gateState.ready_to_apply && (activeContext?.status ?? activeStatus?.status) === "REVIEWED_PASS");
  const messages = dedupeMessages(activity.messages ?? []);
  const primaryAction = activity.next_action;
  const suggestions = suggestionsFor(activity, activeContext);
  const suggestionGroups = useMemo(() => suggestionGroupsFor(suggestions, activeContext?.action_groups), [suggestions, activeContext?.action_groups]);
  const failureGuidance =
    loadedStatus === "FAILED"
      ? conversationState?.next_step ?? activity.current_step?.summary ?? "运行遇到错误，请查看诊断日志。"
      : "";
  const failureRecovery = loadedStatus === "FAILED" ? activeContext?.failure_recovery ?? activeStatus?.failure_recovery ?? undefined : undefined;
  const selectedTask = conversationState?.task ?? activeStatus?.task ?? selectedSummary?.task ?? "";
  const runKey = selectedRun || "__new__";
  const localRunMessages = visibleLocalMessages(localMessages[runKey] ?? [], messages);
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
    const requestedTab = requestedDisplayTabFromAgentResponse(agentResponse);
    const nextStatus = isRunStatusPayload(agentResponse?.status, runId) ? agentResponse.status : await client.getStatus(runId);
    setStatus(nextStatus);
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
    const firstArtifact = previewArtifactName(nextStatus);
    if (firstArtifact) {
      const artifact = await client.getArtifact(runId, firstArtifact, { tail: 80 });
      setArtifactText(artifact.text);
    } else {
      setArtifactText("");
    }
    patchRunSummary(runId, {
      status: agentResponse?.context?.status ?? nextStatus.status,
      task: agentResponse?.context?.agent_activity?.conversation_state?.task ?? nextStatus.task,
      background_job: agentResponse?.context?.background_job ?? agentResponse?.context?.agent_activity?.background_job ?? nextStatus.background_job
    });
    if (requestedTab) {
      setDiagnosticsOpen(true);
      setActiveTab(requestedTab);
    }
  };

  const runAction = async (action: string, targetRun = selectedRun) => {
    if (!targetRun || interactionBusy) return;
    setError("");
    setActionInFlight(true);
    try {
      if (shouldAutopilot(action)) {
        const response = await client.agentMessage("continue", {
          runId: targetRun,
          include: { diff: true, review: true },
          background: true
        });
        await refreshRun(targetRun, response);
        return;
      }
      await client.runAction(targetRun, action);
      await refreshRun(targetRun);
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
    const targetRun = action.run_id || selectedRun;
    const targetSummary = targetRun ? runs.find((run) => run.run_id === targetRun) : undefined;
    const targetReadyToApply = targetSummary ? readyToApplyRun(targetSummary) : readyToApply;
    const phaseAction = isPhaseAction(action.action);
    if (targetRun && targetRun !== selectedRun) {
      setNewTaskMode(false);
      setSelectedRun(targetRun);
    }
    if (!phaseAction) {
      const healthAction = healthActionFromSuggestion(action);
      if (healthAction) {
        void runHealthAction(healthAction);
        return;
      }
    }
    if (action.action === "apply" && !targetReadyToApply) action.safe = false;
    const confirmation = confirmCopy(action, targetReadyToApply);
    if (confirmation) {
      setConfirm({ ...confirmation, runId: targetRun });
      return;
    }
    if (!action.safe) {
      const blocked = confirmCopy(action, targetReadyToApply);
      if (blocked) setConfirm({ ...blocked, runId: targetRun });
      return;
    }
    void runAction(action.action, targetRun);
  };

  const confirmAction = async () => {
    if (!confirm || actionInFlight) return;
    if (!confirm.safe) {
      setConfirm(null);
      return;
    }
    const targetRun = confirm.runId || selectedRun;
    if (!targetRun) return;
    setError("");
    const action = confirm.action;
    setConfirm(null);
    const confirmation = confirmationForAction(action);
    setActionInFlight(true);
    try {
      if (confirmation) {
        const response = await client.agentMessage(action, {
          runId: targetRun,
          confirmation,
          include: { diff: action === "apply", review: action === "apply" },
          background: action !== "apply"
        });
        await refreshRun(targetRun, response);
      } else if (action === "cleanup") {
        await client.cleanup(targetRun);
        await refreshRun(targetRun);
      } else if (shouldAutopilot(action)) {
        const response = await client.agentMessage("continue", {
          runId: targetRun,
          include: { diff: true, review: true },
          background: true
        });
        await refreshRun(targetRun, response);
      } else {
        await client.runAction(targetRun, action);
        await refreshRun(targetRun);
      }
    } finally {
      setActionInFlight(false);
    }
  };

  const appendLocalMessage = (body: string, targetRunKey = runKey) => {
    const timestamp = new Date().toISOString();
    setLocalMessages((current) => ({
      ...current,
      [targetRunKey]: [...(current[targetRunKey] ?? []), { id: `local-${Date.now()}`, body, timestamp }]
    }));
  };

  const appendLocalAgentReply = (response: AgentResponse, targetRunKey = runKey) => {
    const body = response.reply || response.action || "Patchbay Agent returned a local response.";
    const timestamp = new Date().toISOString();
    setLocalMessages((current) => ({
      ...current,
      [targetRunKey]: [
        ...(current[targetRunKey] ?? []),
        { id: `local-agent-${Date.now()}`, role: "assistant", body, timestamp, response }
      ]
    }));
  };

  const runSetupAction = async (host: SetupHostOption = readinessHost, message = host.message) => {
    if (setupInFlight) return;
    const skipMcp = isNoMcpSetupText(message);
    if (skipMcp) setLocalOnlyMode(true);
    setError("");
    setReadinessHost(host);
    setSetupInFlight(true);
    try {
      const response = await client.agentMessage(message);
      const responseHost = setupHostById(hostFromAgentResponse(response) ?? host.id);
      const setupDoctor = response.setup?.doctor ?? response.doctor;
      setReadinessHost(responseHost);
      if (selectedRun) appendLocalAgentReply(response);
      else setNewTaskReply(response);
      if (setupDoctor) {
        setDoctor(setupDoctor);
      } else {
        setDoctor(await client.getDoctor({ include_mcp: false, host: responseHost.id, ...(skipMcp ? { skip_mcp: true } : {}) }));
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
      const profile = await client.applyConfigProfile("economy");
      const routing = profileStatusToRouting(profile);
      const response: AgentResponse = {
        run_id: null,
        action: "profile_apply",
        ok: true,
        reply: "Economy routing profile applied.",
        profile,
        routing,
        next_actions: profile.next_actions ?? ["readiness", "start"],
        actions: profile.actions ?? [],
        action_groups: profile.action_groups ?? []
      };
      if (selectedRun) appendLocalAgentReply(response);
      else setNewTaskReply(response);
      const [nextDoctor, nextConfig] = await Promise.all([client.getDoctor({ include_mcp: false, host: readinessHost.id }), client.getConfig()]);
      setDoctor(nextDoctor);
      setConfig(nextConfig);
      if (selectedRun) await refreshRun(selectedRun);
      else await loadRuns(undefined, { autoSelect: false });
    } catch (err) {
      setError(String(err));
    } finally {
      setProfileInFlight(false);
    }
  };

  const configureReasonixCommandAction = async (message = "configure reasonix command") => {
    if (profileInFlight) return;
    setError("");
    setProfileInFlight(true);
    try {
      const response = await client.agentMessage(message);
      if (selectedRun) appendLocalAgentReply(response);
      else setNewTaskReply(response);
      const [nextDoctor, nextConfig] = await Promise.all([client.getDoctor({ include_mcp: false, host: readinessHost.id }), client.getConfig()]);
      setDoctor(nextDoctor);
      setConfig(nextConfig);
      if (selectedRun) await refreshRun(selectedRun);
      else await loadRuns(undefined, { autoSelect: false });
    } catch (err) {
      setError(String(err));
    } finally {
      setProfileInFlight(false);
    }
  };

  const configureProviderCommandAction = async (message: string) => {
    if (profileInFlight) return;
    setError("");
    setProfileInFlight(true);
    try {
      const response = await client.agentMessage(message);
      if (selectedRun) appendLocalAgentReply(response);
      else setNewTaskReply(response);
      const [nextDoctor, nextConfig] = await Promise.all([client.getDoctor({ include_mcp: false, host: readinessHost.id }), client.getConfig()]);
      setDoctor(nextDoctor);
      setConfig(nextConfig);
      if (selectedRun) await refreshRun(selectedRun);
      else await loadRuns(undefined, { autoSelect: false });
    } catch (err) {
      setError(String(err));
    } finally {
      setProfileInFlight(false);
    }
  };

  const createEconomyProviderAction = async (draft: EconomyProviderDraft) => {
    if (profileInFlight) return;
    setError("");
    setProfileInFlight(true);
    try {
      const result = await client.createProvider({
        provider_id: draft.providerId,
        roles: ["write", "fix"],
        command: draft.command,
        args: [],
        prompt_mode: "stdin",
        output_contract: "writer_diff",
        activate_economy: true,
        economy_model: draft.model,
        economy_label: draft.label
      });
      const routing = result.status ? profileStatusToRouting(result.status) : undefined;
      const response: AgentResponse = {
        run_id: null,
        action: "provider_create",
        ok: true,
        reply: `Economy provider ${result.provider ?? draft.providerId} activated.`,
        profile: result.status,
        routing,
        actions: result.actions ?? [],
        action_groups: result.action_groups ?? result.status?.action_groups ?? [],
        next_actions: result.next_actions ?? ["readiness", "start"]
      };
      if (selectedRun) appendLocalAgentReply(response);
      else setNewTaskReply(response);
      const [nextDoctor, nextConfig] = await Promise.all([client.getDoctor({ include_mcp: false, host: readinessHost.id }), client.getConfig()]);
      setDoctor(nextDoctor);
      setConfig(nextConfig);
      if (selectedRun) await refreshRun(selectedRun);
      else await loadRuns(undefined, { autoSelect: false });
    } catch (err) {
      setError(String(err));
    } finally {
      setProfileInFlight(false);
    }
  };

  const runGenericLocalAgentAction = async (message: string) => {
    if (!message || profileInFlight) return;
    setError("");
    setProfileInFlight(true);
    try {
      const response = await client.agentMessage(message, { include: { plan: true }, background: true });
      if (selectsLocalOnlyMode(response)) setLocalOnlyMode(true);
      if (selectedRun) appendLocalAgentReply(response);
      else setNewTaskReply(response);
      if (response.run_id && isLatestRunReadOnlyResponse(response)) {
        await refreshRun(response.run_id, response);
      } else {
        await loadRuns(selectedRun || undefined, { autoSelect: false });
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setProfileInFlight(false);
    }
  };

  const openReadinessAction = async (force = false, host: SetupHostOption = readinessHost, skipMcp = localOnlyMode) => {
    if (skipMcp) setLocalOnlyMode(true);
    if (host.id !== readinessHost.id) {
      setReadinessHost(host);
      force = true;
    }
    setDiagnosticsOpen(true);
    setActiveTab("Readiness");
    if (doctor && !force) return;
    try {
      const localOnly = skipMcp || localOnlyMode;
      setDoctor(await client.getDoctor({ include_mcp: false, host: host.id, ...(localOnly ? { skip_mcp: true } : {}) }));
    } catch (err) {
      setError(String(err));
    }
  };

  const runHealthAction = async (action: AgentHealthAction) => {
    if (action.safe === false) return;
    if (action.kind === "open_run" && action.run_id) {
      setError("");
      setNewTaskMode(false);
      setNewTaskReply(null);
      if (action.tab && diagnosticTabs.has(action.tab as TabName)) {
        setDiagnosticsOpen(true);
        setActiveTab(action.tab as TabName);
      }
      await loadRuns(action.run_id);
      return;
    }
    const targetRun = action.run_id || selectedRun;
    if (action.kind === "local_agent" && action.message && ["context", "events", "status"].includes(action.message) && targetRun) {
      if (action.message === "context") {
        await loadContextNow(targetRun);
        await loadRuns(targetRun);
        return;
      }
      if (action.message === "events") {
        setDiagnosticsOpen(true);
        setActiveTab("Trace");
      }
      await refreshRun(targetRun);
      return;
    }
    if (action.kind === "local_agent" && isCancelBackgroundAction(action) && targetRun) {
      setError("");
      setProfileInFlight(true);
      try {
        const response = await client.agentMessage(action.message || "cancel background job", { runId: targetRun });
        appendLocalAgentReply(response, targetRun);
        await refreshRun(targetRun, response);
      } catch (err) {
        setError(String(err));
      } finally {
        setProfileInFlight(false);
      }
      return;
    }
    if (isConfigureReasonixAction(action)) {
      await configureReasonixCommandAction(action.message || "configure reasonix command");
      return;
    }
    if (isProviderCommandConfigureAction(action)) {
      await configureProviderCommandAction(action.message || providerCommandMessage(action, ""));
      return;
    }
    if (action.kind === "local_agent" && (action.id === "apply_economy_profile" || action.message === "apply economy profile")) {
      await applyEconomyProfileAction();
      return;
    }
    if (action.kind === "focus_composer" || action.id === "start_new_task") {
      setDiagnosticsOpen(true);
      setActiveTab("Trace");
      startNewTask();
      composerRef.current?.focus();
      return;
    }
    if (action.kind === "diagnostic_tab" && action.tab && diagnosticTabs.has(action.tab as TabName)) {
      setDiagnosticsOpen(true);
      setActiveTab(action.tab as TabName);
      return;
    }
    if (action.id === "refresh_readiness" || action.message === "readiness") {
      await openReadinessAction(true, setupHostFromAction(action, readinessHost));
      return;
    }
    if (action.kind === "local_agent" && action.message) {
      await runGenericLocalAgentAction(action.message);
    }
  };

  const runDoctorAction = async (action: AgentHealthAction) => {
    if (action.safe === false) return;
    const actionHost = setupHostFromAction(action, readinessHost);
    if (action.kind === "open_run" && action.run_id) {
      setError("");
      setNewTaskMode(false);
      setNewTaskReply(null);
      if (action.tab && diagnosticTabs.has(action.tab as TabName)) {
        setDiagnosticsOpen(true);
        setActiveTab(action.tab as TabName);
      }
      await loadRuns(action.run_id);
      return;
    }
    if (action.kind === "focus_composer" || action.id === "start_new_task") {
      setDiagnosticsOpen(true);
      setActiveTab("Trace");
      startNewTask();
      composerRef.current?.focus();
      return;
    }
    if (action.kind === "diagnostic_tab" && action.tab && diagnosticTabs.has(action.tab as TabName)) {
      setDiagnosticsOpen(true);
      setActiveTab(action.tab as TabName);
      return;
    }
    if (isConfigureReasonixAction(action)) {
      await configureReasonixCommandAction(action.message || "configure reasonix command");
      return;
    }
    if (isProviderCommandConfigureAction(action)) {
      await configureProviderCommandAction(action.message || providerCommandMessage(action, ""));
      return;
    }
    if (
      action.id === "install_skill" ||
      (action.kind === "local_agent" &&
        action.message &&
        (isSkillOnlySetupText(action.message) || isMcpOnlySetupText(action.message) || isNoMcpSetupText(action.message)))
    ) {
      await runSetupAction(actionHost, action.message || actionHost.message);
      return;
    }
    if (action.id === "run_setup" || action.message?.startsWith("patchbay setup")) {
      await runSetupAction(actionHost);
      return;
    }
    if (action.id === "apply_economy_profile" || action.message === "apply economy profile") {
      await applyEconomyProfileAction();
      return;
    }
    if (action.id === "refresh_readiness" || action.message === "readiness") {
      await openReadinessAction(true, actionHost);
      return;
    }
    if (action.kind === "local_agent" && action.message) {
      await runGenericLocalAgentAction(action.message);
    }
  };

  const runLocalReplyAction = async (action: LocalReplyAction) => {
    if (action.phaseAction) {
      handleAction({
        id: action.id,
        label: action.label,
        action: action.phaseAction,
        safe: action.safe !== false,
        requires_human_confirmation: action.requiresConfirmation ?? action.phaseAction !== "continue",
        reason: action.reason
      });
      return;
    }
    if (["install-skill-only", "register-mcp-only", "setup-without-mcp"].includes(action.id)) {
      await runSetupAction(setupHostFromLocalReplyAction(action), action.message);
      return;
    }
    if (action.id.startsWith("setup")) {
      await runSetupAction(setupHostFromLocalReplyAction(action));
      return;
    }
    if (action.id === "apply-economy") {
      await applyEconomyProfileAction();
      return;
    }
    if (action.id === "configure_reasonix_command" || action.message.startsWith("configure reasonix command")) {
      await configureReasonixCommandAction(action.message);
      return;
    }
    if (action.id === "readiness" || action.id.startsWith("readiness-")) {
      await openReadinessAction(Boolean(action.skipMcp), setupHostById(action.host), action.skipMcp ?? localOnlyMode);
      return;
    }
    if (action.id === "open-latest-run") {
      const runId = action.runId ?? newTaskReply?.run_reference?.run_id ?? newTaskReply?.recent_run?.run_id;
      if (!runId) {
        setError("No recent run was returned by Patchbay Agent.");
        return;
      }
      const requestedTab = action.tab ?? newTaskReply?.run_reference?.requested_view?.tab ?? newTaskReply?.requested_view?.tab;
      setError("");
      setNewTaskMode(false);
      setNewTaskReply(null);
      if (requestedTab && diagnosticTabs.has(requestedTab as TabName)) {
        setDiagnosticsOpen(true);
        setActiveTab(requestedTab as TabName);
      }
      await loadRuns(runId);
      return;
    }
    if (action.tab && diagnosticTabs.has(action.tab as TabName)) {
      setDiagnosticsOpen(true);
      setActiveTab(action.tab as TabName);
      return;
    }
    if (action.id === "start") {
      startNewTask();
      composerRef.current?.focus();
      return;
    }
    if (action.id === "runs") {
      setError("");
      try {
        if (selectedRun) {
          const response = await client.agentMessage(action.message || "status", {
            runId: selectedRun,
            include: { diff: true, review: true },
            background: true
          });
          appendLocalAgentReply(response);
          await refreshRun(selectedRun, response);
        } else {
          const response = await client.agentMessage(action.message || "status");
          setNewTaskReply(response);
          await loadRuns();
        }
      } catch (err) {
        setError(String(err));
      }
      return;
    }
    if (action.message) {
      await runGenericLocalAgentAction(action.message);
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
        if (selectsLocalOnlyMode(created)) setLocalOnlyMode(true);
        setComposer("");
        setNewTaskReply(null);
        if (isLatestRunReadOnlyResponse(created)) {
          appendLocalMessage(text, created.run_id);
          appendLocalAgentReply(created, created.run_id);
          setNewTaskMode(false);
          await refreshRun(created.run_id, created);
          return;
        }
        if (!created.run_id) {
          appendLocalMessage(text);
          setNewTaskMode(true);
          setNewTaskReply(created);
          const responseHost = hostFromAgentResponse(created);
          const responseDoctor = created.setup?.doctor ?? created.doctor;
          if (responseHost) setReadinessHost(setupHostById(responseHost));
          if (responseDoctor) setDoctor(responseDoctor);
          await loadRuns(undefined, { autoSelect: false });
          return;
        }
        setNewTaskMode(false);
        appendLocalMessage(text, created.run_id);
        appendLocalAgentReply(created, created.run_id);
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
        if (selectsLocalOnlyMode(response)) setLocalOnlyMode(true);
        appendLocalAgentReply(response);
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

  const selectInboxGroup = (key: string) => {
    setStatusFilter("");
    setInboxFilter((current) => (current === key ? "" : key));
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
        <RunInboxSummary inbox={runsInbox} selectedKey={inboxFilter} onSelectGroup={selectInboxGroup} />
        <div className="run-list" aria-label="运行线程">
          {visibleRuns.map((run) => (
            <div
              className={`run-item ${run.run_id === selectedRun ? "selected" : ""}`}
              key={run.run_id}
            >
              <button
                className="run-select"
                type="button"
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
                <RunInboxBadge run={run} />
                <BackgroundJobBadge job={run.background_job} />
              </button>
              <RunInboxActionButton
                run={run}
                busy={interactionBusy}
                onPhaseAction={handleAction}
                onHealthAction={(action) => void runHealthAction(action)}
              />
            </div>
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
                  <button className="empty-action" type="button" onClick={() => void runSetupAction(readinessHost)} disabled={setupInFlight}>
                    {setupInFlight ? <RefreshCw size={14} /> : <Settings size={14} />}
                    {setupInFlight ? "运行中" : "运行 setup"}
                  </button>
                  <button
                    className="empty-action secondary"
                    type="button"
                    onClick={() => void runSetupAction(readinessHost, setupWithoutMcpMessage(readinessHost))}
                    disabled={setupInFlight}
                  >
                    {setupInFlight ? <RefreshCw size={14} /> : <ShieldCheck size={14} />}
                    本地 setup
                  </button>
                  <button
                    className="empty-action secondary"
                    type="button"
                    onClick={() => void openReadinessAction()}
                  >
                    <ShieldCheck size={14} />
                    就绪
                  </button>
                </div>
                <SetupHostButtons onRunSetup={runSetupAction} setupBusy={setupInFlight} selectedHost={readinessHost} onSelectHost={setReadinessHost} />
              </div>
              {localRunMessages.map((message) => (
                <Fragment key={message.id}>
                  {message.hideBubble ? null : (
                    <ChatBubble
                      role={message.role ?? "user"}
                      title={message.role === "assistant" ? "Patchbay Agent" : "本地消息"}
                      body={message.body}
                      timestamp={message.timestamp}
                      tone={message.response?.ok === false ? "failed" : message.role === "assistant" ? "ready" : undefined}
                    />
                  )}
                  <LocalAgentResponseDetails
                    response={message.response}
                    onAction={(action) => void runLocalReplyAction(action)}
                    onCommandAction={(action) => void runHealthAction(action)}
                    actionBusy={setupInFlight || profileInFlight}
                  />
                </Fragment>
              ))}
              {newTaskReply ? <ChatBubble role="assistant" title="Patchbay Agent" body={newTaskReply.reply} tone={newTaskReply.ok === false ? "failed" : "ready"} /> : null}
              <LocalAgentResponseDetails
                response={newTaskReply}
                onAction={(action) => void runLocalReplyAction(action)}
                onCommandAction={(action) => void runHealthAction(action)}
                actionBusy={setupInFlight || profileInFlight}
              />
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
              <BackgroundJobCard
                job={backgroundJob}
                onAction={(action) => void runHealthAction(action)}
              />
              {messages.map((message) => (
                <AgentEventBubble key={message.id} message={message} selected={selectedMessage?.id === message.id} onSelect={() => setSelectedMessage(message)} />
              ))}
              {localRunMessages.map((message) => (
                <Fragment key={message.id}>
                  {message.hideBubble ? null : (
                    <ChatBubble
                      role={message.role ?? "user"}
                      title={message.role === "assistant" ? "Patchbay Agent" : "本地消息"}
                      body={message.body}
                      timestamp={message.timestamp}
                      tone={message.response?.ok === false ? "failed" : message.role === "assistant" ? "ready" : undefined}
                    />
                  )}
                  <LocalAgentResponseDetails
                    response={message.response}
                    onAction={(action) => void runLocalReplyAction(action)}
                    onCommandAction={(action) => void runHealthAction(action)}
                    actionBusy={setupInFlight || profileInFlight}
                  />
                </Fragment>
              ))}
              <NextActionCard
                action={primaryAction}
                suggestions={suggestions}
                busy={runBusy || actionInFlight}
                failureGuidance={failureGuidance}
                failureRecovery={failureRecovery}
                onInspectDiagnostics={() => {
                  setDiagnosticsOpen(true);
                  setActiveTab("Trace");
                }}
                onRecoveryAction={(action) => void runHealthAction(action)}
                onAction={handleAction}
              />
            </>
          )}
        </section>

        <form className="composer" onSubmit={(event) => void submitComposer(event)}>
          {selectedRun && suggestions.length ? (
            <div className="suggestions" aria-label="建议动作">
              {suggestionGroups.map((group) => (
                <div className="suggestion-group" key={group.id}>
                  <span title={group.reason}>{group.label}</span>
                  <div className="suggestion-buttons">
                    {group.suggestions.map((suggestion) => (
                      <button
                        className={`suggestion ${suggestion.safe ? "" : "blocked"}`}
                        type="button"
                        key={suggestion.id}
                        onClick={() => handleAction(suggestion)}
                        disabled={submitting || actionInFlight || (runBusy && !canRunSuggestionWhileBusy(suggestion))}
                      >
                        {suggestion.safe ? <Play size={13} /> : <AlertTriangle size={13} />}
                        {suggestion.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          <div className="composer-box">
            <textarea
              ref={composerRef}
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
              readinessHost={readinessHost}
              localOnlyMode={localOnlyMode}
              onReadinessHostChange={(host) => void openReadinessAction(true, host)}
              onRunSetup={runSetupAction}
              onApplyEconomy={applyEconomyProfileAction}
              onCreateEconomyProvider={(draft) => void createEconomyProviderAction(draft)}
              onDoctorAction={(action) => void runDoctorAction(action)}
              onHealthAction={(action) => void runHealthAction(action)}
              onBackgroundAction={(action) => void runHealthAction(action)}
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
  const badges = [message.provider, message.model, message.tool].filter(Boolean) as string[];
  return (
    <button className={`chat-bubble event tone-${message.tone ?? "idle"} ${selected ? "selected" : ""}`} onClick={onSelect}>
      <div className="avatar">{message.kind === "gate" ? <ShieldCheck size={16} /> : message.kind === "agent" ? <Bot size={16} /> : <MessageSquare size={16} />}</div>
      <div className="bubble-body">
        <div className="bubble-title">
          <strong>{message.title}</strong>
          <span>{timeLabel(message.timestamp)}</span>
        </div>
        {message.body ? <p>{message.body}</p> : null}
        {badges.length ? (
          <div className="event-badges" aria-label="Provider evidence">
            {badges.map((badge) => (
              <span key={badge}>{badge}</span>
            ))}
          </div>
        ) : null}
        <small>{message.status_label ?? statusLabel(message.status)}</small>
      </div>
    </button>
  );
}

function RunInboxSummary({
  inbox,
  selectedKey,
  onSelectGroup
}: {
  inbox?: RunsInbox | null;
  selectedKey?: string;
  onSelectGroup?: (key: string) => void;
}) {
  if (!inbox || !inbox.total) return null;
  const groups = inbox.groups ?? [];
  return (
    <div className="run-inbox-summary" aria-label="Agent inbox summary">
      <div>
        <strong>Agent inbox</strong>
        <span>{inbox.summary ?? `${inbox.total} runs`}</span>
      </div>
      {groups.length ? (
        <div className="run-inbox-groups">
          {groups.slice(0, 3).map((group) => (
            <button
              className={`run-inbox-group tone-${inboxTone(group.key)} ${selectedKey === group.key ? "selected" : ""}`}
              key={group.key ?? group.label}
              onClick={() => group.key && onSelectGroup?.(group.key)}
              type="button"
              aria-pressed={selectedKey === group.key}
            >
              {group.label ?? group.key}
              <strong>{group.count ?? 0}</strong>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function RunInboxBadge({ run }: { run: RunSummary }) {
  if (!run.inbox) return null;
  const detail = inboxDetail(run);
  return (
    <span className={`run-inbox-badge tone-${inboxTone(run.inbox.key)}`} aria-label="Run inbox state" title={run.inbox.summary}>
      <span>{inboxLabel(run)}</span>
      {detail ? <small>{detail}</small> : null}
    </span>
  );
}

function RunInboxActionButton({
  run,
  busy,
  onPhaseAction,
  onHealthAction
}: {
  run: RunSummary;
  busy?: boolean;
  onPhaseAction: (action: SuggestedAction) => void;
  onHealthAction: (action: AgentHealthAction) => void;
}) {
  const phaseAction = inboxSuggestedAction(run);
  const rawAction = run.inbox?.next_action;
  if (!phaseAction && !rawAction) return null;
  const requiresConfirmation = Boolean(phaseAction?.requires_human_confirmation || rawAction?.requires_confirmation || rawAction?.safe === false);
  const label = phaseAction?.label || rawAction?.label || "Open run";
  const disabled = Boolean(busy || (!phaseAction && rawAction?.safe === false));
  const Icon = rawAction?.kind === "diagnostic_tab" || rawAction?.kind === "open_run" ? Search : requiresConfirmation ? ShieldCheck : Play;
  return (
    <button
      className={`run-inbox-action tone-${inboxTone(run.inbox?.key)} ${requiresConfirmation ? "confirmable" : ""}`}
      type="button"
      onClick={() => {
        if (phaseAction) {
          onPhaseAction(phaseAction);
        } else if (rawAction) {
          onHealthAction(rawAction);
        }
      }}
      disabled={disabled}
      title={rawAction?.reason || run.inbox?.summary || label}
      aria-label={`Run inbox action: ${label}`}
    >
      <Icon size={13} />
      <span>{label}</span>
    </button>
  );
}

function BackgroundJobBadge({ job }: { job?: BackgroundJob | null }) {
  if (!job) return null;
  const tone = backgroundJobTone(job);
  const detail = backgroundJobDetail(job);
  const Icon = tone === "failed" ? AlertTriangle : tone === "success" ? Check : RefreshCw;
  return (
    <span className={`background-job-badge tone-${tone}`} aria-label="Background job status">
      <Icon size={12} />
      <span>{backgroundJobTitle(job)}</span>
      {detail ? <small>{detail}</small> : null}
    </span>
  );
}

function BackgroundJobCard({
  job,
  onAction
}: {
  job?: BackgroundJob | null;
  onAction?: (action: AgentHealthAction) => void;
}) {
  if (!job) return null;
  const tone = backgroundJobTone(job);
  const detail = backgroundJobDetail(job);
  const Icon = tone === "failed" ? AlertTriangle : tone === "success" ? Check : RefreshCw;
  const actions = (job.actions ?? []).filter((action) => action.safe !== false);
  return (
    <div className={`background-job-card tone-${tone}`} aria-label="Background job status">
      <Icon size={16} />
      <div>
        <strong>{backgroundJobTitle(job)}</strong>
        {detail ? <span>{detail}</span> : null}
        {job.error ? <p>{job.error}</p> : null}
        {actions.length ? (
          <div className="background-job-actions">
            {actions.map((action) => (
              <button type="button" onClick={() => onAction?.(action)} aria-label={action.label} disabled={!onAction} key={action.id || action.label}>
                {isCancelBackgroundAction(action) ? <XCircle size={13} /> : action.kind === "diagnostic_tab" || action.kind === "open_run" ? <Search size={13} /> : action.message === "context" ? <FileText size={13} /> : <RefreshCw size={13} />}
                {action.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function NextActionCard({
  action,
  suggestions,
  busy,
  failureGuidance,
  failureRecovery,
  onInspectDiagnostics,
  onRecoveryAction,
  onAction
}: {
  action: AgentAction | null | undefined;
  suggestions: SuggestedAction[];
  busy?: boolean;
  failureGuidance?: string;
  failureRecovery?: FailureRecovery | null;
  onInspectDiagnostics?: () => void;
  onRecoveryAction?: (action: AgentHealthAction) => void;
  onAction: (action: SuggestedAction | AgentAction | string) => void;
}) {
  const recoveryGroups = groupedHealthActions(failureRecovery?.actions, failureRecovery?.action_groups);
  const hasFailureRecovery = Boolean(failureRecovery || failureGuidance);
  const failureSummary = failureRecovery?.summary || failureGuidance || "运行遇到错误，请打开诊断查看日志。";
  if (busy) {
    const refreshActions = suggestions.filter(canRunSuggestionWhileBusy);
    return (
      <div className="next-card running" aria-label="后台任务运行中">
        <CircleDot size={16} />
        <div>
          <strong>后台任务运行中</strong>
          <span>Patchbay Agent 会自动刷新进度，也可以安全手动刷新。</span>
        </div>
        {refreshActions.length ? (
          <div className="next-card-actions">
            {refreshActions.slice(0, 4).map((item) => (
              <button type="button" key={item.id} onClick={() => onAction(item)}>
                {isCancelBackgroundAction({ id: item.id || item.action, message: item.message }) ? <XCircle size={13} /> : item.message === "context" || item.action === "poll_context" ? <FileText size={13} /> : <RefreshCw size={13} />}
                {item.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    );
  }
  if (failureRecovery || (!action && !suggestions.length && hasFailureRecovery)) {
    return (
      <div className="next-card failed" aria-label="失败恢复建议">
        <AlertTriangle size={16} />
        <div>
          <strong>运行失败</strong>
          <span>{failureSummary}</span>
          {failureRecovery?.suggested_next_action ? <p>{failureRecovery.suggested_next_action}</p> : null}
          {failureRecovery?.artifacts?.length ? (
            <div className="recovery-artifacts" aria-label="建议检查的失败产物">
              {failureRecovery.artifacts.slice(0, 4).map((artifact) => (
                <span key={artifact}>{artifact}</span>
              ))}
            </div>
          ) : null}
          {recoveryGroups.length ? (
            <div className="recovery-action-groups" aria-label="Failure recovery actions">
              {recoveryGroups.map((group) => (
                <div className="recovery-action-group" key={group.id}>
                  <span title={group.reason}>{group.label}</span>
                  <div className="recovery-actions">
                    {group.actions.map((item) => (
                      <button type="button" key={item.id || item.label} onClick={() => onRecoveryAction?.(item)}>
                        {item.kind === "focus_composer" ? <Plus size={13} /> : <Search size={13} />}
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        {onInspectDiagnostics ? (
          <button type="button" onClick={onInspectDiagnostics}>
            <Search size={13} />
            查看诊断
          </button>
        ) : null}
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
  const alternative = primary?.safe === false ? primary.alternative_action : null;
  return (
    <div className={`next-card ${primary?.safe ? "ready" : "blocked"}`} aria-label="下一步确认">
      {primary?.safe ? <Play size={16} /> : <AlertTriangle size={16} />}
      <div>
        <strong>{primary?.label ?? "下一步"}</strong>
        <span>{primary?.reason || "Patchbay Agent 已准备好继续。"}</span>
      </div>
      {alternative ? (
        <button type="button" onClick={() => onRecoveryAction?.(alternative)} disabled={!onRecoveryAction}>
          <Settings size={13} />
          {alternative.label}
        </button>
      ) : primary ? (
        <button onClick={() => onAction(primary)}>
          {primary.safe ? <Play size={13} /> : <AlertTriangle size={13} />}
          {primary.requires_human_confirmation ? "确认" : "执行"}
        </button>
      ) : null}
    </div>
  );
}

function MetricsGrid({
  metrics,
  onAction,
  actionBusy
}: {
  metrics?: RunMetrics | null;
  onAction?: (action: AgentHealthAction) => void;
  actionBusy?: boolean;
}) {
  const phaseDurations = metricEntries(metrics);
  const slowestPhase = phaseDurations.reduce<[string, number] | null>((slowest, entry) => (!slowest || entry[1] > slowest[1] ? entry : slowest), null);
  const retries = retryEntries(metrics);
  const tokenByPhase = tokenEntries(metrics);
  const costByPhase = costEntries(metrics);
  const tierMetrics = tierMetricEntries(metrics);
  const providerMetrics = providerMetricEntries(metrics);
  const providerCount = metrics?.provider_usage?.filter((item) => item.provider || item.model).length ?? 0;
  const routing = metrics?.routing_evidence;
  const efficiency = metrics?.efficiency_summary;
  const routingCoverage = routingCoverageLabel(routing);
  const economyHealth = economyHealthLabel(routing);
  const routingAction =
    preferredSafeRoutingAction(routing?.actions, routing?.economy_health?.status) ??
    healthActionFromNext(routing?.economy_health?.next_action, routing?.economy_health?.target ?? routing?.target);
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
      {routing?.summary ? (
        <div className={`metric-routing ${routing.economy_configured ? "ready" : "custom"}`} aria-label="路由证据">
          <span>路由证据</span>
          <strong>{routing.summary}</strong>
        </div>
      ) : null}
      <EfficiencySummaryCard summary={efficiency} />
      {routingCoverage ? (
        <div className="metric-row">
          <span>经济覆盖</span>
          <strong>{routingCoverage}</strong>
        </div>
      ) : null}
      {economyHealth ? (
        <div className="metric-row">
          <span>经济健康</span>
          <strong>{economyHealth}</strong>
        </div>
      ) : null}
      {tierMetrics.length ? (
        <div className="phase-metrics" aria-label="Tier 消耗">
          {tierMetrics.map(([tier, usage]) => (
            <span key={tier}>{tierMetricLabel(tier, usage)}</span>
          ))}
        </div>
      ) : null}
      {routingAction ? (
        <div className="metric-action-row" aria-label="路由建议动作">
          <span>{routingAction.reason || "Patchbay 已提供安全的路由后续动作。"}</span>
          {isProviderCommandConfigureAction(routingAction) ? (
            <ProviderCommandAction action={routingAction} onAction={onAction} disabled={actionBusy} />
          ) : routingAction.kind === "command" && routingAction.command ? (
            <CommandActionRow command={routingAction.command} label={routingAction.label} />
          ) : (
            <button
              type="button"
              onClick={() => onAction?.(routingAction)}
              disabled={!onAction || (routingAction.kind !== "diagnostic_tab" && actionBusy)}
            >
              {routingAction.kind === "diagnostic_tab" ? <Search size={13} /> : <Settings size={13} />}
              {routingAction.label}
            </button>
          )}
        </div>
      ) : null}
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

function SetupHostButtons({
  onRunSetup,
  onSelectHost,
  selectedHost,
  setupBusy,
  compact = false
}: {
  onRunSetup: (host?: SetupHostOption, message?: string) => void;
  onSelectHost?: (host: SetupHostOption) => void;
  selectedHost?: SetupHostOption;
  setupBusy?: boolean;
  compact?: boolean;
}) {
  return (
    <div className={`setup-hosts ${compact ? "compact" : ""}`} aria-label="Setup host">
      {setupHostOptions.map((host) => (
        <button
          className="setup-host"
          type="button"
          key={host.id}
          aria-label={`Setup ${host.label}`}
          aria-pressed={selectedHost?.id === host.id}
          onClick={() => {
            onSelectHost?.(host);
            onRunSetup(host);
          }}
          disabled={setupBusy}
        >
          {host.label}
        </button>
      ))}
    </div>
  );
}

function HealthCardGrid({
  cards,
  onAction,
  actionBusy
}: {
  cards?: AgentHealthCard[] | null;
  onAction?: (action: AgentHealthAction) => void;
  actionBusy?: boolean;
}) {
  const visible = (cards ?? []).filter((card) => card.key || card.label || card.detail);
  if (!visible.length) return null;
  return (
    <div className="health-card-grid">
      {visible.map((card) => {
        const cardAction = card.action ?? healthActionFromNext(card.next_action);
        const action = cardAction?.safe === false ? null : cardAction;
        return (
          <div className={`health-card tone-${card.tone ?? "idle"}`} key={card.key || card.label}>
            <div className="health-card-head">
              <span>{card.label || card.key}</span>
              <strong>{healthStatusLabel(card.status)}</strong>
            </div>
            {typeof card.coverage_percent === "number" ? <small>{card.coverage_percent}% economy observed</small> : null}
            {card.detail ? <p>{card.detail}</p> : null}
            {card.recommendation ? <em>{card.recommendation}</em> : null}
            {action && isProviderCommandConfigureAction(action) ? (
              <ProviderCommandAction action={action} onAction={onAction} disabled={actionBusy} />
            ) : action?.kind === "command" && action.command ? (
              <CommandActionRow command={action.command} label={action.label} />
            ) : action ? (
              <button
                className="health-card-action"
                type="button"
                onClick={() => onAction?.(action)}
                disabled={!onAction || (action.kind !== "diagnostic_tab" && actionBusy)}
                title={action.reason}
              >
                {action.kind === "diagnostic_tab" ? <Search size={13} /> : <Settings size={13} />}
                {action.label}
              </button>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function LocalAgentResponseDetails({
  response,
  onAction,
  onCommandAction,
  actionBusy
}: {
  response?: AgentResponse | null;
  onAction?: (action: LocalReplyAction) => void;
  onCommandAction?: (action: AgentHealthAction) => void;
  actionBusy?: boolean;
}) {
  if (!response) return null;
  const commands = localReplyCommandActions(response);
  const commandGroups = localReplyCommandActionGroups(response, commands);
  const suggestions = localReplyActions(response).filter((action) => !(response.run_id && action.id === "open-latest-run" && action.runId === response.run_id));
  const suggestionGroups = localReplyActionGroups(response, suggestions);
  const capabilities = localReplyCapabilities(response);
  const efficiency = response.efficiency_summary ?? response.metrics?.efficiency_summary;
  const hasPanels = Boolean(
    response.gate_diagnosis ||
      response.setup ||
      response.routing ||
      response.metrics?.routing_evidence ||
      efficiency ||
      response.recovery ||
      capabilities.length ||
      commandGroups.length ||
      suggestionGroups.length
  );
  if (!hasPanels) return null;
  return (
    <>
      {response.gate_diagnosis ? <GateDiagnosisCard diagnosis={response.gate_diagnosis} /> : null}
      {response.setup ? <SetupResultCard response={response} /> : null}
      {response.routing || response.metrics?.routing_evidence ? <RoutingResultCard response={response} /> : null}
      <EfficiencySummaryCard summary={efficiency} />
      <LocalRecoveryCard recovery={response.recovery} onAction={onCommandAction} actionBusy={actionBusy} />
      <AgentCapabilitiesList capabilities={capabilities} />
      {commandGroups.length ? (
        <div className="local-agent-command-actions" aria-label="Agent command actions">
          {commandGroups.map((group) => (
            <div className="local-agent-command-group" key={group.id}>
              <span title={group.reason}>{group.label}</span>
              <div className="local-agent-command-rows">
                {group.actions.map((action) => (
                  isProviderCommandConfigureAction(action) ? (
                    <ProviderCommandAction key={action.id || action.command} action={action} onAction={onCommandAction} disabled={actionBusy} />
                  ) : (
                    <CommandActionRow key={action.id || action.command} command={action.command ?? ""} label={action.label} />
                  )
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {suggestionGroups.length ? (
        <div className="local-agent-action-groups" aria-label="Agent 建议动作">
          {suggestionGroups.map((group) => (
            <div className="local-agent-action-group" key={group.id}>
              <span title={group.reason}>{group.label}</span>
              <div className="empty-actions local-agent-actions">
                {group.actions.map((action) => (
                  <button
                    className={`empty-action ${action.id === "apply-economy" ? "" : "secondary"}`}
                    type="button"
                    key={action.id}
                    aria-label={action.label}
                    title={action.reason}
                    onClick={() => onAction?.(action)}
                    disabled={!onAction || actionBusy}
                  >
                    {action.icon === "settings" ? (
                      <Settings size={14} />
                    ) : action.icon === "shield" ? (
                      <ShieldCheck size={14} />
                    ) : action.icon === "search" ? (
                      <Search size={14} />
                    ) : (
                      <Play size={14} />
                    )}
                    {action.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

function LocalRecoveryCard({
  recovery,
  onAction,
  actionBusy
}: {
  recovery?: FailureRecovery | null;
  onAction?: (action: AgentHealthAction) => void;
  actionBusy?: boolean;
}) {
  if (!recovery) return null;
  const groups = groupedHealthActions(recovery.actions, recovery.action_groups);
  const summary = recovery.summary || recovery.error || "运行遇到错误，请打开诊断查看日志。";
  const stage = recovery.stage ? phaseLabel(recovery.stage) : "失败";
  return (
    <div className="local-recovery-card" aria-label="Agent failure recovery">
      <div className="local-recovery-head">
        <AlertTriangle size={15} />
        <strong>失败恢复</strong>
        <span>{stage}</span>
      </div>
      <p>{summary}</p>
      {recovery.error && recovery.error !== summary ? <small>{recovery.error}</small> : null}
      {recovery.suggested_next_action ? (
        <div className="local-recovery-next">
          <span>建议下一步</span>
          <strong>{recovery.suggested_next_action}</strong>
        </div>
      ) : null}
      {recovery.artifacts?.length ? (
        <div className="recovery-artifacts" aria-label="建议检查的失败产物">
          {recovery.artifacts.slice(0, 6).map((artifact) => (
            <span key={artifact}>{artifact}</span>
          ))}
        </div>
      ) : null}
      {groups.length ? (
        <div className="recovery-action-groups" aria-label="Agent failure recovery actions">
          {groups.map((group) => (
            <div className="recovery-action-group" key={group.id}>
              <span title={group.reason}>{group.label}</span>
              <div className="recovery-actions">
                {group.actions.map((item) => (
                  <button
                    type="button"
                    key={item.id || item.label}
                    onClick={() => onAction?.(item)}
                    disabled={!onAction || (actionBusy && item.kind !== "diagnostic_tab")}
                    title={item.reason}
                  >
                    {item.kind === "focus_composer" ? <Plus size={13} /> : item.kind === "diagnostic_tab" ? <Search size={13} /> : <Settings size={13} />}
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function localReplyCapabilities(response: AgentResponse | null) {
  return (response?.capabilities ?? []).filter((capability) => capability.name || capability.summary);
}

function AgentCapabilitiesList({ capabilities }: { capabilities: NonNullable<AgentResponse["capabilities"]> }) {
  if (!capabilities.length) return null;
  return (
    <div className="agent-capabilities" aria-label="Agent capabilities">
      {capabilities.map((capability) => {
        const name = capability.name || "capability";
        const contract = capability.contract;
        const references = [...(capability.references ?? []), ...(contract?.references ?? [])].filter((reference) => reference.path || reference.label);
        const commands = [...(capability.commands ?? []), ...(contract?.commands ?? [])].filter((command): command is string => Boolean(command));
        const tags = [contract?.kind ?? "", contract?.local_only_supported ? "local-only supported" : ""].filter((tag): tag is string => Boolean(tag));
        return (
          <div className="agent-capability" key={capability.name || capability.summary}>
            <strong>{name}</strong>
            {capability.summary ? <span>{capability.summary}</span> : null}
            {tags.length ? (
              <div className="agent-capability-tags">
                {tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            ) : null}
            {contract?.entrypoint ? (
              <div className="agent-capability-entry">
                <span>entrypoint</span>
                <code>{contract.entrypoint}</code>
              </div>
            ) : null}
            {references.length ? (
              <div className="agent-capability-refs" aria-label={`${name} references`}>
                {references.map((reference) => (
                  <div key={reference.path || reference.label}>
                    <code>{reference.path || reference.label}</code>
                    {reference.purpose ? <span>{reference.purpose}</span> : null}
                  </div>
                ))}
              </div>
            ) : null}
            {commands.length ? (
              <div className="agent-capability-commands" aria-label={`${name} commands`}>
                {commands.map((command) => (
                  <code key={command}>{command}</code>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function GateDiagnosisCard({ diagnosis }: { diagnosis?: GateDiagnosis | null }) {
  if (!diagnosis) return null;
  const checks = diagnosis.checks?.length ? diagnosis.checks : diagnosis.blockers ?? [];
  const blockers = diagnosis.blockers?.filter((check) => check.ok === false) ?? [];
  const nextAction = diagnosis.next_action;
  const ready = Boolean(diagnosis.ready_to_apply);
  const status = diagnosis.status || "unknown";
  const nextActionTone = nextAction?.requires_confirmation
    ? "需要显式确认"
    : nextAction?.safe === false
      ? "需手动执行"
      : "安全后续";
  return (
    <div className={`gate-diagnosis-card ${ready ? "ready" : "blocked"}`} aria-label="Gate diagnosis">
      <div className="gate-diagnosis-head">
        <ShieldCheck size={15} />
        <strong>门禁诊断</strong>
        <span>{status}</span>
      </div>
      <p>
        {ready
          ? "所有技术门禁已通过；apply 仍需要显式确认。"
          : blockers.length
            ? `Apply 仍被 ${blockers.length} 项检查阻塞。`
            : "Apply 尚未标记为可执行，请查看状态和事件证据。"}
      </p>
      {nextAction ? (
        <div className="gate-diagnosis-next">
          <span>下一步动作</span>
          <strong>{nextAction.label || nextAction.id}</strong>
          <em>{nextActionTone}</em>
          {nextAction.reason ? <p>{nextAction.reason}</p> : null}
        </div>
      ) : null}
      {checks.length ? (
        <div className="gate-diagnosis-checks">
          {checks.map((check) => {
            const ok = Boolean(check.ok);
            return (
              <div className={`gate-diagnosis-check ${ok ? "ok" : "blocked"}`} key={check.key || check.label || check.detail}>
                <div className="gate-check-icon">{ok ? <Check size={13} /> : <AlertTriangle size={13} />}</div>
                <div>
                  <strong>{check.label || check.key || "Gate check"}</strong>
                  <span>{check.status ?? (ok ? "done" : "blocked")}</span>
                  {check.detail ? <p>{check.detail}</p> : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function SetupResultCard({ response }: { response: AgentResponse }) {
  const setup = response.setup;
  if (!setup) return null;
  const mcp = setup.mcp;
  const host = String(response.setup_host ?? setup.setup_host ?? mcp?.host ?? "codex");
  const command = typeof mcp?.command === "string" ? mcp.command : "";
  const note = typeof mcp?.note === "string" ? mcp.note : "";
  const root = typeof setup.root === "string" ? setup.root : "";
  const nextActions = setup.next_actions ?? [];
  const recommendations = dedupeStrings([
    ...(setup.recommendations ?? []),
    ...(response.recommendations ?? []),
    ...(setup.doctor?.recommendations ?? [])
  ]);
  return (
    <div className="setup-result-card" aria-label="Setup result">
      <div className="setup-result-head">
        <Settings size={15} />
        <strong>{setupHostLabel(host)}</strong>
        <span>{setup.ok ? "ready" : setup.dry_run ? "dry run" : "needs follow-up"}</span>
      </div>
      {root ? (
        <div className="setup-result-row">
          <span>root</span>
          <code>{root}</code>
        </div>
      ) : null}
      {command ? (
        <div className="setup-result-row">
          <span>MCP</span>
          <CommandActionRow command={command} label="MCP registration" />
        </div>
      ) : null}
      {note ? <p>{note}</p> : null}
      {nextActions.length ? (
        <div className="setup-result-actions">
          {nextActions.slice(0, 3).map((action) => (
            <span key={action}>{action}</span>
          ))}
        </div>
      ) : null}
      {recommendations.length ? (
        <div className="setup-result-recommendations">
          <strong>建议</strong>
          {recommendations.slice(0, 3).map((recommendation) => (
            <span key={recommendation}>{recommendation}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function RoutingResultCard({ response }: { response: AgentResponse }) {
  const routing = response.routing ?? response.metrics?.routing_evidence;
  if (!routing) return null;
  return <RoutingEvidenceCard routing={routing} />;
}

function RoutingEvidenceCard({ routing }: { routing: RoutingEvidence }) {
  const write = routing.phases?.write?.configured;
  const fix = routing.phases?.fix?.configured;
  const writeSignal = routeEvidenceLabel("write", routing);
  const fixSignal = routeEvidenceLabel("fix", routing);
  const workloadPolicy = routing.workload_policy;
  return (
    <div className={`routing-result-card ${routing.economy_configured ? "ready" : "custom"}`} aria-label="Routing result">
      <div className="routing-result-head">
        <Settings size={15} />
        <strong>{routing.economy_configured ? "经济路由已启用" : "经济路由未启用"}</strong>
        {routing.profile ? <span>{routing.profile}</span> : null}
      </div>
      {routing.summary ? <p>{routing.summary}</p> : null}
      {workloadPolicy?.summary ? (
        <div className="routing-workload-policy" aria-label="Workload routing policy">
          <p>{workloadPolicy.summary}</p>
          <div>
            <span>{(workloadPolicy.economy_phases ?? ["write", "fix"]).join("/")} → {workloadPolicy.target_label ?? "economy"}</span>
            <span>{(workloadPolicy.supervision_phases ?? ["plan", "review"]).join("/")} → supervision</span>
          </div>
        </div>
      ) : null}
      <div className="routing-result-routes">
        <div>
          <span>实现</span>
          <strong>{routeSummary(write)}</strong>
          {writeSignal ? <small>{writeSignal}</small> : null}
        </div>
        <div>
          <span>修复</span>
          <strong>{routeSummary(fix)}</strong>
          {fixSignal ? <small>{fixSignal}</small> : null}
        </div>
      </div>
      {routing.recommendation ? <small>{routing.recommendation}</small> : null}
    </div>
  );
}

function CommandActionRow({ command, label }: { command: string; label: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  if (!command) return null;
  const copyCommand = async () => {
    const copied = await copyTextToClipboard(command);
    setCopyState(copied ? "copied" : "failed");
  };
  return (
    <div className={`command-action-row ${copyState}`}>
      <code>{command}</code>
      <button type="button" aria-label={`Copy command ${label}`} onClick={() => void copyCommand()}>
        {copyState === "copied" ? <Check size={13} /> : <Copy size={13} />}
        {copyState === "copied" ? "Copied" : copyState === "failed" ? "Unavailable" : "Copy"}
      </button>
    </div>
  );
}

function PhaseStrategyMap({
  strategy,
  routing,
  providers
}: {
  strategy?: Record<string, PhaseStrategy> | null;
  routing?: RoutingEvidence | null;
  providers?: Record<string, PhaseProvider>;
}) {
  const entries = phaseStrategyEntries(strategy, routing, providers);
  if (!entries.length) return null;
  return (
    <div className="phase-strategy-map" aria-label="四阶段路由策略">
      {entries.map(([phase, item]) => {
        const isWriterPhase = phase === "write" || phase === "fix";
        const tier = item.tier ?? (isWriterPhase ? (item.economy_route ? "economy" : "custom") : "supervision");
        const signal = routeEvidenceLabel(phase, routing);
        return (
          <div className={`phase-strategy-node ${tier === "economy" ? "economy" : tier === "custom" ? "custom" : "supervision"}`} key={phase}>
            <div className="phase-strategy-head">
              <span>{phaseLabel(phase)}</span>
              <strong>{strategyTierLabel(tier)}</strong>
            </div>
            <code>{routeSummary(item)}</code>
            {signal ? <small>{signal}</small> : <small>{item.reason ?? strategyReason(phase)}</small>}
            {item.error ? <em>{item.error}</em> : null}
          </div>
        );
      })}
    </div>
  );
}

function ReasonixCommandAction({
  action,
  onAction,
  disabled
}: {
  action: AgentHealthAction;
  onAction?: (action: AgentHealthAction) => void;
  disabled?: boolean;
}) {
  const [path, setPath] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onAction?.({ ...action, message: reasonixCommandMessage(path) });
  };
  return (
    <form className="reasonix-command-action" onSubmit={submit}>
      <label>
        <span>Reasonix path</span>
        <input
          aria-label="Reasonix command path"
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="reasonix or full path"
          disabled={disabled}
        />
      </label>
      <button type="submit" disabled={!onAction || disabled}>
        <Settings size={13} />
        {action.label || "Configure Reasonix"}
      </button>
    </form>
  );
}

function ProviderCommandAction({
  action,
  onAction,
  disabled
}: {
  action: AgentHealthAction;
  onAction?: (action: AgentHealthAction) => void;
  disabled?: boolean;
}) {
  const [path, setPath] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onAction?.({ ...action, message: providerCommandMessage(action, path) });
  };
  const copyCommand = async () => {
    if (!action.command) return;
    const copied = await copyTextToClipboard(action.command);
    setCopyState(copied ? "copied" : "failed");
  };
  return (
    <form className={`reasonix-command-action provider-command-action ${copyState}`} onSubmit={submit}>
      <label>
        <span>{providerCommandLabel(action)}</span>
        <input
          aria-label="Provider command path"
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="executable or wrapper path"
          disabled={disabled}
        />
      </label>
      <button type="submit" disabled={!onAction || disabled || !path.trim()}>
        <Settings size={13} />
        Configure
      </button>
      {action.command ? (
        <button type="button" aria-label={`Copy command ${action.label}`} onClick={() => void copyCommand()}>
          {copyState === "copied" ? <Check size={13} /> : <Copy size={13} />}
          {copyState === "copied" ? "Copied" : "Copy"}
        </button>
      ) : null}
    </form>
  );
}

function DoctorActionButtons({
  actions,
  onAction,
  setupBusy,
  profileBusy
}: {
  actions?: AgentHealthAction[] | null;
  onAction?: (action: AgentHealthAction) => void;
  setupBusy?: boolean;
  profileBusy?: boolean;
}) {
  const visible = actions ?? [];
  if (!visible.length) return null;
  return (
    <div className="doctor-action-buttons" aria-label="Readiness actions">
      {visible.map((action) =>
        isProviderCommandConfigureAction(action) ? (
          <ProviderCommandAction
            key={action.id || action.label}
            action={action}
            onAction={onAction}
            disabled={setupBusy || profileBusy}
          />
        ) : action.kind === "command" ? (
          <CommandActionRow key={action.id || action.label} command={action.command ?? ""} label={action.label} />
        ) : isConfigureReasonixAction(action) ? (
          <ReasonixCommandAction
            key={action.id || action.label}
            action={action}
            onAction={onAction}
            disabled={setupBusy || profileBusy}
          />
        ) : (
          <button
            type="button"
            key={action.id || action.label}
            title={action.reason}
            onClick={() => onAction?.(action)}
            disabled={!onAction || setupBusy || (action.id === "apply_economy_profile" && profileBusy)}
          >
            {action.id === "apply_economy_profile" ? <Play size={13} /> : action.id === "refresh_readiness" ? <ShieldCheck size={13} /> : <Settings size={13} />}
            {action.label}
          </button>
        )
      )}
    </div>
  );
}

function EconomyProviderForm({
  onSubmit,
  disabled
}: {
  onSubmit?: (draft: EconomyProviderDraft) => void;
  disabled?: boolean;
}) {
  const [providerId, setProviderId] = useState("cheap_writer");
  const [command, setCommand] = useState("deepseek-writer");
  const [model, setModel] = useState("deepseek-chat");
  const [label, setLabel] = useState("DeepSeek cheap writer");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit?.({
      providerId: providerId.trim(),
      command: command.trim(),
      model: model.trim(),
      label: label.trim()
    });
  };
  const blocked = disabled || !providerId.trim() || !command.trim() || !model.trim();
  return (
    <form className="economy-provider-form" aria-label="Economy provider" onSubmit={submit}>
      <label>
        <span>Provider id</span>
        <input aria-label="Provider id" value={providerId} onChange={(event) => setProviderId(event.target.value)} disabled={disabled} />
      </label>
      <label>
        <span>Writer command</span>
        <input aria-label="Writer command" value={command} onChange={(event) => setCommand(event.target.value)} disabled={disabled} />
      </label>
      <label>
        <span>Model</span>
        <input aria-label="Economy model" value={model} onChange={(event) => setModel(event.target.value)} disabled={disabled} />
      </label>
      <label>
        <span>Label</span>
        <input aria-label="Economy label" value={label} onChange={(event) => setLabel(event.target.value)} disabled={disabled} />
      </label>
      <button type="submit" disabled={!onSubmit || blocked}>
        <Plus size={13} />
        Activate economy provider
      </button>
    </form>
  );
}

function DoctorPanel({
  report,
  readinessHost,
  localOnlyMode,
  onReadinessHostChange,
  onRunSetup,
  onApplyEconomy,
  onCreateEconomyProvider,
  onDoctorAction,
  setupBusy,
  profileBusy
}: {
  report?: DoctorReport | null;
  readinessHost?: SetupHostOption;
  localOnlyMode?: boolean;
  onReadinessHostChange?: (host: SetupHostOption) => void;
  onRunSetup?: (host?: SetupHostOption, message?: string) => void;
  onApplyEconomy?: () => void;
  onCreateEconomyProvider?: (draft: EconomyProviderDraft) => void;
  onDoctorAction?: (action: AgentHealthAction) => void;
  setupBusy?: boolean;
  profileBusy?: boolean;
}) {
  const checks = Object.entries(report?.checks ?? {});
  const profile = doctorProfileStatus(report);
  const economy = profile?.economy;
  const routing = report?.routing;
  const doctorActions = report?.actions ?? [];
  const doctorActionGroups = groupedHealthActions(doctorActions, report?.action_groups);
  const canCreateEconomyProvider = Boolean(
    onCreateEconomyProvider &&
      doctorActions.some((action) => action.id === "configure_deepseek_provider" || action.message === "configure DeepSeek provider")
  );
  const selectedHost = readinessHost ?? setupHostById(report?.host);
  const hostSelectLabel = localOnlyMode ? "Setup host" : "MCP host";
  return (
    <div className="doctor-panel">
      {onRunSetup ? (
        <div className="doctor-toolbar">
          <label className="doctor-host-select">
            <span id="doctor-host-select-label">{hostSelectLabel}</span>
            <select
              aria-labelledby="doctor-host-select-label"
              value={selectedHost.id}
              onChange={(event) => onReadinessHostChange?.(setupHostById(event.target.value))}
              disabled={setupBusy}
            >
              {setupHostOptions.map((host) => (
                <option value={host.id} key={host.id}>
                  {host.label}
                </option>
              ))}
            </select>
          </label>
          <button className="doctor-setup-button" type="button" onClick={() => onRunSetup(selectedHost)} disabled={setupBusy}>
            {setupBusy ? <RefreshCw size={14} /> : <Settings size={14} />}
            {setupBusy ? "运行中" : "运行 setup"}
          </button>
          <button
            className="doctor-setup-button secondary"
            type="button"
            onClick={() => onRunSetup(selectedHost, setupWithoutMcpMessage(selectedHost))}
            disabled={setupBusy}
          >
            {setupBusy ? <RefreshCw size={14} /> : <ShieldCheck size={14} />}
            本地 setup
          </button>
          <SetupHostButtons onRunSetup={onRunSetup} setupBusy={setupBusy} selectedHost={selectedHost} compact />
        </div>
      ) : null}
      <div className={`doctor-summary ${report?.ok ? "ready" : "blocked"}`}>
        {report?.ok ? <Check size={16} /> : <AlertTriangle size={16} />}
        <div>
          <strong>{report?.ok ? "环境就绪" : "需要处理"}</strong>
          <span>
            {report?.root ?? "正在读取 Patchbay doctor 结果"} · {setupHostLabel(report?.host ?? selectedHost.id)}
          </span>
        </div>
      </div>
      {doctorActionGroups.length ? (
        <section>
          <h2>Actions</h2>
          <div className="doctor-action-groups" aria-label="Readiness action groups">
            {doctorActionGroups.map((group) => (
              <div className="doctor-action-group" key={group.id}>
                <div className="doctor-action-group-head">
                  <strong>{group.label}</strong>
                  {group.reason ? <span>{group.reason}</span> : null}
                </div>
                <DoctorActionButtons actions={group.actions} onAction={onDoctorAction} setupBusy={setupBusy} profileBusy={profileBusy} />
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {canCreateEconomyProvider ? (
        <section>
          <h2>Economy provider</h2>
          <EconomyProviderForm onSubmit={onCreateEconomyProvider} disabled={profileBusy} />
        </section>
      ) : null}
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
              const canApplyEconomy = /config profile apply economy/i.test(recommendation);
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
      {routing ? (
        <section>
          <h2>路由</h2>
          <RoutingEvidenceCard routing={routing} />
        </section>
      ) : profile ? (
        <section>
          <h2>路由</h2>
          <div className={`doctor-profile ${economy?.matches ? "ready" : "custom"}`}>
            <div className="doctor-profile-head">
              <strong>{economy?.matches ? "经济路由已启用" : "自定义路由"}</strong>
              <span>{economy?.intent || profile.recommendation || "当前配置使用自定义阶段路由。"}</span>
            </div>
            <div className="doctor-routes">
              <div>
                <span>实现</span>
                <strong>{routeSummary(economy?.write)}</strong>
              </div>
              <div>
                <span>修复</span>
                <strong>{routeSummary(economy?.fix)}</strong>
              </div>
            </div>
          </div>
        </section>
      ) : null}
      {profile?.phase_strategy ? (
        <section>
          <h2>四阶段路由</h2>
          <PhaseStrategyMap strategy={profile.phase_strategy} />
        </section>
      ) : null}
      <section>
        <h2>检查项</h2>
        <div className="doctor-checks">
          {checks.length ? (
            checks.map(([name, check]) => {
              const details = doctorCheckDetails(check);
              return (
                <div className={`doctor-check ${doctorCheckTone(check)}`} key={name}>
                  <span>{name}</span>
                  <strong>{doctorCheckStatusLabel(check)}</strong>
                  {details.map((detail) => (
                    <small key={detail}>{detail}</small>
                  ))}
                </div>
              );
            })
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
  readinessHost,
  localOnlyMode,
  onReadinessHostChange,
  onRunSetup,
  onApplyEconomy,
  onCreateEconomyProvider,
  onDoctorAction,
  onHealthAction,
  onBackgroundAction,
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
  readinessHost?: SetupHostOption;
  localOnlyMode?: boolean;
  onReadinessHostChange?: (host: SetupHostOption) => void;
  onRunSetup?: (host?: SetupHostOption, message?: string) => void;
  onApplyEconomy?: () => void;
  onCreateEconomyProvider?: (draft: EconomyProviderDraft) => void;
  onDoctorAction?: (action: AgentHealthAction) => void;
  onHealthAction?: (action: AgentHealthAction) => void;
  onBackgroundAction?: (action: AgentHealthAction) => void;
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
    const routing = context?.routing_evidence ?? metrics?.routing_evidence ?? status?.routing_evidence;
    const effectiveProviders = status?.effective_phase_providers ?? {};
    const hasStrategy = phaseStrategyEntries(undefined, routing, effectiveProviders).length > 0;
    const backgroundJob = context?.background_job ?? activity.background_job ?? status?.background_job ?? null;
    return (
      <div className="overview-panel">
        {backgroundJob ? (
          <section>
            <h2>后台任务</h2>
            <BackgroundJobCard job={backgroundJob} onAction={onBackgroundAction} />
          </section>
        ) : null}
        {hasStrategy ? (
          <section>
            <h2>路由策略</h2>
            <PhaseStrategyMap routing={routing} providers={effectiveProviders} />
          </section>
        ) : null}
        <section>
          <h2>效率</h2>
          <MetricsGrid metrics={metrics} onAction={onHealthAction} actionBusy={profileBusy} />
        </section>
        {(activity.health_cards ?? []).length ? (
          <section>
            <h2>健康</h2>
            <HealthCardGrid cards={activity.health_cards} onAction={onHealthAction} actionBusy={profileBusy} />
          </section>
        ) : null}
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
        readinessHost={readinessHost}
        localOnlyMode={localOnlyMode}
        onReadinessHostChange={onReadinessHostChange}
        onRunSetup={onRunSetup}
        onApplyEconomy={onApplyEconomy}
        onCreateEconomyProvider={onCreateEconomyProvider}
        onDoctorAction={onDoctorAction}
        setupBusy={setupBusy}
        profileBusy={profileBusy}
      />
    );
  }
  if (tab === "Trace") {
    return <TracePanel message={message} trace={trace} rawTrace={rawTrace} />;
  }
  const recovery = diagnosticRecovery(context, status);
  const artifacts = diagnosticArtifacts(context, status, activity, recovery);
  if (tab === "Diff") return <DiffPanel diff={diff} />;
  if (tab === "Log") return <LogPanel artifactText={artifactText} recovery={recovery} status={status} artifacts={artifacts} />;
  if (tab === "Artifacts") return <ArtifactsPanel artifactText={artifactText} artifacts={artifacts} recovery={recovery} status={status} />;
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
    <ConfigPanel config={config} />
  );
}

export default Workbench;
