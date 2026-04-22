const form = document.getElementById("contact-us-form");

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

    const name = normalizeValue(document.getElementById("contact-name")?.value);
    const email = normalizeValue(document.getElementById("contact-email")?.value);
    const message = normalizeValue(document.getElementById("contact-message")?.value);
    const emailRegex = /^\S+@\S+\.\S+$/;

    if (!name) {
      notify("Please enter your name.", "error");
      return;
    }
    if (!emailRegex.test(email)) {
      notify("Please enter a valid email address.", "error");
      return;
    }
    if (!message) {
      notify("Please enter a message.", "error");
      return;
    }

    const submitButton = form.querySelector("button[type='submit']");
    if (submitButton) submitButton.disabled = true;
    notify("Sending your message...");

    try {
      const response = await fetch("/api/forms/contact-us", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name,
          email,
          message,
        }),
      });

      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Unable to send your message right now.");
      }

      notify(result.message || "Thanks. Your message has been sent.", "success");
      form.reset();
    } catch (error) {
      notify(error.message || "Unable to send your message right now.", "error");
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
}
