const form = document.getElementById("merch-interest-form");
const statusNode = document.getElementById("merch-form-status");

function normalizeValue(value) {
  return String(value || "").trim().toLowerCase();
}

function getFieldsetVariants(fieldset) {
  return [...(fieldset?.querySelectorAll("[data-merch-variant-map] [data-variant-id]") || [])].map((node) => ({
    id: Number.parseInt(node.dataset.variantId || "0", 10),
    label: node.dataset.variantLabel || "",
    style: node.dataset.style || "",
    size: node.dataset.size || "",
    color: node.dataset.color || "",
    imageURL: node.dataset.imageUrl || "",
  }));
}

function resolveFieldsetVariant(fieldset) {
  const variants = getFieldsetVariants(fieldset);
  if (!variants.length) return null;

  const select = fieldset?.querySelector("[data-merch-item-select]");
  if (select) {
    const variantId = Number.parseInt(select.value || "0", 10);
    return variants.find((variant) => variant.id === variantId) || null;
  }

  const styleSelect = fieldset?.querySelector("[data-merch-item-style]");
  const sizeSelect = fieldset?.querySelector("[data-merch-item-size]");
  const colorSelect = fieldset?.querySelector("[data-merch-item-colour]");
  if (styleSelect || sizeSelect || colorSelect) {
    const styleValue = normalizeValue(styleSelect?.value);
    const sizeValue = normalizeValue(sizeSelect?.value);
    const colorValue = normalizeValue(colorSelect?.value);

    const exactMatch = variants.find(
      (variant) =>
        normalizeValue(variant.style) === styleValue &&
        normalizeValue(variant.size || variant.label) === sizeValue &&
        normalizeValue(variant.color) === colorValue
    );
    if (exactMatch) return exactMatch;

    const styleColorMatch =
      styleValue && colorValue
        ? variants.find(
            (variant) =>
              normalizeValue(variant.style) === styleValue &&
              normalizeValue(variant.color) === colorValue
          )
        : null;
    if (styleColorMatch) return styleColorMatch;

    const styleSizeMatch =
      styleValue && sizeValue
        ? variants.find(
            (variant) =>
              normalizeValue(variant.style) === styleValue &&
              normalizeValue(variant.size || variant.label) === sizeValue
          )
        : null;
    if (styleSizeMatch) return styleSizeMatch;

    const styleOnlyMatch = styleValue
      ? variants.find((variant) => normalizeValue(variant.style) === styleValue)
      : null;
    if (styleOnlyMatch) return styleOnlyMatch;

    const colorOnlyMatch = colorValue
      ? variants.find((variant) => normalizeValue(variant.color) === colorValue)
      : null;
    if (colorOnlyMatch) return colorOnlyMatch;

    const sizeOnlyMatch = variants.find(
      (variant) => normalizeValue(variant.size || variant.label) === sizeValue
    );
    if (sizeOnlyMatch) return sizeOnlyMatch;

    return null;
  }

  const quantityInput = fieldset?.querySelector("[data-merch-item-quantity]");
  const singleVariantId = Number.parseInt(quantityInput?.dataset.merchVariantId || "0", 10);
  return variants.find((variant) => variant.id === singleVariantId) || null;
}

function updateFieldsetPreview(fieldset) {
  const previewImage = fieldset?.querySelector("[data-merch-preview-image]");
  const variant = resolveFieldsetVariant(fieldset);

  if (previewImage && variant?.imageURL) {
    previewImage.src = variant.imageURL;
  }
}

if (form && statusNode) {
  [...form.querySelectorAll("[data-merch-item-select]")].forEach((select) => {
    select.addEventListener("change", () => updateFieldsetPreview(select.closest("fieldset")));
  });

  [...form.querySelectorAll("[data-merch-item-size], [data-merch-item-colour]")].forEach((select) => {
    select.addEventListener("change", () => updateFieldsetPreview(select.closest("fieldset")));
  });

  [...form.querySelectorAll("[data-merch-item-style]")].forEach((select) => {
    select.addEventListener("change", () => updateFieldsetPreview(select.closest("fieldset")));
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
        const selectedVariant = resolveFieldsetVariant(fieldset);
        const quantity = Number.parseInt(quantityInputs[index]?.value || "0", 10);
        const submittedPrice = String(priceInputs[index]?.value || "").trim();

        return {
          merch_variant_id: selectedVariant?.id || 0,
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
