const config = window.__WORKFLOW_CONFIG || {};
const apiBase = (config.apiBase || "/api").replace(/\/$/, "");

const form = document.getElementById("perform-interest-form");
const statusBox = document.getElementById("perform-interest-status");

function setStatus(message, level = "info", extraHtml = "") {
  if (!statusBox) return;
  statusBox.className = `workflow-status ${level}`;
  statusBox.innerHTML = extraHtml ? `${message}<div class="workflow-status-extra">${extraHtml}</div>` : message;
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = form.querySelector('button[type="submit"]');
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  submitButton.disabled = true;
  setStatus("Submitting interest…");

  try {
    const response = await fetch(`${apiBase}/performer-interest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Unable to submit interest");
    }

    const delivery = result.email?.sent ? "We emailed your private manage link." : "Email delivery is not configured yet, so keep this private link.";
    setStatus(
      "Interest submitted.",
      "success",
      `${delivery} <a href="${result.manageUrl}">Open manage page</a>`
    );
    form.reset();
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    submitButton.disabled = false;
  }
});
