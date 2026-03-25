const form = document.getElementById("merch-interest-form");
const statusNode = document.getElementById("merch-form-status");

if (form && statusNode) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = String(document.getElementById("merch-email")?.value || "").trim();
    const comments = String(document.getElementById("merch-comments")?.value || "").trim();
    const emailRegex = /^\S+@\S+\.\S+$/;

    if (!emailRegex.test(email)) {
      statusNode.textContent = "Please enter a valid email address.";
      return;
    }

    const lines = [...form.querySelectorAll("[data-merch-variant-id]")]
      .map((input) => {
        const quantity = Number.parseInt(input.value, 10);
        return {
          merch_variant_id: Number.parseInt(input.dataset.merchVariantId, 10),
          quantity: Number.isNaN(quantity) ? 0 : quantity,
        };
      })
      .filter((line) => line.quantity > 0);

    if (!lines.length) {
      statusNode.textContent = "Please choose at least one merch item.";
      return;
    }

    const apiUrl = new URL("/api/forms/merch-interest", window.location.origin).toString();

    statusNode.textContent = "Submitting...";

    try {
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          comments: comments || null,
          lines,
        }),
      });

      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "Submission failed.");
      }

      form.reset();
      [...form.querySelectorAll("[data-merch-variant-id]")].forEach((input) => {
        input.value = "0";
      });
      statusNode.textContent = "Thanks. We'll let you know when merch becomes available.";
    } catch (error) {
      statusNode.textContent = error.message || "Submission failed. Please try again later.";
    }
  });
}
