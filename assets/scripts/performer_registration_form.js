const appNode = document.getElementById("performer-registration-app");

if (appNode) {
  const startSection = document.getElementById("performer-registration-start");
  const sessionSection = document.getElementById("performer-registration-session");
  const startForm = document.getElementById("performer-registration-start-form");
  const sessionForm = document.getElementById("performer-registration-session-form");
  const emailDisplay = document.getElementById("performer-email-display");
  const profileTypeField = document.getElementById("performer-profile-type");
  const displayNameField = document.getElementById("performer-display-name");
  const firstNameField = document.getElementById("performer-first-name");
  const lastNameField = document.getElementById("performer-last-name");
  const contactPhoneField = document.getElementById("performer-contact-phone");
  const bioField = document.getElementById("performer-artist-bio");
  const additionalInfoField = document.getElementById("performer-additional-info");
  const isEmailPublicField = document.getElementById("performer-is-email-public");
  const isNamePublicField = document.getElementById("performer-is-name-public");
  const socialLinksNode = document.getElementById("performer-social-links");
  const addSocialLinkButton = document.getElementById("performer-add-social-link");
  const eventOptionsNode = document.getElementById("performer-event-options");
  const eventsNoteNode = document.getElementById("performer-events-note");

  let registrationToken = new URLSearchParams(window.location.search).get("token") || "";
  let socialPlatforms = [];
  let availableEvents = [];

  function setStatus(message, kind = "") {
    const text = String(message || "").trim();
    if (!text) return;
    if (typeof window.showToast === "function") {
      window.showToast(text, { kind: kind || "info" });
    }
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("en-AU", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function getSocialPlatformById(platformId) {
    return socialPlatforms.find((platform) => Number(platform.id) === Number(platformId)) || null;
  }

  function splitUrlFormat(urlFormat) {
    const token = "{profileName}";
    const format = String(urlFormat || "");
    const tokenIndex = format.indexOf(token);
    if (tokenIndex < 0) {
      return {
        prefix: "",
        suffix: "",
      };
    }
    return {
      prefix: format.slice(0, tokenIndex),
      suffix: format.slice(tokenIndex + token.length),
    };
  }

  function inferSocialInputLabel(platform) {
    if (!platform) return "Profile name / handle";
    const format = String(platform.url_format || "").trim();
    if (format === "{profileName}") {
      return "Profile URL or address";
    }
    return "Profile name / handle";
  }

  function inferSocialInputPlaceholder(platform) {
    if (!platform) return "profile name";
    const format = String(platform.url_format || "").trim();
    if (format === "{profileName}") {
      return "https://example.com";
    }
    return "profile name";
  }

  function updateSocialLinkRowPresentation(row) {
    const platformSelect = row.querySelector("[data-social-platform-id]");
    const profileInput = row.querySelector("[data-social-profile-name]");
    const labelNode = row.querySelector("[data-social-profile-label]");
    const prefixNode = row.querySelector("[data-social-url-prefix]");
    const suffixNode = row.querySelector("[data-social-url-suffix]");
    const helpNode = row.querySelector("[data-social-profile-help]");

    if (!platformSelect || !profileInput || !labelNode || !prefixNode || !suffixNode || !helpNode) {
      return;
    }

    const selectedPlatform = getSocialPlatformById(platformSelect.value);
    const urlParts = splitUrlFormat(selectedPlatform?.url_format);
    const inputLabel =
      String(selectedPlatform?.input_label || "").trim() || inferSocialInputLabel(selectedPlatform);
    const inputPlaceholder =
      String(selectedPlatform?.input_placeholder || "").trim() || inferSocialInputPlaceholder(selectedPlatform);
    const inputHelp = String(selectedPlatform?.input_help || "").trim();

    labelNode.textContent = inputLabel;
    profileInput.placeholder = inputPlaceholder;

    prefixNode.textContent = urlParts.prefix;
    prefixNode.hidden = !urlParts.prefix;

    suffixNode.textContent = urlParts.suffix;
    suffixNode.hidden = !urlParts.suffix;

    helpNode.textContent = inputHelp;
    helpNode.hidden = !inputHelp;
  }

  function getSocialPlatformSelectWidthCh() {
    const longestName = socialPlatforms.reduce((maxLength, platform) => {
      const nameLength = String(platform?.platform_name || "").trim().length;
      return Math.max(maxLength, nameLength);
    }, 0);
    return Math.max(longestName + 3, 12);
  }

  function applySocialPlatformSelectWidth(row) {
    const platformSelect = row.querySelector("[data-social-platform-id]");
    if (!platformSelect) return;
    platformSelect.style.width = `${getSocialPlatformSelectWidthCh()}ch`;
  }

  function createSocialLinkRow(link = {}) {
    const row = document.createElement("div");
    row.className = "performer-social-link-row";

    const optionsHtml = socialPlatforms
      .map((platform) => {
        const isSelected = Number(platform.id) === Number(link.social_platform_id);
        return `<option value="${platform.id}"${isSelected ? " selected" : ""}>${escapeHtml(platform.platform_name)}</option>`;
      })
      .join("");

    row.innerHTML = `
      <div class="performer-social-link-fields">
        <label class="performer-social-platform-label">
          Platform
          <select data-social-platform-id class="performer-social-platform-select">
            <option value="">Choose...</option>
            ${optionsHtml}
          </select>
        </label>
        <label class="performer-social-profile-label">
          <span data-social-profile-label>Profile name / handle</span>
          <span class="performer-social-profile-input">
            <span class="performer-social-profile-prefix" data-social-url-prefix hidden></span>
            <input type="text" value="${escapeHtml(link.profile_name || "")}" data-social-profile-name>
            <span class="performer-social-profile-suffix" data-social-url-suffix hidden></span>
          </span>
        </label>
        <p class="performer-registration-note performer-social-profile-help" data-social-profile-help hidden></p>
      </div>
      <button type="button" data-remove-social-link>Remove</button>
    `;

    row.querySelector("[data-social-platform-id]")?.addEventListener("change", () => {
      updateSocialLinkRowPresentation(row);
    });

    row.querySelector("[data-remove-social-link]")?.addEventListener("click", () => {
      row.remove();
      if (!socialLinksNode.children.length) {
        createSocialLinkRow();
      }
    });

    applySocialPlatformSelectWidth(row);
    updateSocialLinkRowPresentation(row);
    socialLinksNode.appendChild(row);
  }

  function populateSocialLinks(links) {
    socialLinksNode.innerHTML = "";
    if (links && links.length) {
      links.forEach((link) => createSocialLinkRow(link));
      return;
    }
    createSocialLinkRow();
  }

  function populateEvents(events, selectedEventIds = []) {
    eventOptionsNode.innerHTML = "";
    availableEvents = events || [];
    const selectedSet = new Set((selectedEventIds || []).map((value) => Number(value)));

    if (!availableEvents.length) {
      eventOptionsNode.innerHTML = "<p>No eligible future dates are currently available.</p>";
      return;
    }

    availableEvents.forEach((eventItem) => {
      const wrapper = document.createElement("label");
      wrapper.className = "performer-event-option";
      const isChecked = selectedSet.has(Number(eventItem.id));
      const backupOnlyHtml = eventItem.is_backup_only
        ? ' <em class="performer-event-backup-note">(backup only)</em>'
        : "";
      wrapper.innerHTML = `
        <input type="checkbox" value="${eventItem.id}" data-event-checkbox${isChecked ? " checked" : ""}>
        <span>${escapeHtml(eventItem.event_name)} <small>(${escapeHtml(formatDate(eventItem.event_date))})</small>${backupOnlyHtml}</span>
      `;
      eventOptionsNode.appendChild(wrapper);
    });
  }

  function getSelectedEventIds() {
    return [...eventOptionsNode.querySelectorAll("[data-event-checkbox]:checked")]
      .map((node) => Number.parseInt(node.value || "0", 10))
      .filter((value) => value > 0);
  }

  function getSocialLinksRows() {
    return [...socialLinksNode.querySelectorAll(".performer-social-link-row")].map((row) => {
      const socialPlatformId = Number.parseInt(
        row.querySelector("[data-social-platform-id]")?.value || "0",
        10
      );
      const profileName = String(
        row.querySelector("[data-social-profile-name]")?.value || ""
      ).trim();
      return {
        social_platform_id: socialPlatformId,
        profile_name: profileName,
      };
    });
  }

  function applyProfile(profile, email) {
    emailDisplay.value = email || "";
    profileTypeField.value = profile?.profile_type || "person";
    displayNameField.value = profile?.display_name || "";
    firstNameField.value = profile?.first_name || "";
    lastNameField.value = profile?.last_name || "";
    contactPhoneField.value = profile?.contact_phone || "";
    bioField.value = profile?.artist_bio || "";
    additionalInfoField.value = profile?.additional_info || "";
    isEmailPublicField.checked = Boolean(profile?.is_email_public);
    isNamePublicField.checked = Boolean(profile?.is_name_public);
    populateSocialLinks(profile?.social_links || []);
  }

  async function loadSession(token) {
    // setStatus("Loading registration form...");
    try {
      const response = await fetch(`/api/forms/performer-registration/session?token=${encodeURIComponent(token)}`);
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to load registration form.");
      }

      socialPlatforms = result.social_platforms || [];
      applyProfile(result.profile, result.email);
      populateEvents(result.available_events || [], result.profile?.requested_event_ids || []);

      const hasBackupOnlyDates = (result.available_events || []).some(
        (eventItem) => Boolean(eventItem.is_backup_only)
      );
      eventsNoteNode.textContent = hasBackupOnlyDates
        ? "Tell us the dates you'd like to play. Dates marked 'backup only' fall within the cooldown period after your most recent performance."
        : "Tell us the dates you'd like to play.";

      startSection.hidden = true;
      sessionSection.hidden = false;
      setStatus("");
    } catch (error) {
      setStatus(error.message || "Unable to load registration form.", "error");
      startSection.hidden = false;
      sessionSection.hidden = true;
    }
  }

  startForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = String(document.getElementById("performer-registration-email")?.value || "").trim();

    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setStatus("Please enter a valid email address.", "error");
      return;
    }

    setStatus("Sending your registration link...");
    try {
      const response = await fetch("/api/forms/performer-registration/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to send registration link.");
      }

      setStatus("Your registration link has been emailed. Please check your inbox.", "success");
      startForm.reset();
    } catch (error) {
      setStatus(error.message || "Unable to send registration link.", "error");
    }
  });

  addSocialLinkButton?.addEventListener("click", () => createSocialLinkRow());

  sessionForm?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const requestedEventIds = getSelectedEventIds();
    if (!requestedEventIds.length) {
      setStatus("Please select at least one available date.", "error");
      return;
    }

    const socialLinkRows = getSocialLinksRows();
    const hasIncompleteSocialLink = socialLinkRows.some(
      (item) =>
        (item.social_platform_id > 0 && !item.profile_name) ||
        (!item.social_platform_id && item.profile_name)
    );
    if (hasIncompleteSocialLink) {
      setStatus("Please complete or remove any unfinished social link entries.", "error");
      return;
    }

    const socialLinks = socialLinkRows.filter(
      (item) => item.social_platform_id > 0 && item.profile_name
    );

    const payload = {
      token: registrationToken,
      profile_type: profileTypeField.value,
      display_name: String(displayNameField.value || "").trim(),
      first_name: String(firstNameField.value || "").trim() || null,
      last_name: String(lastNameField.value || "").trim() || null,
      contact_phone: String(contactPhoneField.value || "").trim(),
      is_email_public: isEmailPublicField.checked,
      is_name_public: isNamePublicField.checked,
      artist_bio: String(bioField.value || "").trim() || null,
      additional_info: String(additionalInfoField.value || "").trim() || null,
      social_links: socialLinks,
      requested_event_ids: requestedEventIds,
    };

    if (!payload.display_name) {
      setStatus("Please enter a display or stage name.", "error");
      return;
    }

    if (!payload.contact_phone) {
      setStatus("Please enter a contact phone number.", "error");
      return;
    }

    setStatus("Submitting your registration...");
    try {
      const response = await fetch("/api/forms/performer-registration/submit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to submit registration.");
      }

      setStatus("Your profile submission has been sent for moderation. We will email you once it has been reviewed.", "success");
      sessionForm.reset();
      populateSocialLinks([]);
      populateEvents(availableEvents, []);
      registrationToken = "";
      const url = new URL(window.location.href);
      url.searchParams.delete("token");
      window.history.replaceState({}, "", url.toString());
      startSection.hidden = false;
      sessionSection.hidden = true;
    } catch (error) {
      setStatus(error.message || "Unable to submit registration.", "error");
    }
  });

  if (registrationToken) {
    loadSession(registrationToken);
  }
}
