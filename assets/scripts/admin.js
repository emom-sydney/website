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

  function lineupEligibilityMessage(item) {
    const needsApproval = !item.is_profile_approved;
    const needsConfirmation = item.availability_status !== "availability_confirmed";

    if (needsApproval && needsConfirmation) {
      return "Awaiting profile approval and availability confirmation";
    }
    if (needsApproval) return "Awaiting profile approval";
    return "Awaiting availability confirmation";
  }

  function formatAvailabilityEmailSent(epoch) {
    const sentAt = new Date(Number(epoch));
    if (Number.isNaN(sentAt.getTime())) return "";
    const day = String(sentAt.getDate()).padStart(2, "0");
    const month = String(sentAt.getMonth() + 1).padStart(2, "0");
    const hours = String(sentAt.getHours()).padStart(2, "0");
    const minutes = String(sentAt.getMinutes()).padStart(2, "0");
    const elapsedHours = Math.max(0, Math.floor((Date.now() - sentAt.getTime()) / 3600000));
    return `${day}/${month} ${hours}:${minutes} (${elapsedHours} hours ago)`;
  }

  function socialLinkUrl(link) {
    const profileName = String(link.profile_name || "").trim();
    const urlFormat = String(link.url_format || "").trim();
    const href = urlFormat
      ? urlFormat.replaceAll("{profileName}", profileName)
      : profileName;

    try {
      const url = new URL(href);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch {
      return "";
    }
  }

  function renderSocialLinks(socialLinks) {
    if (!Array.isArray(socialLinks) || !socialLinks.length) return "<small>None</small>";

    return `<ul class="admin-social-links">${socialLinks.map((link) => {
      const label = link.platform_name || link.profile_name || "Social profile";
      const href = socialLinkUrl(link);
      return href
        ? `<li><a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a></li>`
        : `<li>${escapeHtml(label)}</li>`;
    }).join("")}</ul>`;
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
      window.showToast?.(error.message, { kind: "error" });
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
            <h2>${escapeHtml(event.type_description)}: ${escapeHtml(event.event_name)}</h2>
            <p>${escapeHtml(event.event_date)}</p>
            <p>${escapeHtml(event.event_description)}</p>
            <div class="admin-actions">
              ${session.is_admin ? `<a href="/admin/events/${event.event_id}/edit/">Edit event</a>
              <a href="/admin/events/${event.event_id}/lineup/">Edit lineup</a>` : ""}
              <a href="/admin/events/${event.event_id}/standby/">Standby performers</a>
            </div>
          </article>`).join("")}</div>`
      : "<p>No upcoming Open Mic events.</p>";
  }

  async function loadEventEdit(node) {
    const eventId = node.dataset.eventId ? Number(node.dataset.eventId) : null;
    const [event, typeData] = await Promise.all([
      eventId
        ? api(`/api/v1/admin/events/${eventId}`)
        : Promise.resolve({ event_date: "", type_id: 1, event_name: "", event_description: "" }),
      api("/api/v1/admin/event-types"),
    ]);
    node.innerHTML = `
      <form data-event-edit-form>
        <label>Event date <input name="event_date" type="date" required value="${escapeHtml(event.event_date)}"></label>
        <label>Event type <select name="type_id">
          ${typeData.event_types.map((type) => `<option value="${type.id}"${event.type_id === type.id ? " selected" : ""}>${escapeHtml(type.description)}</option>`).join("")}
        </select></label>
        <label>Event name <input name="event_name" required value="${escapeHtml(event.event_name)}"></label>
        <label>Event description <textarea name="event_description" rows="6">${escapeHtml(event.event_description)}</textarea></label>
        <button type="submit">Save and close</button>
      </form>`;
    node.querySelector("[data-event-edit-form]").addEventListener("submit", async (submitEvent) => {
      submitEvent.preventDefault();
      const form = new FormData(submitEvent.currentTarget);
      try {
        await api(eventId ? `/api/v1/admin/events/${eventId}` : "/api/v1/admin/events", {
          method: eventId ? "PUT" : "POST",
          body: JSON.stringify(Object.fromEntries(form)),
        });
        window.location.assign("/admin/events/");
      } catch (error) {
        window.showToast?.(error.message, { kind: "error" });
      }
    });
  }

  async function loadLineup(node) {
    const eventId = Number(node.dataset.eventId);
    const eventDetails = await api(`/api/v1/admin/events/${eventId}`);
    if (eventDetails.type_id === 2) {
      let performers = eventDetails.performers || [];
      node.innerHTML = `<h2>${escapeHtml(eventDetails.event_name)} — performers</h2>
        <label>Find performer <input data-performer-search autocomplete="off"></label>
        <div data-performer-suggestions></div>
        <table><thead><tr><th>#</th><th>Name</th><th>Email</th><th>Mobile</th><th>Actions</th></tr></thead>
        <tbody data-performer-list></tbody></table>
        <button type="button" data-save-performers>Save lineup</button>`;
      const listNode = node.querySelector("[data-performer-list]");
      const suggestionsNode = node.querySelector("[data-performer-suggestions]");
      const render = () => { listNode.innerHTML = performers.map((item, index) => `<tr>
        <td>${index + 1}</td><td>${escapeHtml(item.display_name)}</td>
        <td>${item.email ? `<a href="mailto:${escapeHtml(item.email)}">${escapeHtml(item.email)}</a>` : ""}</td>
        <td>${escapeHtml(item.contact_phone)}</td><td>
        <button type="button" data-up="${index}"${index ? "" : " disabled"}>Up</button>
        <button type="button" data-down="${index}"${index === performers.length - 1 ? " disabled" : ""}>Down</button>
        <button type="button" data-remove="${index}">Remove</button></td></tr>`).join(""); };
      render();
      node.addEventListener("click", (clickEvent) => {
        const button = clickEvent.target.closest("button");
        if (!button) return;
        const index = Number(button.dataset.up ?? button.dataset.down ?? button.dataset.remove);
        if (button.dataset.up !== undefined && index > 0) [performers[index - 1], performers[index]] = [performers[index], performers[index - 1]];
        if (button.dataset.down !== undefined && index < performers.length - 1) [performers[index], performers[index + 1]] = [performers[index + 1], performers[index]];
        if (button.dataset.remove !== undefined) performers.splice(index, 1);
        if (button.dataset.up !== undefined || button.dataset.down !== undefined || button.dataset.remove !== undefined) render();
      });
      node.querySelector("[data-performer-search]").addEventListener("input", async (inputEvent) => {
        const query = inputEvent.target.value.trim();
        if (query.length < 2) { suggestionsNode.innerHTML = ""; return; }
        try {
          const result = await api(`/api/v1/admin/profiles/search?q=${encodeURIComponent(query)}`);
          suggestionsNode.innerHTML = result.profiles.map((item, index) => `<button type="button" data-suggestion="${index}">${escapeHtml(item.display_name)}${item.email ? ` — ${escapeHtml(item.email)}` : ""}</button>`).join("");
          suggestionsNode.querySelectorAll("[data-suggestion]").forEach((button) => button.addEventListener("click", () => {
            const item = result.profiles[Number(button.dataset.suggestion)];
            if (!performers.some((performer) => performer.profile_id === item.profile_id)) performers.push(item);
            render(); inputEvent.target.value = ""; suggestionsNode.innerHTML = "";
          }));
        } catch (error) { window.showToast?.(error.message, { kind: "error" }); }
      });
      node.querySelector("[data-save-performers]").addEventListener("click", async () => {
        try {
          await api(`/api/v1/admin/events/${eventId}/performers`, { method: "PUT", body: JSON.stringify({ profile_ids: performers.map((item) => item.profile_id) }) });
          window.location.assign("/admin/events/");
        } catch (error) { window.showToast?.(error.message, { kind: "error" }); }
      });
      return;
    }
    await api(`/api/v1/admin/events/${eventId}/lineup/lock`, { method: "POST" });
    const data = await api(`/api/v1/admin/events/${eventId}/lineup`);
    node.innerHTML = `
      <h2>${escapeHtml(data.event.event_name)} — ${escapeHtml(data.event.event_date)}</h2>
      <p><span data-interest-count>${data.candidates.length}</span> performers have expressed interest in this date.</p>
      <form data-lineup-form>
        <div class="admin-table-wrap"><table>
          <thead><tr><th>Performer</th><th>Social media</th><th>Availability</th><th>Status</th><th>Reminder</th></tr></thead>
          <tbody>${data.candidates.map((item) => `
            <tr>
              <td>${escapeHtml(item.display_name)}<br><small>${escapeHtml(item.email)}</small></td>
              <td>${renderSocialLinks(item.social_links)}</td>
              <td>${escapeHtml(item.availability_status)}</td>
              <td>
                ${item.availability_status === "availability_cancelled"
                  ? ""
                  : item.availability_status === "availability_confirmed" && item.is_profile_approved
                  ? `<select name="status_${item.requested_date_id}">
                      ${["standby", "selected", "reserve"].map((value) =>
                        `<option value="${value}"${item.selection_status === value ? " selected" : ""}>${value}</option>`
                      ).join("")}
                    </select>`
                  : item.availability_email_sent_at_epoch
                  ? `<small>Availability confirmation sent ${escapeHtml(formatAvailabilityEmailSent(item.availability_email_sent_at_epoch))}</small>`
                  : `<small>${lineupEligibilityMessage(item)}</small>`}
              </td>
              <td><button type="button" data-reminder-id="${item.requested_date_id}" data-reminder-kind="${item.availability_status === "availability_cancelled" ? "remove" : item.availability_status === "availability_confirmed" && item.is_profile_approved ? "lineup-status" : "availability"}">${item.availability_status === "availability_cancelled" ? "Remove" : "Send"}</button></td>
            </tr>`).join("")}</tbody>
        </table></div>
        <button type="submit">Save lineup</button>
        <p role="status" data-lineup-status></p>
      </form>`;

    node.querySelectorAll("[data-reminder-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          if (button.dataset.reminderKind === "remove") {
            try {
              const result = await api(
                `/api/v1/admin/events/${eventId}/performer-requests/${button.dataset.reminderId}`,
                { method: "DELETE" }
              );
              button.closest("tr")?.remove();
              const countNode = node.querySelector("[data-interest-count]");
              if (countNode) countNode.textContent = String(Math.max(0, Number(countNode.textContent) - 1));
              window.showToast?.(result.message, { kind: "success" });
            } catch (error) {
              window.showToast?.(error.message, { kind: "error" });
            } finally {
              button.disabled = false;
            }
            return;
          }
          const path = button.dataset.reminderKind === "lineup-status"
            ? `/api/v1/admin/events/${eventId}/performer-requests/${button.dataset.reminderId}/lineup-status-notifications`
            : `/api/v1/admin/events/${eventId}/performer-requests/${button.dataset.reminderId}/availability-reminders`;
          const body = button.dataset.reminderKind === "lineup-status"
            ? { status: button.closest("tr")?.querySelector("select")?.value }
            : undefined;
          const result = await api(path, {
            method: "POST",
            ...(body ? { body: JSON.stringify(body) } : {}),
          });
          if (button.dataset.reminderKind === "availability" && result.availability_email_sent_at_epoch) {
            const statusCell = button.closest("tr")?.children[3];
            if (statusCell) {
              statusCell.innerHTML = `<small>Availability confirmation sent ${escapeHtml(formatAvailabilityEmailSent(result.availability_email_sent_at_epoch))}</small>`;
            }
          }
          window.showToast?.(result.message, { kind: "success" });
        } catch (error) {
          window.showToast?.(error.message, { kind: "error" });
        } finally {
          button.disabled = false;
        }
      });
    });

    node.querySelector("[data-lineup-form]")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const statuses = {};
      new FormData(form).forEach((value, key) => {
        if (key.startsWith("status_")) statuses[key.slice(7)] = value;
      });
      try {
        const preview = await api(`/api/v1/admin/events/${eventId}/lineup/preview`, {
          method: "POST",
          body: JSON.stringify({ statuses }),
        });
        const confirmation = document.createElement("div");
        confirmation.innerHTML = `<h3>Continue and notify</h3>
          <p>The following performers will be notified:</p>
          ${preview.recipients.length ? `<ul>${preview.recipients.map((item) => `<li>${escapeHtml(item.display_name)} — ${escapeHtml(item.email)}</li>`).join("")}</ul>` : "<p>No new selection notifications will be sent.</p>"}
          <button type="button" data-confirm-lineup>Continue</button>
          <button type="button" data-cancel-lineup>Cancel</button>
          <button type="button" data-exit-lineup>Exit without saving</button>`;
        form.replaceWith(confirmation);
        confirmation.querySelector("[data-cancel-lineup]").addEventListener("click", () => confirmation.replaceWith(form));
        confirmation.querySelector("[data-exit-lineup]").addEventListener("click", () => {
          window.location.assign("/admin/events/");
        });
        confirmation.querySelector("[data-confirm-lineup]").addEventListener("click", async () => {
          try {
            const result = await api(`/api/v1/admin/events/${eventId}/lineup`, {
              method: "PUT",
              body: JSON.stringify({ statuses }),
            });
            window.showToast?.(result.message, { kind: "success" });
            confirmation.replaceWith(form);
          } catch (error) {
            window.showToast?.(error.message, { kind: "error" });
          }
        });
      } catch (error) {
        window.showToast?.(error.message, { kind: "error" });
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
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
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
        formElement.querySelectorAll("button, input, select, textarea").forEach((field) => {
          field.disabled = true;
        });
      } catch (error) {
        statusNode.textContent = "";
        window.showToast?.(error.message, { kind: "error" });
      }
    });
  }

  const loaders = [
    ["[data-admin-dashboard]", loadDashboard],
    ["[data-admin-events]", loadEvents],
    ["[data-admin-event-edit]", loadEventEdit],
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
