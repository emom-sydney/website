const form = document.getElementById("newsletter-subscribe-form");
const statusNode = document.getElementById("newsletter-subscribe-status");

function normalizeValue(value) {
  return String(value || "").trim();
}

if (form && statusNode) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = normalizeValue(document.getElementById("newsletter-email")?.value);
    const firstName = normalizeValue(document.getElementById("newsletter-first-name")?.value);
    const lastName = normalizeValue(document.getElementById("newsletter-last-name")?.value);
    const emailRegex = /^\S+@\S+\.\S+$/;

    if (!emailRegex.test(email)) {
      statusNode.textContent = "Please enter a valid email address.";
      return;
    }

    statusNode.textContent = "Sending confirmation email...";

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

      statusNode.textContent =
        result.message || "Thanks. Please check your email and click the confirmation link.";
      form.reset();
    } catch (error) {
      statusNode.textContent = error.message || "Unable to send confirmation email right now.";
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
}
