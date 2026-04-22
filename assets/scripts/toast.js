(function () {
  const MAX_TOASTS = 4;
  const DEFAULT_DURATION_MS = 4000;

  function getRoot() {
    let root = document.getElementById("toast-root");
    if (root) return root;
    root = document.createElement("div");
    root.id = "toast-root";
    root.className = "toast-stack";
    root.setAttribute("aria-live", "polite");
    root.setAttribute("aria-atomic", "true");
    document.body.appendChild(root);
    return root;
  }

  function removeToast(node) {
    if (!node || !node.parentNode) return;
    node.classList.add("toast--closing");
    window.setTimeout(() => {
      if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
    }, 180);
  }

  function clampToasts(root) {
    while (root.children.length > MAX_TOASTS) {
      removeToast(root.firstElementChild);
    }
  }

  function showToast(message, options = {}) {
    const text = String(message || "").trim();
    if (!text) return;

    const kind = String(options.kind || "info").toLowerCase();
    const durationMs = Number.isFinite(options.duration) ? Number(options.duration) : DEFAULT_DURATION_MS;
    const role = kind === "error" ? "alert" : "status";
    const root = getRoot();
    const toast = document.createElement("div");

    toast.className = `toast toast--${kind}`;
    toast.setAttribute("role", role);

    const textNode = document.createElement("div");
    textNode.className = "toast__message";
    textNode.textContent = text;

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "toast__close";
    closeButton.setAttribute("aria-label", "Dismiss notification");
    closeButton.textContent = "x";
    closeButton.addEventListener("click", () => removeToast(toast));

    toast.appendChild(textNode);
    toast.appendChild(closeButton);
    root.appendChild(toast);
    clampToasts(root);

    if (durationMs > 0) {
      const timer = window.setTimeout(() => removeToast(toast), durationMs);
      toast.addEventListener("mouseenter", () => window.clearTimeout(timer), { once: true });
    }
  }

  window.showToast = showToast;
}());
