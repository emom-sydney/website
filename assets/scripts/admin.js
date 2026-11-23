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
    return `${day}/${month} ${hours}:${minutes} (${elapsedHours}h ago)`;
  }

  function lineupStatusLabel(status) {
    return {
      requested: "Requested",
      availability_confirmed: "Availability confirmed",
      selected: "Selected",
      standby: "Standby",
      reserve: "Reserve",
      cancelled: "Cancelled",
      declined: "Declined",
    }[status] || status;
  }

  function lineupEffectiveStatus(item) {
    return item.selection_status || item.availability_status || "requested";
  }

  function lineupMessage(status, item, event) {
    const greeting = `Hi ${item.first_name || item.display_name},\n\n`;
    if (status === "requested") {
      return `${greeting}This is an automated message. You previously registered interest in playing at ${event.event_name} on ${event.event_date}, and we're just checking in that you're still available before we make a final lineup selection later this week. Thanks!`;
    }
    if (status === "selected") {
      return `${greeting}Yay! Your appearance at ${event.event_name} on ${event.event_date} has been confirmed.\nPlease see our FAQ for everything you need to know: https://sydney.emom.me/perform/faq\nAnd feel free to email us with any further questions: admin@sydney.emom.me`;
    }
    if (status === "standby") {
      return `${greeting}You have not been selected to perform at ${event.event_name} on ${event.event_date}, but you are on standby. You are number ${item.queue_position} in the queue in case someone drops out.`;
    }
    return `${greeting}You have not been selected to perform at ${event.event_name} on ${event.event_date} because you have played recently, but we may still call on you if we need to make up numbers.`;
  }

  function editAndConfirmEmail(message, title = "Confirm email") {
    return new Promise((resolve) => {
      const dialog = document.createElement("dialog");
      dialog.className = "admin-email-dialog";
      dialog.innerHTML = `<form method="dialog">
        <h2>${escapeHtml(title)}</h2>
        <label>Message <textarea data-email-message rows="8"></textarea></label>
        <div><button type="button" data-email-cancel>Cancel</button><button type="submit" data-email-confirm>Send email</button></div>
      </form>`;
      document.body.appendChild(dialog);
      dialog.querySelector("[data-email-message]").value = message;
      const finish = (value) => {
        dialog.close();
        dialog.remove();
        resolve(value);
      };
      dialog.querySelector("[data-email-cancel]").addEventListener("click", () => finish(null));
      dialog.querySelector("form").addEventListener("submit", (event) => {
        event.preventDefault();
        finish(dialog.querySelector("[data-email-message]").value.trim());
      });
      dialog.addEventListener("cancel", () => finish(null), { once: true });
      dialog.showModal();
    });
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

  function renderInfoLinks(item) {
    const links = [];
    if (String(item.artist_bio || "").trim()) {
      links.push(`<li><a href="#" class="admin-info-trigger" data-info-title="Bio" data-info-content="${escapeHtml(item.artist_bio)}">Bio</a></li>`);
    }
    if (String(item.additional_info || "").trim()) {
      links.push(`<li><a href="#" class="admin-info-trigger" data-info-title="More" data-info-content="${escapeHtml(item.additional_info)}">More</a></li>`);
    }
    return links.length ? `<ul class="admin-social-links">${links.join("")}</ul>` : "";
  }

  let infoTooltip = null;
  let infoTooltipHideTimer = null;
  let infoTooltipTrigger = null;

  function getInfoTooltip() {
    if (infoTooltip) return infoTooltip;
    infoTooltip = document.createElement("div");
    infoTooltip.className = "admin-info-tooltip";
    infoTooltip.setAttribute("role", "tooltip");
    document.body.append(infoTooltip);
    infoTooltip.addEventListener("mouseenter", () => clearTimeout(infoTooltipHideTimer));
    infoTooltip.addEventListener("mouseleave", hideInfoTooltip);
    return infoTooltip;
  }

  function positionInfoTooltip(trigger) {
    const tooltip = getInfoTooltip();
    const rect = trigger.getBoundingClientRect();
    const gap = 8;
    const maxLeft = window.innerWidth - tooltip.offsetWidth - gap;
    const left = Math.min(Math.max(gap, rect.left), Math.max(gap, maxLeft));
    const top = Math.min(rect.bottom + gap, window.innerHeight - tooltip.offsetHeight - gap);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(gap, top)}px`;
  }

  function showInfoTooltip(trigger) {
    clearTimeout(infoTooltipHideTimer);
    const tooltip = getInfoTooltip();
    infoTooltipTrigger = trigger;
    tooltip.innerHTML = `<strong>${escapeHtml(trigger.dataset.infoTitle || "Info")}</strong><div>${escapeHtml(trigger.dataset.infoContent || "")}</div>`;
    tooltip.classList.add("is-visible");
    positionInfoTooltip(trigger);
  }

  function hideInfoTooltip() {
    clearTimeout(infoTooltipHideTimer);
    infoTooltipHideTimer = window.setTimeout(() => {
      infoTooltip?.classList.remove("is-visible");
      infoTooltipTrigger = null;
    }, 120);
  }

  function setupInfoTooltips(node) {
    node.querySelectorAll(".admin-info-trigger").forEach((trigger) => {
      trigger.addEventListener("mouseenter", () => {
        clearTimeout(infoTooltipHideTimer);
        infoTooltipHideTimer = window.setTimeout(() => showInfoTooltip(trigger), 350);
      });
      trigger.addEventListener("mouseleave", hideInfoTooltip);
      trigger.addEventListener("focus", () => showInfoTooltip(trigger));
      trigger.addEventListener("blur", hideInfoTooltip);
      trigger.addEventListener("click", (event) => {
        event.preventDefault();
        if (infoTooltipTrigger === trigger && infoTooltip?.classList.contains("is-visible")) {
          hideInfoTooltip();
        } else {
          showInfoTooltip(trigger);
        }
      });
    });
  }

  function setupSortableTable(table) {
    const headers = Array.from(table.querySelectorAll("thead th"));
    const body = table.tBodies[0];
    if (!body) return;

    headers.forEach((header, columnIndex) => {
      if (header.dataset.sortable === "false") return;
      const label = header.textContent.trim();
      header.dataset.sortColumn = String(columnIndex);
      const labels = header.dataset.sortLabels?.split(",") || [label];
      const keys = header.dataset.sortKeys?.split(",") || [""];
      header.innerHTML = labels.map((sortLabel, index) => `<button type="button" class="admin-table-sort" aria-label="Sort by ${escapeHtml(sortLabel.trim())}" aria-sort="none" data-sort-direction="none" data-sort-key="${escapeHtml(keys[index]?.trim() || "")}">${escapeHtml(sortLabel.trim())}<span aria-hidden="true"></span></button>`).join(" ");
    });

    table.addEventListener("click", (event) => {
      const button = event.target.closest(".admin-table-sort");
      if (!button || !table.contains(button)) return;
      const header = button.closest("th");
      const columnIndex = Number(header.dataset.sortColumn);
      const descending = button.dataset.sortDirection === "ascending";
      headers.forEach((otherHeader) => {
        otherHeader.querySelectorAll(".admin-table-sort").forEach((otherButton) => {
          otherButton.dataset.sortDirection = "none";
          otherButton.setAttribute("aria-sort", "none");
        });
      });
      button.dataset.sortDirection = descending ? "descending" : "ascending";
      button.setAttribute("aria-sort", button.dataset.sortDirection);

      const rows = Array.from(body.rows);
      rows.sort((left, right) => {
        const sortKey = button.dataset.sortKey;
        const leftCell = left.cells[columnIndex];
        const rightCell = right.cells[columnIndex];
        const leftText = sortKey ? leftCell?.dataset[sortKey] || "" : leftCell?.dataset.sortValue || leftCell?.textContent.trim() || "";
        const rightText = sortKey ? rightCell?.dataset[sortKey] || "" : rightCell?.dataset.sortValue || rightCell?.textContent.trim() || "";
        const result = leftText.localeCompare(rightText, undefined, { numeric: true, sensitivity: "base" });
        return descending ? -result : result;
      });
      body.append(...rows);
    });
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

  document.querySelector("[data-admin-passkey-login]")?.addEventListener("click", async () => {
    if (!window.PublicKeyCredential || !navigator.credentials) {
      status("Passkeys are not supported by this browser. Use the email login instead.", true);
      return;
    }
    const button = document.querySelector("[data-admin-passkey-login]");
    button.disabled = true;
    try {
      const next = document.querySelector("[data-admin-login] input[name=next]")?.value || "/admin/";
      const optionsResponse = await fetch("/api/v1/admin/passkeys/login/options", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ next }) });
      const optionsPayload = await optionsResponse.json();
      if (!optionsResponse.ok) throw new Error(optionsPayload?.error?.message || "Unable to start passkey login.");
      const options = optionsPayload.data;
      options.challenge = decodeBase64Url(options.challenge);
      const credential = await navigator.credentials.get({ publicKey: options });
      const response = await fetch("/api/v1/admin/passkeys/login/verify", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential: credentialToJson(credential), next }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload?.error?.message || "Passkey verification failed.");
      }
      window.location.assign(response.url || next);
    } catch (error) {
      status(error.name === "NotAllowedError" ? "Passkey login was cancelled." : error.message, true);
      button.disabled = false;
    }
  });

  function decodeBase64Url(value) {
    const padded = value.replaceAll("-", "+").replaceAll("_", "/") + "===";
    const binary = atob(padded.slice(0, padded.length - (padded.length % 4)));
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  }

  function encodeBase64Url(value) {
    return btoa(String.fromCharCode(...new Uint8Array(value))).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  }

  function credentialToJson(credential) {
    const response = credential.response;
    const result = { id: credential.id, rawId: encodeBase64Url(credential.rawId), type: credential.type, response: {} };
    if (response.clientDataJSON) result.response.clientDataJSON = encodeBase64Url(response.clientDataJSON);
    if (response.authenticatorData) result.response.authenticatorData = encodeBase64Url(response.authenticatorData);
    if (response.signature) result.response.signature = encodeBase64Url(response.signature);
    if (response.userHandle) result.response.userHandle = encodeBase64Url(response.userHandle);
    if (response.attestationObject) result.response.attestationObject = encodeBase64Url(response.attestationObject);
    return result;
  }

  document.querySelector("[data-admin-logout]")?.addEventListener("click", async () => {
    try {
      await api("/api/v1/admin/session", { method: "DELETE" });
      window.location.assign("/admin/login/");
    } catch (error) {
      window.showToast?.(error.message, { kind: "error" });
    }
  });

  document.querySelector("[data-admin-passkey-register]")?.addEventListener("click", async () => {
    try {
      const options = await api("/api/v1/admin/passkeys/registration/options", { method: "POST", body: "{}" });
      options.challenge = decodeBase64Url(options.challenge);
      options.user.id = decodeBase64Url(options.user.id);
      const credential = await navigator.credentials.create({ publicKey: options });
      await api("/api/v1/admin/passkeys/registration/verify", {
        method: "POST",
        body: JSON.stringify({ credential: credentialToJson(credential), label: "Passkey" }),
      });
      window.showToast?.("Passkey registered.");
    } catch (error) {
      window.showToast?.(error.message, { kind: "error" });
    }
  });

  async function loadDashboard(node) {
    const data = await api("/api/v1/admin/dashboard");
    const eventCounts = (data.event_counts || [])
      .map((eventType) => `${eventType.count} ${escapeHtml(eventType.type_description)}`)
      .join(", ");
    node.innerHTML = `
      <a class="admin-summary-card" href="/admin/profiles/">
        <strong>${data.pending_profile_submissions}</strong>
        <span>pending profile submissions</span>
      </a>
      <a class="admin-summary-card" href="/admin/events/">
        <strong>${data.upcoming_events}</strong>
        <span>upcoming events</span>
        <small>(${eventCounts})</small>
      </a>`;
  }

  async function loadEvents(node) {
    const [data, session] = await Promise.all([
      api("/api/v1/admin/events"),
      api("/api/v1/admin/session"),
    ]);
    node.innerHTML = data.events.length
      ? `<div class="admin-list">${data.events.map((event) => `
          <article class="admin-event-card">
            <h2>${escapeHtml(event.type_description)}: ${escapeHtml(event.event_name)}</h2>
            <p>${escapeHtml(event.event_date)}${event.location_name ? ` · ${escapeHtml(event.location_name)}` : ""}</p>
            <p>${escapeHtml(event.event_description)}</p>
            <div class="admin-actions">
              ${session.is_admin ? `<a href="/admin/events/${event.event_id}/edit/">Edit event</a>
              <a href="/admin/events/${event.event_id}/lineup/">Edit lineup</a>` : ""}
              <a href="/admin/events/${event.event_id}/standby/">Standby performers</a>
            </div>
            ${session.is_admin && event.can_delete ? `<button type="button" class="admin-event-delete" data-delete-event="${event.event_id}" aria-label="Delete ${escapeHtml(event.event_name)}" title="Delete event">&#128465;</button>` : ""}
          </article>`).join("")}</div>`
      : "<p>No upcoming Open Mic events.</p>";
    node.querySelectorAll("[data-delete-event]").forEach((button) => button.addEventListener("click", async () => {
      const eventName = button.getAttribute("aria-label").replace(/^Delete /, "");
      if (!window.confirm(`Delete ${eventName}? This cannot be undone.`)) return;
      try {
        await api(`/api/v1/admin/events/${button.dataset.deleteEvent}`, { method: "DELETE" });
        await loadEvents(node);
      } catch (error) { window.showToast?.(error.message, { kind: "error" }); }
    }));
  }

  async function loadLocations(node) {
    const data = await api("/api/v1/admin/locations");
    const renderRows = () => data.locations.map((location) => `
      <tr data-location-id="${location.id}">
        <td><input name="name" value="${escapeHtml(location.name)}" required></td>
        <td><input name="address" value="${escapeHtml(location.address)}"></td>
        <td><button type="button" data-save-location>Save</button> <button type="button" data-delete-location>Delete</button></td>
      </tr>`).join("");
    node.innerHTML = `
      <form data-new-location>
        <h2>Add location</h2>
        <label>Name <input name="name" required></label>
        <label>Address <input name="address"></label>
        <button type="submit">Add location</button>
      </form>
      <h2>Existing locations</h2>
      ${data.locations.length ? `<div class="admin-table-wrap"><table><thead><tr><th>Name</th><th>Address</th><th>Actions</th></tr></thead><tbody>${renderRows()}</tbody></table></div>` : "<p>No locations have been added yet.</p>"}`;

    node.querySelector("[data-new-location]")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      try {
        await api("/api/v1/admin/locations", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
        await loadLocations(node);
      } catch (error) { window.showToast?.(error.message, { kind: "error" }); }
    });
    node.querySelectorAll("[data-save-location]").forEach((button) => button.addEventListener("click", async () => {
      const row = button.closest("tr");
      try {
        await api(`/api/v1/admin/locations/${row.dataset.locationId}`, { method: "PUT", body: JSON.stringify({ name: row.querySelector('[name="name"]').value, address: row.querySelector('[name="address"]').value }) });
        window.showToast?.("Location saved.");
      } catch (error) { window.showToast?.(error.message, { kind: "error" }); }
    }));
    node.querySelectorAll("[data-delete-location]").forEach((button) => button.addEventListener("click", async () => {
      const row = button.closest("tr");
      if (!window.confirm("Delete this location?")) return;
      try {
        await api(`/api/v1/admin/locations/${row.dataset.locationId}`, { method: "DELETE" });
        await loadLocations(node);
      } catch (error) { window.showToast?.(error.message, { kind: "error" }); }
    }));
  }

  async function loadEventEdit(node) {
    const eventId = node.dataset.eventId ? Number(node.dataset.eventId) : null;
    const [event, typeData, locationData] = await Promise.all([
      eventId
        ? api(`/api/v1/admin/events/${eventId}`)
        : Promise.resolve({ event_date: "", type_id: 1, event_name: "", event_description: "", performance_slots: 7, starts_at: "", ends_at: "", timezone: "Australia/Sydney", location_id: null }),
      api("/api/v1/admin/event-types"),
      api("/api/v1/admin/locations"),
    ]);
    node.innerHTML = `
      <form data-event-edit-form>
        <div class="admin-event-edit__row">
          <label class="admin-event-edit__name">Event name <input name="event_name" required value="${escapeHtml(event.event_name)}"></label>
          <label class="admin-event-edit__compact">Event date <input name="event_date" type="date" required value="${escapeHtml(event.event_date)}"></label>
        </div>
        <div class="admin-event-edit__row">
          <label class="admin-event-edit__compact">Event type <select name="type_id">
            ${typeData.event_types.map((type) => `<option value="${type.id}"${event.type_id === type.id ? " selected" : ""}>${escapeHtml(type.description)}</option>`).join("")}
          </select></label>
          <label class="admin-event-edit__compact">Performance slots <input name="performance_slots" type="number" min="1" step="1" required value="${escapeHtml(event.performance_slots)}"></label>
        </div>
        <div class="admin-event-edit__row">
          <label>Starts at <input name="starts_at" type="datetime-local" value="${escapeHtml(event.starts_at ? event.starts_at.slice(0, 16) : "")}"></label>
          <label>Ends at <input name="ends_at" type="datetime-local" value="${escapeHtml(event.ends_at ? event.ends_at.slice(0, 16) : "")}"></label>
        </div>
        <div class="admin-event-edit__row">
          <label>Timezone <input name="timezone" value="${escapeHtml(event.timezone || "Australia/Sydney")}"></label>
          <label>Location <select name="location_id"><option value="">No location</option>${locationData.locations.map((location) => `<option value="${location.id}"${String(event.location_id) === String(location.id) ? " selected" : ""}>${escapeHtml(location.name)}${location.address ? ` — ${escapeHtml(location.address)}` : ""}</option>`).join("")}</select></label>
        </div>
        <label class="admin-event-edit__description">Event description <textarea name="event_description" rows="6">${escapeHtml(event.event_description)}</textarea></label>
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

  async function loadLineup(node, restoreSelectedIds = []) {
    const eventId = Number(node.dataset.eventId);
    const eventDetails = await api(`/api/v1/admin/events/${eventId}`);
    if (eventDetails.type_id === 2) {
      let performers = eventDetails.performers || [];
      node.innerHTML = `<h2>${escapeHtml(eventDetails.event_name)} — performers</h2>
        <p><button type="button" class="admin-add-performer-button" data-show-performer-search>Find performer</button></p>
        <div data-performer-search-panel hidden>
          <label>Performer name <input data-performer-search autocomplete="off"></label>
          <div data-performer-suggestions></div>
        </div>
        <table><thead><tr><th>#</th><th>Name</th><th>Email</th><th>Mobile</th><th>Actions</th></tr></thead>
        <tbody data-performer-list></tbody></table>
        <button type="button" data-save-performers>Save lineup</button>`;
      const listNode = node.querySelector("[data-performer-list]");
      const suggestionsNode = node.querySelector("[data-performer-suggestions]");
      const searchPanel = node.querySelector("[data-performer-search-panel]");
      node.querySelector("[data-show-performer-search]").addEventListener("click", () => {
        searchPanel.hidden = !searchPanel.hidden;
        if (!searchPanel.hidden) node.querySelector("[data-performer-search]").focus();
      });
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
    const newFaceCount = data.candidates.filter((item) => Number(item.played_count) === 0).length;
    const frequentNewFaceCount = data.candidates.filter(
      (item) => Number(item.played_count) === 0 && Number(item.request_count) >= 3,
    ).length;
    const frequentNewFaceNote = frequentNewFaceCount > 0
      ? ` ${frequentNewFaceCount} of those have requested to play more than twice already.`
      : "";
    function renderLineupStatusCell(item) {
      const status = item.availability_status === "availability_cancelled" ? "cancelled" : lineupEffectiveStatus(item);
      const label = status === "cancelled" ? "Cancelled" : lineupStatusLabel(status);
      let extra = "";
      if (item.availability_email_sent_at_epoch) {
        const when = formatAvailabilityEmailSent(item.availability_email_sent_at_epoch);
        if (when) extra = `<br><small class="admin-last-sent">Reminder sent ${escapeHtml(when)}</small>`;
      }
      return `<td data-status-cell data-sort-value="${escapeHtml(status)}">${escapeHtml(label)}${extra}</td>`;
    }

    const lineupColumns = [
      { id: "select", sortable: false, header: () => `<th data-sortable="false" class="admin-select-cell"><input type="checkbox" data-select-all aria-label="Select all performers"></th>`, cell: (item) => `<td class="admin-select-cell"><input type="checkbox" data-select-row="${item.requested_date_id}" aria-label="Select ${escapeHtml(item.display_name)}"></td>` },
      { id: "performer", label: "Performer", sortable: true, cell: (item) => `<td>${escapeHtml(item.display_name)}<br><small><a class="admin-email-link" href="mailto:${escapeHtml(item.email)}">${escapeHtml(item.email)}</a></small></td>` },
      { id: "info", label: "Info", sortable: false, cell: (item) => `<td>${renderInfoLinks(item)}</td>` },
      { id: "social", label: "Social media", sortable: false, cell: (item) => `<td>${renderSocialLinks(item.social_links)}</td>` },
      { id: "reqplayed", label: "Req / Played", sortable: true, sortLabels: "Req,Played", sortKeys: "requestCount,playedCount", cell: (item) => `<td data-request-count="${escapeHtml(item.request_count)}" data-played-count="${escapeHtml(item.played_count)}">${escapeHtml(item.request_count)} / ${escapeHtml(item.played_count)}</td>` },
      { id: "status", label: "Status", sortable: true, cell: renderLineupStatusCell },
    ];
    const lineupHeaderHtml = lineupColumns.map((col) => {
      if (col.header) return col.header();
      const attrs = [];
      if (col.sortable === false) attrs.push('data-sortable="false"');
      if (col.sortLabels) attrs.push(`data-sort-labels="${escapeHtml(col.sortLabels)}"`);
      if (col.sortKeys) attrs.push(`data-sort-keys="${escapeHtml(col.sortKeys)}"`);
      return `<th${attrs.length ? " " + attrs.join(" ") : ""}>${escapeHtml(col.label)}</th>`;
    }).join("");
    const lineupBodyHtml = data.candidates.map((item) => `<tr>${lineupColumns.map((col) => col.cell(item)).join("")}</tr>`).join("");

    node.innerHTML = `
      <h2>${escapeHtml(data.event.event_name)} — ${escapeHtml(data.event.event_date)}</h2>
      <p><span data-interest-count>${data.candidates.length}</span> performers have expressed interest in this date, ${newFaceCount} of whom haven't played before.${frequentNewFaceNote}</p>
      <div class="admin-lineup-container">
        <div class="admin-lineup-toolbar">
          <div class="admin-lineup-toolbar-left">
            <p><strong><span data-selected-slots>0</span>/${escapeHtml(data.event.performance_slots)} slots selected</strong></p>
            <p><button type="button" class="admin-add-performer-button" data-add-lineup-performer>Add performer</button></p>
            <div data-add-lineup-panel hidden>
              <label>Performer name <input type="search" data-lineup-performer-search autocomplete="off" minlength="2"></label>
              <div data-lineup-performer-suggestions></div>
            </div>
          </div>
          <div class="admin-lineup-toolbar-right">
            <div class="admin-actions-menu" data-actions-menu>
              <button type="button" class="admin-actions-toggle" data-actions-toggle disabled>Actions <span aria-hidden="true">▾</span></button>
              <ul class="admin-actions-list" data-actions-list hidden>
                <li class="admin-actions-group-label">Set status</li>
                <li><button type="button" data-action="set-status" data-status="selected" disabled>Selected</button></li>
                <li><button type="button" data-action="set-status" data-status="standby" disabled>Standby</button></li>
                <li><button type="button" data-action="set-status" data-status="reserve" disabled>Reserve</button></li>
                <li><button type="button" data-action="set-status" data-status="cancelled" disabled>Cancelled</button></li>
                <li><button type="button" data-action="set-status" data-status="declined" disabled>Declined</button></li>
                <li class="admin-actions-separator" aria-hidden="true"></li>
                <li><button type="button" data-action="send" disabled>Send email</button></li>
                <li><button type="button" data-action="remove" disabled>Remove from lineup</button></li>
              </ul>
            </div>
          </div>
        </div>
        <div class="admin-table-wrap"><table data-sortable-table>
          <thead><tr>${lineupHeaderHtml}</tr></thead>
          <tbody>${lineupBodyHtml}</tbody>
        </table></div>
        <p role="status" data-lineup-status></p>
      </div>`;

    setupSortableTable(node.querySelector("[data-sortable-table]"));
    setupInfoTooltips(node);

    const addPanel = node.querySelector("[data-add-lineup-panel]");
    const addSearch = node.querySelector("[data-lineup-performer-search]");
    const addSuggestions = node.querySelector("[data-lineup-performer-suggestions]");
    let addSearchTimer;
    node.querySelector("[data-add-lineup-performer]").addEventListener("click", () => {
      addPanel.hidden = !addPanel.hidden;
      if (!addPanel.hidden) addSearch.focus();
    });
    addSearch.addEventListener("input", () => {
      clearTimeout(addSearchTimer);
      const query = addSearch.value.trim();
      addSuggestions.innerHTML = "";
      if (query.length < 2) return;
      addSearchTimer = setTimeout(async () => {
        try {
          const result = await api(`/api/v1/admin/profiles/search?q=${encodeURIComponent(query)}`);
          addSuggestions.innerHTML = result.profiles.map((item, index) =>
            `<button type="button" data-add-suggestion="${index}">${escapeHtml(item.display_name)}${item.email ? ` — ${escapeHtml(item.email)}` : ""}</button>`
          ).join("");
          addSuggestions.querySelectorAll("[data-add-suggestion]").forEach((button) => button.addEventListener("click", async () => {
            const item = result.profiles[Number(button.dataset.addSuggestion)];
            button.disabled = true;
            try {
              await api(`/api/v1/admin/events/${eventId}/lineup/performers`, {
                method: "POST",
                body: JSON.stringify({ profile_id: item.profile_id }),
              });
              await loadLineup(node);
            } catch (error) {
              window.showToast?.(error.message, { kind: "error" });
              button.disabled = false;
            }
          }));
        } catch (error) { window.showToast?.(error.message, { kind: "error" }); }
      }, 250);
    });

    const performanceSlots = Number(data.event.performance_slots);

    function effectiveStatus(item) {
      return item.availability_status === "availability_cancelled" ? "cancelled" : lineupEffectiveStatus(item);
    }
    const EMAILABLE_STATUSES = new Set(["requested", "selected", "standby", "reserve"]);

    function itemForId(id) {
      return data.candidates.find((candidate) => candidate.requested_date_id === id) || null;
    }
    function rowStatus(row) {
      const cell = row?.querySelector("[data-status-cell]");
      return cell?.dataset.sortValue || "requested";
    }
    function selectedRows() {
      return [...node.querySelectorAll("input[data-select-row]:checked")]
        .map((checkbox) => checkbox.closest("tr"))
        .filter(Boolean);
    }
    function selectedIdSet() {
      return new Set(selectedRows().map((row) => Number(row.querySelector("input[data-select-row]").dataset.selectRow)));
    }
    function updateSelectAll() {
      const checkboxes = node.querySelectorAll("input[data-select-row]");
      const selectAll = node.querySelector("[data-select-all]");
      if (!selectAll) return;
      const checked = [...checkboxes].filter((cb) => cb.checked);
      selectAll.checked = checkboxes.length > 0 && checked.length === checkboxes.length;
      selectAll.indeterminate = checked.length > 0 && checked.length < checkboxes.length;
    }
    function updateSelectedSlotsCount() {
      const count = data.candidates.filter((candidate) => effectiveStatus(candidate) === "selected").length;
      const slotsNode = node.querySelector("[data-selected-slots]");
      if (slotsNode) slotsNode.textContent = String(count);
    }
    function updateActionsMenu() {
      const rows = selectedRows();
      const count = rows.length;
      const toggle = node.querySelector("[data-actions-toggle]");
      if (toggle) toggle.disabled = count === 0;
      const selectedIds = selectedIdSet();
      node.querySelectorAll('[data-action="set-status"]').forEach((button) => {
        const status = button.dataset.status;
        let disabled = count === 0;
        button.title = "";
        if (!disabled && status === "selected") {
          const prospective = data.candidates.filter((candidate) =>
            selectedIds.has(candidate.requested_date_id) ? true : effectiveStatus(candidate) === "selected"
          ).length;
          if (prospective > performanceSlots) {
            disabled = true;
            button.title = `Would exceed ${performanceSlots} selected slots`;
          }
        }
        button.disabled = disabled;
      });
      const removeButton = node.querySelector('[data-action="remove"]');
      if (removeButton) removeButton.disabled = count === 0;
      const sendButton = node.querySelector('[data-action="send"]');
      if (sendButton) {
        const statuses = new Set(rows.map(rowStatus));
        const uniform = statuses.size === 1;
        const status = uniform ? [...statuses][0] : null;
        const emailable = status && EMAILABLE_STATUSES.has(status);
        sendButton.disabled = count === 0 || !emailable;
        sendButton.textContent = count > 0 && emailable
          ? `Send "${lineupStatusLabel(status)}" message to ${count}`
          : "Send email";
      }
    }

    async function removeSelected() {
      const rows = selectedRows();
      if (!rows.length) return;
      if (!window.confirm(`Remove ${rows.length} performer${rows.length > 1 ? "s" : ""} from this lineup? This cannot be undone.`)) return;
      for (const row of [...rows]) {
        const id = Number(row.querySelector("input[data-select-row]").dataset.selectRow);
        try {
          await api(`/api/v1/admin/events/${eventId}/performer-requests/${id}`, { method: "DELETE" });
          row.remove();
        } catch (error) {
          window.showToast?.(error.message, { kind: "error" });
          break;
        }
      }
      const countNode = node.querySelector("[data-interest-count]");
      if (countNode) countNode.textContent = String(node.querySelectorAll("tbody tr").length);
      updateSelectAll();
      updateActionsMenu();
    }

    async function setSelectedStatus(status) {
      const rows = selectedRows();
      if (!rows.length) return;
      const selectedIds = selectedIdSet();
      const statuses = {};
      for (const candidate of data.candidates) {
        statuses[candidate.requested_date_id] = selectedIds.has(candidate.requested_date_id)
          ? status
          : effectiveStatus(candidate);
      }
      try {
        await api(`/api/v1/admin/events/${eventId}/lineup`, {
          method: "PUT",
          body: JSON.stringify({ statuses, notify: false }),
        });
        window.showToast?.(`Status set to "${lineupStatusLabel(status)}" for ${rows.length} performer${rows.length > 1 ? "s" : ""}.`, { kind: "success" });
        await loadLineup(node, [...selectedIds]);
      } catch (error) {
        window.showToast?.(error.message, { kind: "error" });
      }
    }

    async function sendSelected() {
      const rows = selectedRows();
      if (!rows.length) return;
      const statuses = new Set(rows.map(rowStatus));
      if (statuses.size !== 1) {
        window.showToast?.("Select performers with the same status to send an email.", { kind: "error" });
        return;
      }
      const status = [...statuses][0];
      if (!EMAILABLE_STATUSES.has(status)) {
        window.showToast?.(`Cannot send an email for the "${lineupStatusLabel(status)}" status.`, { kind: "error" });
        return;
      }
      const items = rows
        .map((row) => itemForId(Number(row.querySelector("input[data-select-row]").dataset.selectRow)))
        .filter(Boolean);
      if (!items.length) return;
      const message = await editAndConfirmEmail(
        lineupMessage(status, items[0], data.event),
        `${lineupStatusLabel(status)} message for ${items.length} performer${items.length > 1 ? "s" : ""}`,
      );
      if (message === null) return;
      const isAvailability = status === "requested";
      let sent = 0;
      for (const item of items) {
        const path = isAvailability
          ? `/api/v1/admin/events/${eventId}/performer-requests/${item.requested_date_id}/availability-reminders`
          : `/api/v1/admin/events/${eventId}/performer-requests/${item.requested_date_id}/lineup-status-notifications`;
        const body = isAvailability ? { message } : { status, message };
        try {
          const result = await api(path, { method: "POST", body: JSON.stringify(body) });
          if (isAvailability && result?.availability_email_sent_at_epoch) {
            item.availability_email_sent_at_epoch = result.availability_email_sent_at_epoch;
          }
          sent += 1;
        } catch (error) {
          window.showToast?.(error.message, { kind: "error" });
          break;
        }
      }
      if (sent) window.showToast?.(`Email sent to ${sent} performer${sent > 1 ? "s" : ""}.`, { kind: "success" });
      updateActionsMenu();
    }

    node.querySelectorAll("input[data-select-row]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        updateSelectAll();
        updateActionsMenu();
      });
    });
    node.querySelector("[data-select-all]")?.addEventListener("change", (event) => {
      const checked = event.currentTarget.checked;
      node.querySelectorAll("input[data-select-row]").forEach((checkbox) => {
        checkbox.checked = checked;
      });
      updateActionsMenu();
    });

    const actionsMenu = node.querySelector("[data-actions-menu]");
    const actionsToggle = node.querySelector("[data-actions-toggle]");
    const actionsList = node.querySelector("[data-actions-list]");
    if (actionsMenu && actionsToggle && actionsList) {
      actionsToggle.addEventListener("click", () => {
        actionsList.hidden = !actionsList.hidden;
        if (!actionsList.hidden) {
          setTimeout(() => {
            document.addEventListener("click", function closer(event) {
              if (!actionsMenu.contains(event.target)) actionsList.hidden = true;
              document.removeEventListener("click", closer);
            });
          }, 0);
        }
      });
      actionsList.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-action]");
        if (!button) return;
        actionsList.hidden = true;
        if (button.dataset.action === "remove") removeSelected();
        else if (button.dataset.action === "send") sendSelected();
        else if (button.dataset.action === "set-status") setSelectedStatus(button.dataset.status);
      });
    }

    updateSelectedSlotsCount();
    if (Array.isArray(restoreSelectedIds) && restoreSelectedIds.length) {
      const restore = new Set(restoreSelectedIds);
      node.querySelectorAll("input[data-select-row]").forEach((checkbox) => {
        if (restore.has(Number(checkbox.dataset.selectRow))) checkbox.checked = true;
      });
    }
    updateSelectAll();
    updateActionsMenu();

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
    const [data, session] = await Promise.all([
      api("/api/v1/admin/profiles/submissions?status=pending"),
      api("/api/v1/admin/session"),
    ]);
    node.innerHTML = `${session.is_admin ? `
      <section class="admin-profile-tools">
        <button type="button" data-create-profile>Create performer profile</button>
        <div data-profile-editor></div>
      </section>` : ""}
      <h2>Pending profile submissions</h2>
      <div>${data.submissions.length
        ? `<div class="admin-list">${data.submissions.map((item) => `
            <article>
              <h3><a href="/admin/profiles/submissions/${item.id}/">${escapeHtml(item.display_name)}</a></h3>
              <p>${escapeHtml(item.email)} · ${escapeHtml(item.submitted_at)}</p>
            </article>`).join("")}</div>`
        : "<p>No profile submissions are awaiting moderation.</p>"}</div>`;
    if (!session.is_admin) return;

    const editor = node.querySelector("[data-profile-editor]");
    const options = await api("/api/v1/admin/profiles/options");
    const socialPlatforms = options.social_platforms || [];
    const showEditor = (profile, events = []) => {
      const selectedEvents = new Set(profile?.requested_event_ids || []);
      const socialLinks = profile?.social_links || [];
      editor.innerHTML = `
        <form data-manual-profile-form>
          <h2>${profile ? `Edit ${escapeHtml(profile.display_name)}` : "Create performer profile"}</h2>
          <div class="admin-event-edit__row">
            <label>Profile type <select name="profile_type">
              <option value="person"${profile?.profile_type !== "group" ? " selected" : ""}>Artist</option>
              <option value="group"${profile?.profile_type === "group" ? " selected" : ""}>Group</option>
            </select></label>
            <label>Display name <input name="display_name" required value="${escapeHtml(profile?.display_name)}"></label>
          </div>
          <div class="admin-event-edit__row">
            <label>First name <input name="first_name" value="${escapeHtml(profile?.first_name)}"></label>
            <label>Last name <input name="last_name" value="${escapeHtml(profile?.last_name)}"></label>
          </div>
          <div class="admin-event-edit__row">
            <label>Email <input name="email" type="email" required value="${escapeHtml(profile?.email)}"></label>
            <label>Phone <input name="contact_phone" required value="${escapeHtml(profile?.contact_phone)}"></label>
          </div>
          <label><input type="checkbox" name="is_email_public"${profile?.is_email_public ? " checked" : ""}> Show email publicly</label>
          <label><input type="checkbox" name="is_name_public"${profile?.is_name_public ? " checked" : ""}> Show real name publicly</label>
          <label>Artist bio <textarea name="artist_bio" rows="6">${escapeHtml(profile?.artist_bio)}</textarea></label>
          <label>Image URL <input name="image_url" type="url" value="${escapeHtml(profile?.image_url)}"></label>
          <label><input type="checkbox" name="show_tribuo_link"${profile?.show_tribuo_link ? " checked" : ""}> Show Tribuo link</label>
          <fieldset><legend>Social links</legend><div data-manual-social-links></div><button type="button" data-add-social>Add social link</button></fieldset>
          <fieldset><legend>Future Open Mic availability requests</legend>
            ${events.length ? events.map((event) => `<label class="admin-choice"><input type="checkbox" name="requested_event_ids" value="${event.id}"${selectedEvents.has(event.id) ? " checked" : ""}> ${escapeHtml(event.event_date)} — ${escapeHtml(event.event_name)}</label>`).join("") : "<small>No future Open Mic events.</small>"}
          </fieldset>
          <button type="submit">Save profile</button><p role="status" data-manual-profile-status></p>
        </form>`;
      const socialNode = editor.querySelector("[data-manual-social-links]");
      const addSocial = (link = {}) => {
        const row = document.createElement("div");
        row.className = "admin-social-row";
        row.innerHTML = `<select name="social_platform_id"><option value="">Platform</option>${socialPlatforms.map((platform) => `<option value="${platform.id}"${String(platform.id) === String(link.social_platform_id) ? " selected" : ""}>${escapeHtml(platform.platform_name)}</option>`).join("")}</select><input name="profile_name" placeholder="Profile name" value="${escapeHtml(link.profile_name)}"><button type="button" data-remove-social>Remove</button>`;
        row.querySelector("[data-remove-social]").addEventListener("click", () => row.remove());
        socialNode.append(row);
      };
      socialLinks.forEach(addSocial);
      if (!socialLinks.length) addSocial();
      editor.querySelector("[data-add-social]").addEventListener("click", () => addSocial());
      editor.querySelector("[data-manual-profile-form]").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const social_links = [...socialNode.children].map((row) => ({
          social_platform_id: Number(row.querySelector("[name=social_platform_id]").value),
          profile_name: row.querySelector("[name=profile_name]").value,
        })).filter((link) => link.social_platform_id && link.profile_name.trim());
        const payload = {
          profile_type: form.get("profile_type"), display_name: form.get("display_name"),
          first_name: form.get("first_name"), last_name: form.get("last_name"), email: form.get("email"),
          contact_phone: form.get("contact_phone"), is_email_public: form.has("is_email_public"),
          is_name_public: form.has("is_name_public"), artist_bio: form.get("artist_bio"),
          image_url: form.get("image_url"), show_tribuo_link: form.has("show_tribuo_link"),
          social_links, requested_event_ids: form.getAll("requested_event_ids").map(Number),
        };
        const status = editor.querySelector("[data-manual-profile-status]");
        status.textContent = "Saving…";
        try {
          await api(profile ? `/api/v1/admin/profiles/${profile.id}` : "/api/v1/admin/profiles", { method: profile ? "PUT" : "POST", body: JSON.stringify(payload) });
          editor.innerHTML = "";
          const profileSearch = node.querySelector("[data-manual-profile-search]");
          const profileSuggestions = node.querySelector("[data-manual-profile-suggestions]");
          if (profileSearch) profileSearch.value = "";
          if (profileSuggestions) profileSuggestions.innerHTML = "";
          window.showToast?.("Profile saved.", { kind: "success" });
        } catch (error) { status.textContent = error.message; status.classList.add("is-error"); }
      });
    };
    node.querySelector("[data-create-profile]").addEventListener("click", () => showEditor(null, options.events || []));
    const search = document.createElement("div");
    search.innerHTML = `<h2>Edit an existing artist profile</h2><label>Search performer <input type="search" data-manual-profile-search autocomplete="off"></label><div data-manual-profile-suggestions></div>`;
    node.querySelector(".admin-profile-tools").prepend(search);
    const searchInput = search.querySelector("[data-manual-profile-search]");
    const suggestions = search.querySelector("[data-manual-profile-suggestions]");
    let timer;
    searchInput.addEventListener("input", () => {
      clearTimeout(timer); const query = searchInput.value.trim(); suggestions.innerHTML = "";
      if (query.length < 2) return;
      timer = setTimeout(async () => {
        const result = await api(`/api/v1/admin/profiles/search?q=${encodeURIComponent(query)}&artist_only=1`);
        suggestions.innerHTML = result.profiles.map((item, index) => `<button type="button" data-profile-suggestion="${index}">${escapeHtml(item.display_name)}${item.email ? ` — ${escapeHtml(item.email)}` : ""}</button>`).join("");
        suggestions.querySelectorAll("[data-profile-suggestion]").forEach((button) => button.addEventListener("click", async () => {
          const item = result.profiles[Number(button.dataset.profileSuggestion)];
          const profileData = await api(`/api/v1/admin/profiles/${item.profile_id}`);
          showEditor({ ...profileData.profile, image_url: profileData.image_url }, profileData.events);
          suggestions.innerHTML = ""; searchInput.value = item.display_name;
        }));
      }, 250);
    });
  }

  async function loadSubmission(node) {
    const draftId = Number(node.dataset.draftId);
    const data = await api(`/api/v1/admin/profiles/submissions/${draftId}`);
    const item = data.submission;
    const approvalMessage = "Your performer profile has been approved, and your requested performance dates have been noted.";
    const denialMessage = "Your performer profile submission was not approved at this stage.";
    node.innerHTML = `
      <h2>${escapeHtml(item.display_name)}</h2>
      <dl class="admin-details">
        <dt>Email</dt><dd>${escapeHtml(item.email)}</dd>
        <dt>Profile type</dt><dd>${escapeHtml(item.profile_type)}</dd>
        <dt>Name</dt><dd>${escapeHtml([item.first_name, item.last_name].filter(Boolean).join(" "))}</dd>
        <dt>Phone</dt><dd>${escapeHtml(item.contact_phone)}</dd>
        <dt>Show Tribuo link</dt><dd>${item.show_tribuo_link ? "Yes" : "No"}</dd>
        <dt>Artist bio</dt><dd>${escapeHtml(item.artist_bio)}</dd>
        <dt>Additional info</dt><dd>${escapeHtml(item.additional_info)}</dd>
        <dt>Social media</dt><dd>${renderSocialLinks(item.social_links)}</dd>
      </dl>
      ${item.previous_performances?.length ? `<p><strong>Previously performed at:</strong> ${item.previous_performances.map(escapeHtml).join(", ")}</p>` : ""}
      ${item.requested_date_summary?.length ? `
        <h3>Requested dates</h3>
        <div class="admin-table-wrap">
          <table>
            <thead><tr><th>Include</th><th>Requested date</th><th>New Faces</th><th>Total requested</th></tr></thead>
            <tbody>${item.requested_date_summary.map((summary) => `
              <tr>
                <td><input type="checkbox" name="requested_date_ids" value="${item.requested_events.find((event) => event.event_id === summary.event_id)?.requested_date_id || ""}" checked form="decision-form"></td>
                <td>${escapeHtml(summary.event_date)}${summary.event_name ? ` — ${escapeHtml(summary.event_name)}` : ""}</td>
                <td>${escapeHtml(summary.new_faces)}</td>
                <td>${escapeHtml(summary.total_requested)}</td>
              </tr>`).join("")}</tbody>
          </table>
        </div>` : ""}
      <form id="decision-form" data-decision-form>
        <label>Decision
          <select name="decision"><option value="approved">Approve</option><option value="denied">Deny</option></select>
        </label>
        <label>Include message <textarea name="message">${escapeHtml(approvalMessage)}</textarea></label>
        <label><input type="checkbox" name="include_edit_link" checked> Include a fresh edit link when denied</label>
        <button type="submit">Record decision</button>
      </form>`;
    const decisionSelect = node.querySelector("select[name=decision]");
    const messageField = node.querySelector("textarea[name=message]");
    decisionSelect.addEventListener("change", () => {
      messageField.value = decisionSelect.value === "approved" ? approvalMessage : denialMessage;
    });
    node.querySelector("[data-decision-form]")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      try {
        const result = await api(`/api/v1/admin/profiles/submissions/${draftId}/decisions`, {
          method: "POST",
          body: JSON.stringify({
            decision: form.get("decision"),
            message: form.get("message"),
            requested_date_ids: form.getAll("requested_date_ids").map(Number),
            include_edit_link: form.get("include_edit_link") === "on",
          }),
        });
        window.showToast?.(`Submission ${result.decision}.`, { kind: "success" });
        window.location.assign("/admin/profiles");
      } catch (error) {
        window.showToast?.(error.message, { kind: "error" });
      }
    });
  }

  const loaders = [
    ["[data-admin-dashboard]", loadDashboard],
    ["[data-admin-events]", loadEvents],
    ["[data-admin-locations]", loadLocations],
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
