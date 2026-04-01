const appNode = document.getElementById("performer-registration-app");

if (appNode) {
  const startSection = document.getElementById("performer-registration-start");
  const sessionSection = document.getElementById("performer-registration-session");
  const statusNode = document.getElementById("performer-registration-status");
  const startForm = document.getElementById("performer-registration-start-form");
  const sessionForm = document.getElementById("performer-registration-session-form");
  const introNode = document.getElementById("performer-registration-intro");
  const emailDisplay = document.getElementById("performer-email-display");
  const profileTypeField = document.getElementById("performer-profile-type");
  const displayNameField = document.getElementById("performer-display-name");
  const firstNameField = document.getElementById("performer-first-name");
  const lastNameField = document.getElementById("performer-last-name");
  const contactPhoneField = document.getElementById("performer-contact-phone");
  const bioField = document.getElementById("performer-artist-bio");
  const isEmailPublicField = document.getElementById("performer-is-email-public");
  const isNamePublicField = document.getElementById("performer-is-name-public");
  const isBioPublicField = document.getElementById("performer-is-bio-public");
  const socialLinksNode = document.getElementById("performer-social-links");
  const addSocialLinkButton = document.getElementById("performer-add-social-link");
  const eventOptionsNode = document.getElementById("performer-event-options");
  const eventsNoteNode = document.getElementById("performer-events-note");

  let registrationToken = new URLSearchParams(window.location.search).get("token") || "";
  let socialPlatforms = [];
  let availableEvents = [];

  function setStatus(message, kind = "") {
    statusNode.textContent = message || "";
    statusNode.dataset.statusKind = kind;
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
        <label>
          Platform
          <select data-social-platform-id>
            <option value="">Choose...</option>
            ${optionsHtml}
          </select>
        </label>
        <label>
          Profile name / handle
          <input type="text" value="${escapeHtml(link.profile_name || "")}" data-social-profile-name>
        </label>
      </div>
      <button type="button" data-remove-social-link>Remove</button>
    `;

    row.querySelector("[data-remove-social-link]")?.addEventListener("click", () => {
      row.remove();
      if (!socialLinksNode.children.length) {
        createSocialLinkRow();
      }
    });

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

  function populateEvents(events) {
    eventOptionsNode.innerHTML = "";
    availableEvents = events || [];

    if (!availableEvents.length) {
      eventOptionsNode.innerHTML = "<p>No eligible future dates are currently available.</p>";
      return;
    }

    availableEvents.forEach((eventItem) => {
      const wrapper = document.createElement("label");
      wrapper.className = "performer-event-option";
      wrapper.innerHTML = `
        <input type="checkbox" value="${eventItem.id}" data-event-checkbox>
        <span>${escapeHtml(eventItem.event_name)} <small>(${escapeHtml(formatDate(eventItem.event_date))})</small></span>
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
    isEmailPublicField.checked = Boolean(profile?.is_email_public);
    isNamePublicField.checked = Boolean(profile?.is_name_public);
    isBioPublicField.checked = Boolean(profile?.is_artist_bio_public);
    populateSocialLinks(profile?.social_links || []);
  }

  async function loadSession(token) {
    setStatus("Loading registration form...");
    try {
      const response = await fetch(`/api/forms/performer-registration/session?token=${encodeURIComponent(token)}`);
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to load registration form.");
      }

      socialPlatforms = result.social_platforms || [];
      applyProfile(result.profile, result.email);
      populateEvents(result.available_events || []);

      introNode.textContent = result.profile
        ? "Update your performer profile details below and select the dates you are available to play."
        : "Create your performer profile below and select the dates you are available to play.";
      eventsNoteNode.textContent = result.cooldown_events
        ? `Available dates are based on upcoming events and the current cooldown rule of skipping the next ${result.cooldown_events} event(s) after a recent performance.`
        : "";

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
      is_artist_bio_public: isBioPublicField.checked,
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
      populateEvents(availableEvents);
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
