const state = {
  runId: "",
  eventCursor: 0,
  lastConfirmation: null,
};

const statusLabels = {
  PLANNED: "待批准",
  APPROVED: "已批准",
  IMPLEMENTING: "实现中",
  IMPLEMENTED: "待测试",
  TESTING: "测试中",
  TESTED: "待审查",
  REVIEWING: "审查中",
  REVIEWED_PASS: "待应用",
  REVIEWED_CHANGES_REQUESTED: "需修复",
  FIXING: "修复中",
  APPLIED: "已应用",
  FAILED: "失败",
};

const phaseLabels = {
  agent: "Agent",
  plan: "计划",
  approve: "批准",
  write: "实现",
  test: "测试",
  review: "审查",
  fix: "修复",
  apply: "应用",
};

const messages = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const input = document.querySelector("#messageInput");
const runLabel = document.querySelector("#runLabel");
const statusPill = document.querySelector("#statusPill");
const statusBox = document.querySelector("#statusBox");
const timeline = document.querySelector("#timeline");
const artifactBox = document.querySelector("#artifactBox");
const confirmRow = document.querySelector("#confirmRow");
const approveButton = document.querySelector("#approveButton");
const applyButton = document.querySelector("#applyButton");

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  appendMessage("user", text);
  input.value = "";
  await sendMessage(text);
});

document.querySelector("#refreshButton").addEventListener("click", () => refreshStatus());

approveButton.addEventListener("click", async () => {
  await sendMessage("批准计划", "plan_approved");
});

applyButton.addEventListener("click", async () => {
  await sendMessage("应用变更", "apply_approved");
});

document.querySelectorAll("[data-artifact]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.runId) return;
    setActiveArtifact(button);
    const name = button.getAttribute("data-artifact");
    const url = name === "FINAL.diff"
      ? `/api/diff?run_id=${encodeURIComponent(state.runId)}`
      : `/api/artifact?run_id=${encodeURIComponent(state.runId)}&name=${encodeURIComponent(name)}`;
    const response = await fetch(url);
    const payload = await response.json();
    artifactBox.textContent = payload.diff || payload.text || payload.error || JSON.stringify(payload, null, 2);
  });
});

appendMessage("agent", "已就绪。描述一个任务，我会先生成计划并等待你批准。");

async function sendMessage(message, confirmation = "none") {
  const response = await fetch("/api/message", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      message,
      run_id: state.runId,
      confirmation,
      include: { plan: true, review: true, diff: true, events_since: state.eventCursor },
    }),
  });
  const payload = await response.json();
  renderAgentResponse(payload);
}

async function refreshStatus() {
  if (!state.runId) return;
  const response = await fetch(`/api/status?run_id=${encodeURIComponent(state.runId)}&since=${state.eventCursor}`);
  renderAgentResponse(await response.json(), false);
}

function renderAgentResponse(payload, append = true) {
  if (payload.run_id) state.runId = payload.run_id;
  if (append) appendMessage(payload.ok === false ? "error" : "agent", payload.reply || JSON.stringify(payload, null, 2));

  runLabel.textContent = state.runId ? state.runId : "暂无运行";
  const status = payload.status || {};
  const statusValue = status.status || "IDLE";
  statusPill.textContent = statusLabels[statusValue] || statusValue || "空闲";
  statusPill.classList.toggle("is-failed", statusValue === "FAILED");
  statusPill.classList.toggle("is-ready", Boolean(status.gate_state && status.gate_state.ready_to_apply));

  statusBox.textContent = JSON.stringify({
    "状态": statusLabels[status.status] || status.status || "空闲",
    "当前阶段": phaseLabels[status.current_phase] || status.current_phase || "",
    "下一步": payload.next_actions || status.next_commands || [],
    "门禁": status.gate_state || {},
  }, null, 2);

  renderEvents(payload.events);
  renderConfirmation(payload.requires_confirmation);
  renderArtifacts(payload);
}

function renderEvents(eventsPayload) {
  if (!eventsPayload || !Array.isArray(eventsPayload.events)) return;
  state.eventCursor = eventsPayload.total || state.eventCursor;
  for (const event of eventsPayload.events) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    const phase = phaseLabels[event.phase] || event.phase || "运行";
    title.textContent = `${phase} / ${event.action || event.status}`;
    const meta = document.createElement("span");
    meta.textContent = [event.status, event.detail, event.timestamp].filter(Boolean).join(" | ");
    item.append(title, meta);
    timeline.append(item);
  }
}

function renderConfirmation(confirmation) {
  state.lastConfirmation = confirmation || null;
  confirmRow.hidden = !confirmation;
  approveButton.hidden = !confirmation || confirmation.type !== "plan_approval";
  applyButton.hidden = !confirmation || confirmation.type !== "apply_approval";
}

function renderArtifacts(payload) {
  if (payload.diff) {
    artifactBox.textContent = payload.diff || "当前还没有 diff。";
    setActiveArtifact(document.querySelector('[data-artifact="FINAL.diff"]'));
    return;
  }
  const artifacts = payload.artifacts || {};
  const first = Object.keys(artifacts)[0];
  if (!first) return;
  artifactBox.textContent = artifacts[first].text || artifacts[first].error || JSON.stringify(artifacts[first], null, 2);
  setActiveArtifact(document.querySelector(`[data-artifact="${first}"]`));
}

function appendMessage(kind, text) {
  const node = document.createElement("div");
  node.className = `message ${kind}`;
  node.textContent = text;
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
}

function setActiveArtifact(button) {
  document.querySelectorAll("[data-artifact]").forEach((item) => item.classList.remove("active"));
  if (button) button.classList.add("active");
}
