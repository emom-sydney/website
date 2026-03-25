const form = document.getElementById("merch-interest-form");
const statusNode = document.getElementById("merch-form-status");

if (form && statusNode) {
  [...form.querySelectorAll("[data-merch-item-select]")].forEach((select) => {
    select.addEventListener("change", () => {
      const previewImage = select
        .closest("fieldset")
        ?.querySelector("[data-merch-preview-image]");
      const selectedOption = select.options[select.selectedIndex];
      const selectedImageUrl = selectedOption?.dataset.imageUrl;

      if (previewImage && selectedImageUrl) {
        previewImage.src = selectedImageUrl;
      }
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = String(document.getElementById("merch-email")?.value || "").trim();
    const comments = String(document.getElementById("merch-comments")?.value || "").trim();
    const emailRegex = /^\S+@\S+\.\S+$/;

    if (!emailRegex.test(email)) {
      statusNode.textContent = "Please enter a valid email address.";
      return;
    }

    const quantityInputs = [...form.querySelectorAll("[data-merch-item-quantity]")];
    const priceInputs = [...form.querySelectorAll("[data-merch-item-price]")];
    const lines = quantityInputs
      .map((quantityInput, index) => {
        const fieldset = quantityInput.closest("fieldset");
        const select = fieldset?.querySelector("[data-merch-item-select]");
        const selectedVariantId = select ? Number.parseInt(select.value, 10) : Number.parseInt(quantityInput.dataset.merchVariantId || "0", 10);
        const quantity = Number.parseInt(quantityInputs[index]?.value || "0", 10);
        const submittedPrice = String(priceInputs[index]?.value || "").trim();

        return {
          merch_variant_id: Number.isNaN(selectedVariantId) ? 0 : selectedVariantId,
          quantity: Number.isNaN(quantity) ? 0 : quantity,
          submitted_price: submittedPrice,
        };
      })
      .filter((line) => line.merch_variant_id > 0 && line.quantity > 0);

    const invalidPrice = lines.some((line) => !/^\d+(\.\d{1,2})?$/.test(line.submitted_price));
    if (invalidPrice) {
      statusNode.textContent = "Please enter a valid suggested price using numbers only.";
      return;
    }

    if (!lines.length) {
      statusNode.textContent = "Please enter a quantity for at least one merch item.";
      return;
    }

    statusNode.textContent = "Submitting...";

    try {
      const response = await fetch("/api/forms/merch-interest", {
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

      window.location.href = "/merch/thanks/index.html";
    } catch (error) {
      statusNode.textContent = error.message || "Submission failed. Please try again later.";
    }
  });
}
