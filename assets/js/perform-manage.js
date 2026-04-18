const config = window.__WORKFLOW_CONFIG || {};
const apiBase = (config.apiBase || "/api").replace(/\/$/, "");
const storageKey = "emomPerformerManageToken";

const loadStatus = document.getElementById("manage-load-status");
const shell = document.getElementById("manage-shell");
const eventName = document.getElementById("manage-event-name");
const statusBadge = document.getElementById("manage-status-badge");
const lastNote = document.getElementById("manage-last-note");
const historyList = document.getElementById("manage-history");
const detailsForm = document.getElementById("manage-details-form");
const actionStatus = document.getElementById("manage-action-status");
const actionNote = document.getElementById("manage-action-note");
const confirmButton = document.getElementById("confirm-button");
const withdrawButton = document.getElementById("withdraw-button");
const requestChangeButton = document.getElementById("request-change-button");

const state = {
  token: null,
  interest: null
};

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatStatus(status) {
  return String(status || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatAction(action) {
  return formatStatus(action);
}

function readToken() {
  const url = new URL(window.location.href);
  const queryToken = url.searchParams.get("token");
  if (queryToken) {
    sessionStorage.setItem(storageKey, queryToken);
    url.searchParams.delete("token");
    window.history.replaceState({}, "", url.pathname + url.search);
    return queryToken;
  }

  return sessionStorage.getItem(storageKey);
}

function setLoadStatus(message, level = "info") {
  loadStatus.textContent = message;
  loadStatus.className = `workflow-status ${level}`;
}

function setActionStatus(message, level = "info") {
  actionStatus.textContent = message;
  actionStatus.className = `workflow-status ${level}`;
}

function applyCapabilities(interest) {
  const capabilities = interest.performerCapabilities || {};
  const confirmLabel = interest.status === "waitlisted" ? "I can still play" : "Confirm";

  confirmButton.hidden = !capabilities.canConfirm;
  confirmButton.textContent = confirmLabel;
  withdrawButton.hidden = !capabilities.canWithdraw;
  requestChangeButton.hidden = !capabilities.canRequestChange;
  detailsForm.querySelectorAll("input, textarea, button").forEach((element) => {
    if (element.type !== "submit") {
      element.disabled = !capabilities.canEdit;
    }
  });
}

function renderHistory(history = []) {
  if (!history.length) {
    historyList.innerHTML = '<p class="workflow-note">No activity yet.</p>';
    return;
  }

  historyList.innerHTML = history
    .map(
      (item) => `
        <div class="history-item">
          <div class="history-meta">${escapeHtml(formatAction(item.action))} • ${escapeHtml(item.actor)} • ${escapeHtml(item.createdAt)}</div>
          ${item.note ? `<div>${escapeHtml(item.note)}</div>` : ""}
        </div>
      `
    )
    .join("");
}

function renderInterest(interest) {
  state.interest = interest;
  shell.hidden = false;
  setLoadStatus("Private link loaded.", "success");

  eventName.textContent = interest.event.label;
  statusBadge.textContent = formatStatus(interest.status);
  statusBadge.className = `status-badge status-${interest.status}`;

  if (interest.lastActivity?.note) {
    lastNote.hidden = false;
    lastNote.textContent = `Latest note: ${interest.lastActivity.note}`;
  } else {
    lastNote.hidden = true;
  }

  detailsForm.elements.name.value = interest.performer.name || "";
  detailsForm.elements.stageName.value = interest.performer.stageName || "";
  detailsForm.elements.email.value = interest.performer.email || "";
  detailsForm.elements.mobile.value = interest.performer.mobile || "";
  detailsForm.elements.socials.value = interest.performer.socials || "";
  detailsForm.elements.setDescription.value = interest.setDescription || "";
  detailsForm.elements.gearNotes.value = interest.gearNotes || "";
  detailsForm.elements.availability.value = interest.availability || "";

  renderHistory(interest.history || []);
  applyCapabilities(interest);
}

async function apiFetch(method, path, body) {
  const response = await fetch(`${apiBase}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${state.token}`,
      "Content-Type": "application/json"
    },
    body: body ? JSON.stringify(body) : undefined
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "Request failed");
  }

  return result;
}

async function loadInterest() {
  state.token = readToken();
  if (!state.token) {
    setLoadStatus("This page needs the private link from your email.", "error");
    return;
  }

  try {
    const result = await apiFetch("GET", `/performer/manage?token=${encodeURIComponent(state.token)}`);
    renderInterest(result.interest);
  } catch (err) {
    sessionStorage.removeItem(storageKey);
    setLoadStatus(err.message, "error");
  }
}

detailsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = detailsForm.querySelector('button[type="submit"]');
  const payload = Object.fromEntries(new FormData(detailsForm).entries());

  submitButton.disabled = true;
  setActionStatus("Saving details…");

  try {
    const result = await apiFetch("POST", "/performer/manage", {
      action: "update_details",
      ...payload
    });
    renderInterest(result.interest);
    setActionStatus("Details updated.", "success");
  } catch (err) {
    setActionStatus(err.message, "error");
  } finally {
    submitButton.disabled = false;
  }
});

async function sendPerformerAction(action) {
  setActionStatus("Updating…");
  try {
    const result = await apiFetch("POST", "/performer/manage", {
      action,
      note: actionNote.value
    });
    renderInterest(result.interest);
    actionNote.value = "";
    setActionStatus("Update saved.", "success");
  } catch (err) {
    setActionStatus(err.message, "error");
  }
}

confirmButton?.addEventListener("click", () => sendPerformerAction("confirm"));
withdrawButton?.addEventListener("click", () => sendPerformerAction("withdraw"));
requestChangeButton?.addEventListener("click", () => sendPerformerAction("request_change"));

loadInterest();
