const form = document.getElementById("newsletter-subscribe-form");

function normalizeValue(value) {
  return String(value || "").trim();
}

function notify(message, kind = "info") {
  const text = String(message || "").trim();
  if (!text) return;
  if (typeof window.showToast === "function") {
    window.showToast(text, { kind });
  }
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = normalizeValue(document.getElementById("newsletter-email")?.value);
    const firstName = normalizeValue(document.getElementById("newsletter-first-name")?.value);
    const lastName = normalizeValue(document.getElementById("newsletter-last-name")?.value);
    const emailRegex = /^\S+@\S+\.\S+$/;

    if (!emailRegex.test(email)) {
      notify("Please enter a valid email address.", "error");
      return;
    }

    notify("Sending confirmation email...");

    const submitButton = form.querySelector("button[type='submit']");
    if (submitButton) submitButton.disabled = true;

    try {
      const response = await fetch("/api/forms/newsletter-subscribe/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          first_name: firstName || null,
          last_name: lastName || null,
        }),
      });

      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to send confirmation email right now.");
      }

      notify(result.message || "Thanks. Please check your email and click the confirmation link.", "success");
      form.reset();
    } catch (error) {
      notify(error.message || "Unable to send confirmation email right now.", "error");
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
}
