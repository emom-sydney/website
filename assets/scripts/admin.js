(function () {
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function readCookie(name) {
    const prefix = `${name}=`;
    const item = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(prefix));
    return item ? decodeURIComponent(item.slice(prefix.length)) : "";
  }

  async function api(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      headers.set("X-CSRF-Token", readCookie("emom_staff_csrf"));
    }
    const response = await fetch(path, { ...options, method, headers, credentials: "same-origin" });
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.error?.message || `Request failed (${response.status}).`);
    }
    return payload.data;
  }

  function status(message, isError = false) {
    const node = document.querySelector("[data-admin-status]");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("is-error", isError);
  }

  document.querySelector("[data-admin-login]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    status("Sending login link…");
    try {
      const data = await api("/api/v1/admin/login-links", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), next: form.get("next") }),
      });
      status(data.message);
      formElement.reset();
    } catch (error) {
      status(error.message, true);
    }
  });

  document.querySelector("[data-admin-logout]")?.addEventListener("click", async () => {
    try {
      await api("/api/v1/admin/session", { method: "DELETE" });
      window.location.assign("/admin/login/");
    } catch (error) {
      window.alert(error.message);
    }
  });

  async function loadDashboard(node) {
    const data = await api("/api/v1/admin/dashboard");
    node.innerHTML = `
      <a class="admin-summary-card" href="/admin/profiles/">
        <strong>${data.pending_profile_submissions}</strong>
        <span>pending profile submissions</span>
      </a>
      <a class="admin-summary-card" href="/admin/events/">
        <strong>${data.upcoming_events}</strong>
        <span>upcoming Open Mic events</span>
      </a>`;
  }

  async function loadEvents(node) {
    const [data, session] = await Promise.all([
      api("/api/v1/admin/events"),
      api("/api/v1/admin/session"),
    ]);
    node.innerHTML = data.events.length
      ? `<div class="admin-list">${data.events.map((event) => `
          <article>
            <h2>${escapeHtml(event.event_name)}</h2>
            <p>${escapeHtml(event.event_date)}</p>
            <div class="admin-actions">
              ${session.is_admin ? `<a href="/admin/events/${event.event_id}/lineup/">Edit lineup</a>` : ""}
              <a href="/admin/events/${event.event_id}/standby/">Standby performers</a>
            </div>
          </article>`).join("")}</div>`
      : "<p>No upcoming Open Mic events.</p>";
  }

  async function loadLineup(node) {
    const eventId = Number(node.dataset.eventId);
    await api(`/api/v1/admin/events/${eventId}/lineup/lock`, { method: "POST" });
    const data = await api(`/api/v1/admin/events/${eventId}/lineup`);
    node.innerHTML = `
      <h2>${escapeHtml(data.event.event_name)} — ${escapeHtml(data.event.event_date)}</h2>
      <p>Select no more than ${data.max_performers} performers.</p>
      <form data-lineup-form>
        <div class="admin-table-wrap"><table>
          <thead><tr><th>Performer</th><th>Availability</th><th>Status</th><th>Reminder</th></tr></thead>
          <tbody>${data.candidates.map((item) => `
            <tr>
              <td>${escapeHtml(item.display_name)}<br><small>${escapeHtml(item.email)}</small></td>
              <td>${escapeHtml(item.availability_status)}</td>
              <td>
                ${item.availability_status === "availability_confirmed" && item.is_profile_approved
                  ? `<select name="status_${item.requested_date_id}">
                      ${["standby", "selected", "reserve"].map((value) =>
                        `<option value="${value}"${item.selection_status === value ? " selected" : ""}>${value}</option>`
                      ).join("")}
                    </select>`
                  : "<small>Available after approval and confirmation</small>"}
              </td>
              <td><button type="button" data-reminder-id="${item.requested_date_id}">Send</button></td>
            </tr>`).join("")}</tbody>
        </table></div>
        <button type="submit">Save lineup</button>
        <p role="status" data-lineup-status></p>
      </form>`;

    node.querySelectorAll("[data-reminder-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const result = await api(
            `/api/v1/admin/events/${eventId}/performer-requests/${button.dataset.reminderId}/availability-reminders`,
            { method: "POST" }
          );
          window.alert(result.message);
        } catch (error) {
          window.alert(error.message);
        } finally {
          button.disabled = false;
        }
      });
    });

    node.querySelector("[data-lineup-form]")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const statuses = {};
      new FormData(event.currentTarget).forEach((value, key) => {
        if (key.startsWith("status_")) statuses[key.slice(7)] = value;
      });
      const statusNode = node.querySelector("[data-lineup-status]");
      statusNode.textContent = "Saving…";
      try {
        const result = await api(`/api/v1/admin/events/${eventId}/lineup`, {
          method: "PUT",
          body: JSON.stringify({ statuses }),
        });
        statusNode.textContent = result.message;
      } catch (error) {
        statusNode.textContent = error.message;
        statusNode.classList.add("is-error");
      }
    });

    const heartbeat = window.setInterval(() => {
      api(`/api/v1/admin/events/${eventId}/lineup/lock`, { method: "POST" }).catch(() => {
        window.clearInterval(heartbeat);
      });
    }, 5 * 60 * 1000);
    window.addEventListener("pagehide", () => {
      window.clearInterval(heartbeat);
      fetch(`/api/v1/admin/events/${eventId}/lineup/lock`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": readCookie("emom_staff_csrf") },
        credentials: "same-origin",
        keepalive: true,
      });
    });
  }

  async function loadStandby(node) {
    const eventId = Number(node.dataset.eventId);
    const data = await api(`/api/v1/admin/events/${eventId}/standby`);
    node.innerHTML = `
      <h2>${escapeHtml(data.event.event_name)} — ${escapeHtml(data.event.event_date)}</h2>
      <h3>Current lineup</h3>
      <ul>${data.current_lineup.map((item) => `<li>${escapeHtml(item.display_name)}</li>`).join("") || "<li>None</li>"}</ul>
      <h3>Available standby/reserve performers</h3>
      ${data.candidates.length ? `<form data-standby-form>
        ${data.candidates.map((item) => `<label class="admin-choice">
          <input type="radio" name="requested_date_id" value="${item.requested_date_id}" required>
          ${escapeHtml(item.display_name)} (${escapeHtml(item.selection_status)})
        </label>`).join("")}
        <button type="submit">Promote performer</button>
        <p role="status" data-standby-status></p>
      </form>` : "<p>No standby performers are available.</p>"}`;
    node.querySelector("[data-standby-form]")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const statusNode = node.querySelector("[data-standby-status]");
      statusNode.textContent = "Promoting…";
      try {
        const result = await api(`/api/v1/admin/events/${eventId}/lineup/promotions`, {
          method: "POST",
          body: JSON.stringify({ requested_date_id: Number(form.get("requested_date_id")) }),
        });
        statusNode.textContent = `${result.promoted.display_name} was promoted.`;
      } catch (error) {
        statusNode.textContent = error.message;
        statusNode.classList.add("is-error");
      }
    });
  }

  async function loadProfiles(node) {
    const data = await api("/api/v1/admin/profiles/submissions?status=pending");
    node.innerHTML = data.submissions.length
      ? `<div class="admin-list">${data.submissions.map((item) => `
          <article>
            <h2><a href="/admin/profiles/submissions/${item.id}/">${escapeHtml(item.display_name)}</a></h2>
            <p>${escapeHtml(item.email)} · ${escapeHtml(item.submitted_at)}</p>
          </article>`).join("")}</div>`
      : "<p>No profile submissions are awaiting moderation.</p>";
  }

  async function loadSubmission(node) {
    const draftId = Number(node.dataset.draftId);
    const data = await api(`/api/v1/admin/profiles/submissions/${draftId}`);
    const item = data.submission;
    node.innerHTML = `
      <h2>${escapeHtml(item.display_name)}</h2>
      <dl class="admin-details">
        <dt>Email</dt><dd>${escapeHtml(item.email)}</dd>
        <dt>Profile type</dt><dd>${escapeHtml(item.profile_type)}</dd>
        <dt>Name</dt><dd>${escapeHtml([item.first_name, item.last_name].filter(Boolean).join(" "))}</dd>
        <dt>Phone</dt><dd>${escapeHtml(item.contact_phone)}</dd>
        <dt>Artist bio</dt><dd>${escapeHtml(item.artist_bio)}</dd>
        <dt>Additional info</dt><dd>${escapeHtml(item.additional_info)}</dd>
      </dl>
      <form data-decision-form>
        <label>Decision
          <select name="decision"><option value="approved">Approve</option><option value="denied">Deny</option></select>
        </label>
        <label>Denial reason <textarea name="reason"></textarea></label>
        <label><input type="checkbox" name="include_edit_link" checked> Include a fresh edit link when denied</label>
        <button type="submit">Record decision</button>
        <p role="status" data-decision-status></p>
      </form>`;
    node.querySelector("[data-decision-form]")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const statusNode = node.querySelector("[data-decision-status]");
      statusNode.textContent = "Saving decision…";
      try {
        const result = await api(`/api/v1/admin/profiles/submissions/${draftId}/decisions`, {
          method: "POST",
          body: JSON.stringify({
            decision: form.get("decision"),
            reason: form.get("reason"),
            include_edit_link: form.get("include_edit_link") === "on",
          }),
        });
        statusNode.textContent = `Submission ${result.decision}.`;
        event.currentTarget.querySelectorAll("button, input, select, textarea").forEach((field) => {
          field.disabled = true;
        });
      } catch (error) {
        statusNode.textContent = error.message;
        statusNode.classList.add("is-error");
      }
    });
  }

  const loaders = [
    ["[data-admin-dashboard]", loadDashboard],
    ["[data-admin-events]", loadEvents],
    ["[data-admin-lineup]", loadLineup],
    ["[data-admin-standby]", loadStandby],
    ["[data-admin-profiles]", loadProfiles],
    ["[data-admin-submission]", loadSubmission],
  ];
  loaders.forEach(([selector, loader]) => {
    const node = document.querySelector(selector);
    if (node) loader(node).catch((error) => {
      node.innerHTML = `<p class="is-error">${escapeHtml(error.message)}</p>`;
    });
  });
}());
