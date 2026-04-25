const appNode = document.getElementById("volunteer-registration-app");

if (appNode) {
  const startSection = document.getElementById("volunteer-registration-start");
  const sessionSection = document.getElementById("volunteer-registration-session");
  const claimsSection = document.getElementById("volunteer-claims-session");

  const startForm = document.getElementById("volunteer-registration-start-form");
  const claimsStartForm = document.getElementById("volunteer-claims-start-form");
  const sessionForm = document.getElementById("volunteer-registration-session-form");

  const emailDisplay = document.getElementById("volunteer-email-display");
  const profileTypeField = document.getElementById("volunteer-profile-type");
  const displayNameField = document.getElementById("volunteer-display-name");
  const firstNameField = document.getElementById("volunteer-first-name");
  const lastNameField = document.getElementById("volunteer-last-name");
  const contactPhoneField = document.getElementById("volunteer-contact-phone");
  const bioField = document.getElementById("volunteer-bio");
  const additionalInfoField = document.getElementById("volunteer-additional-info");
  const isEmailPublicField = document.getElementById("volunteer-is-email-public");
  const isNamePublicField = document.getElementById("volunteer-is-name-public");
  const socialLinksNode = document.getElementById("volunteer-social-links");
  const addSocialLinkButton = document.getElementById("volunteer-add-social-link");
  const roleClaimsNode = document.getElementById("volunteer-role-claims");
  const claimsListNode = document.getElementById("volunteer-claims-list");

  let registrationToken = new URLSearchParams(window.location.search).get("token") || "";
  let claimsToken = new URLSearchParams(window.location.search).get("claims_token") || "";
  let socialPlatforms = [];
  let roleAvailability = [];
  let existingClaimKeys = new Set();

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

  function claimKey(eventId, roleKey) {
    return `${Number(eventId)}::${String(roleKey || "").toLowerCase()}`;
  }

  function getSocialPlatformById(platformId) {
    return socialPlatforms.find((platform) => Number(platform.id) === Number(platformId)) || null;
  }

  function splitUrlFormat(urlFormat) {
    const token = "{profileName}";
    const format = String(urlFormat || "");
    const tokenIndex = format.indexOf(token);
    if (tokenIndex < 0) {
      return { prefix: "", suffix: "" };
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

  function renderRoleClaims(events) {
    roleClaimsNode.innerHTML = "";
    roleAvailability = events || [];

    if (!roleAvailability.length) {
      roleClaimsNode.innerHTML = "<p>No future events are currently available.</p>";
      return;
    }

    for (const eventItem of roleAvailability) {
      const container = document.createElement("section");
      container.className = "volunteer-role-event";
      container.innerHTML = `
        <h3>${escapeHtml(eventItem.event_name)} <small>(${escapeHtml(formatDate(eventItem.event_date))})</small></h3>
        <div class="volunteer-role-grid"></div>
      `;
      const grid = container.querySelector(".volunteer-role-grid");

      for (const role of eventItem.roles || []) {
        const key = claimKey(eventItem.event_id, role.role_key);
        const isChecked = existingClaimKeys.has(key);
        const isFilled = Boolean(role.is_filled) && role.user_claim_status !== "selected";
        const statusText = isFilled
          ? "Filled (new claims become standby)"
          : `${role.selected_count}/${role.capacity} selected`;

        const card = document.createElement("label");
        card.className = "volunteer-role-card";
        card.innerHTML = `
          <input type="checkbox" data-role-claim data-event-id="${eventItem.event_id}" data-role-key="${escapeHtml(role.role_key)}"${isChecked ? " checked" : ""}>
          <span>
            <strong>${escapeHtml(role.display_name)}</strong>
            <small>${escapeHtml(statusText)}${role.standby_count ? ` • ${role.standby_count} standby` : ""}</small>
            <small>${escapeHtml(role.description || "")}</small>
          </span>
        `;
        grid.appendChild(card);
      }

      roleClaimsNode.appendChild(container);
    }
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

  function getSelectedRoleClaims() {
    return [...roleClaimsNode.querySelectorAll("[data-role-claim]:checked")].map((node) => ({
      event_id: Number.parseInt(node.getAttribute("data-event-id") || "0", 10),
      role_key: String(node.getAttribute("data-role-key") || "").toLowerCase(),
    })).filter((item) => item.event_id > 0 && item.role_key);
  }

  async function loadRegistrationSession(token) {
    try {
      const response = await fetch(`/api/forms/volunteer-registration/session?token=${encodeURIComponent(token)}`);
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to load volunteer registration form.");
      }

      socialPlatforms = result.social_platforms || [];
      existingClaimKeys = new Set(
        (result.existing_claims || []).map((item) => claimKey(item.event_id, item.role_key))
      );

      applyProfile(result.profile, result.email);
      renderRoleClaims(result.role_availability || []);

      startSection.hidden = true;
      claimsSection.hidden = true;
      sessionSection.hidden = false;
    } catch (error) {
      setStatus(error.message || "Unable to load volunteer registration form.", "error");
      startSection.hidden = false;
      sessionSection.hidden = true;
      claimsSection.hidden = true;
    }
  }

  function renderClaimsList(claims) {
    claimsListNode.innerHTML = "";
    if (!claims || !claims.length) {
      claimsListNode.innerHTML = "<p>No volunteer claims found.</p>";
      return;
    }

    const list = document.createElement("div");
    list.className = "volunteer-claims-list";

    for (const claim of claims) {
      const item = document.createElement("article");
      item.className = "volunteer-claim-item";
      item.innerHTML = `
        <h3>${escapeHtml(claim.event_name)} <small>(${escapeHtml(formatDate(claim.event_date))})</small></h3>
        <p><strong>${escapeHtml(claim.role_display_name)}</strong></p>
        <p>Status: ${escapeHtml(claim.status)}</p>
      `;

      if (claim.status === "selected" || claim.status === "standby") {
        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.textContent = "Cancel claim";
        cancelButton.addEventListener("click", async () => {
          try {
            const response = await fetch("/api/forms/volunteer-registration/claims/cancel", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                token: claimsToken,
                claim_id: claim.claim_id,
              }),
            });
            const result = await response.json();
            if (!response.ok || !result.ok) {
              throw new Error(result.error || "Unable to cancel claim.");
            }
            if (result.promoted?.display_name) {
              setStatus(`${result.promoted.display_name} has been promoted from standby.`, "success");
            } else {
              setStatus("Claim cancelled.", "success");
            }
            await loadClaimsSession(claimsToken);
          } catch (error) {
            setStatus(error.message || "Unable to cancel claim.", "error");
          }
        });
        item.appendChild(cancelButton);
      }

      list.appendChild(item);
    }

    claimsListNode.appendChild(list);
  }

  async function loadClaimsSession(token) {
    try {
      const response = await fetch(`/api/forms/volunteer-registration/claims/session?token=${encodeURIComponent(token)}`);
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to load volunteer claims.");
      }

      renderClaimsList(result.claims || []);
      startSection.hidden = true;
      sessionSection.hidden = true;
      claimsSection.hidden = false;
    } catch (error) {
      setStatus(error.message || "Unable to load volunteer claims.", "error");
      startSection.hidden = false;
      sessionSection.hidden = true;
      claimsSection.hidden = true;
    }
  }

  startForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = String(document.getElementById("volunteer-registration-email")?.value || "").trim();
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setStatus("Please enter a valid email address.", "error");
      return;
    }

    setStatus("Sending your volunteer registration link...");
    try {
      const response = await fetch("/api/forms/volunteer-registration/start", {
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

  claimsStartForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = String(document.getElementById("volunteer-claims-email")?.value || "").trim();
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setStatus("Please enter a valid email address.", "error");
      return;
    }

    setStatus("Sending your claims-management link...");
    try {
      const response = await fetch("/api/forms/volunteer-registration/claims/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to send claims link.");
      }
      setStatus(result.message || "If that email belongs to a volunteer profile, a claims link has been sent.", "success");
      claimsStartForm.reset();
    } catch (error) {
      setStatus(error.message || "Unable to send claims link.", "error");
    }
  });

  addSocialLinkButton?.addEventListener("click", () => createSocialLinkRow());

  sessionForm?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const roleClaims = getSelectedRoleClaims();
    if (!roleClaims.length) {
      setStatus("Please select at least one volunteer role claim.", "error");
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
      volunteer_bio: String(bioField.value || "").trim() || null,
      additional_info: String(additionalInfoField.value || "").trim() || null,
      social_links: socialLinks,
      role_claims: roleClaims,
    };

    if (!payload.display_name) {
      setStatus("Please enter a display name.", "error");
      return;
    }

    if (!payload.contact_phone) {
      setStatus("Please enter a contact phone number.", "error");
      return;
    }

    setStatus("Submitting your volunteer registration...");
    try {
      const response = await fetch("/api/forms/volunteer-registration/submit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to submit volunteer registration.");
      }

      if (result.auto_approved) {
        setStatus("Your profile is already approved, and your claims have been recorded.", "success");
      } else {
        setStatus("Your volunteer submission has been sent for moderation.", "success");
      }

      sessionForm.reset();
      populateSocialLinks([]);
      roleClaimsNode.innerHTML = "";
      registrationToken = "";
      const url = new URL(window.location.href);
      url.searchParams.delete("token");
      window.history.replaceState({}, "", url.toString());
      startSection.hidden = false;
      sessionSection.hidden = true;
      claimsSection.hidden = true;
    } catch (error) {
      setStatus(error.message || "Unable to submit volunteer registration.", "error");
    }
  });

  if (claimsToken) {
    loadClaimsSession(claimsToken);
  } else if (registrationToken) {
    loadRegistrationSession(registrationToken);
  }
}
