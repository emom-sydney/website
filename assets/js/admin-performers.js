const config = window.__WORKFLOW_ADMIN_CONFIG || {};
const actionLabels = {
  accept: "Accept",
  waitlist: "Waitlist",
  decline: "Decline",
  ask_for_info: "Ask for info",
  confirmation_reminder: "Send reminder",
  acknowledge_withdrawal: "Acknowledge withdrawal",
  acknowledge_change_request: "Acknowledge change request",
  cancel_by_org: "Cancel by org"
};

const state = {
  apiBase: (config.apiBase || "/api").replace(/\/$/, ""),
  authHeader: null
};

const loginForm = document.getElementById("workflow-admin-login-form");
const refreshButton = document.getElementById("workflow-refresh-button");
const queueContainer = document.getElementById("workflow-queue");
const adminStatus = document.getElementById("workflow-admin-status");
const dialog = document.getElementById("workflow-action-dialog");
const dialogForm = document.getElementById("workflow-action-form");
const dialogTitle = document.getElementById("workflow-action-title");
const dialogStatus = document.getElementById("workflow-dialog-status");
const dialogClose = document.getElementById("workflow-dialog-close");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function setAuthenticated(ok) {
  adminStatus.textContent = ok ? "Credentials saved" : "Not authenticated";
  adminStatus.className = ok ? "admin-status ok" : "admin-status";
}

async function apiFetch(method, path, body) {
  const response = await fetch(`${state.apiBase}${path}`, {
    method,
    headers: {
      Authorization: state.authHeader,
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

function renderQueue(sections = []) {
  queueContainer.innerHTML = sections
    .map((section) => {
      const cards = section.items.length
        ? section.items
            .map(
              (item) => `
                <article class="queue-row">
                  <div class="queue-row-main">
                    <div class="queue-title">${escapeHtml(item.performer.stageName || item.performer.name)}</div>
                    <div class="queue-meta">${escapeHtml(item.event.label)}</div>
                    <div class="queue-meta">Submitted ${escapeHtml(item.createdAt)}</div>
                    <div class="queue-meta">Status: <span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(formatLabel(item.status))}</span></div>
                    ${
                      item.lastActivity?.note
                        ? `<div class="queue-note">Last note: ${escapeHtml(item.lastActivity.note)}</div>`
                        : '<div class="queue-note">Last note: none</div>'
                    }
                  </div>
                  <div class="queue-row-actions">
                    ${item.availableAdminActions
                      .map(
                        (action) => `
                          <button type="button" class="button-secondary queue-action" data-interest-id="${item.id}" data-action="${action}">
                            ${escapeHtml(actionLabels[action] || formatLabel(action))}
                          </button>
                        `
                      )
                      .join("")}
                  </div>
                </article>
              `
            )
            .join("")
        : '<p class="workflow-note">Nothing in this queue.</p>';

      return `
        <section class="workflow-card">
          <div class="workflow-summary">
            <h2>${escapeHtml(section.label)}</h2>
            <div class="workflow-eyebrow">${section.items.length} item${section.items.length === 1 ? "" : "s"}</div>
          </div>
          <div class="queue-section">
            ${cards}
          </div>
        </section>
      `;
    })
    .join("");

  queueContainer.querySelectorAll(".queue-action").forEach((button) => {
    button.addEventListener("click", () => openActionDialog(button.dataset.interestId, button.dataset.action));
  });
}

async function refreshQueue() {
  if (!state.authHeader) {
    queueContainer.innerHTML = '<section class="workflow-card"><p class="workflow-note">Enter credentials first.</p></section>';
    return;
  }

  queueContainer.innerHTML = '<section class="workflow-card"><p class="workflow-note">Loading queue…</p></section>';

  try {
    const result = await apiFetch("GET", "/admin/performer-queue");
    renderQueue(result.sections || []);
  } catch (err) {
    queueContainer.innerHTML = `<section class="workflow-card"><p class="workflow-status error">${escapeHtml(err.message)}</p></section>`;
  }
}

async function openActionDialog(interestId, action) {
  dialogStatus.textContent = "";
  dialogForm.reset();
  dialogTitle.textContent = actionLabels[action] || formatLabel(action);
  dialogForm.elements.interestId.value = interestId;
  dialogForm.elements.action.value = action;

  try {
    const result = await apiFetch("POST", "/admin/action-template", {
      interestId,
      action
    });

    const template = result.template || {};
    dialogForm.elements.note.value = template.note || "";
    dialogForm.elements.sendEmail.checked = Boolean(template.sendEmail);
    dialogForm.elements.emailSubject.value = template.email?.subject || "";
    dialogForm.elements.emailBody.value = template.email?.text || "";
    dialog.showModal();
  } catch (err) {
    adminStatus.textContent = err.message;
    adminStatus.className = "admin-status";
  }
}

loginForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const formData = new FormData(loginForm);
  const apiBase = String(formData.get("apiBase") || "").trim();
  const username = String(formData.get("username") || "");
  const password = String(formData.get("password") || "");

  if (!username || !password) {
    setAuthenticated(false);
    return;
  }

  state.apiBase = apiBase ? apiBase.replace(/\/$/, "") : state.apiBase;
  state.authHeader = `Basic ${btoa(`${username}:${password}`)}`;
  setAuthenticated(true);
  refreshQueue();
});

refreshButton?.addEventListener("click", refreshQueue);
dialogClose?.addEventListener("click", () => dialog.close());

dialogForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  dialogStatus.textContent = "Applying…";
  dialogStatus.className = "workflow-status";

  const payload = {
    interestId: Number(dialogForm.elements.interestId.value),
    action: dialogForm.elements.action.value,
    note: dialogForm.elements.note.value,
    sendEmail: dialogForm.elements.sendEmail.checked,
    emailSubject: dialogForm.elements.emailSubject.value,
    emailBody: dialogForm.elements.emailBody.value
  };

  try {
    await apiFetch("POST", "/admin/interest-action", payload);
    dialog.close();
    refreshQueue();
  } catch (err) {
    dialogStatus.textContent = err.message;
    dialogStatus.className = "workflow-status error";
  }
});
