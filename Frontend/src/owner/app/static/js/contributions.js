(function () {
  const api =
    document.querySelector('meta[name="dataset-api"]')?.getAttribute("content") ||
    "/api/classifications/dataset/batch";
  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  const dialog = document.getElementById("removeDatasetDialog");
  const errorEl = document.getElementById("contribError");
  const successEl = document.getElementById("contribSuccess");
  const dialogError = document.getElementById("removeDatasetError");
  let pendingId = null;

  function showFlash(el, message) {
    if (!el) return;
    if (!message) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = message;
  }

  async function postRemove(id) {
    const response = await fetch(api, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrf,
      },
      credentials: "same-origin",
      body: JSON.stringify({ action: "remove_from_dataset", ids: [id] }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || data.failed?.[0]?.error || "Could not remove from dataset.");
    }
    return data;
  }

  document.querySelectorAll(".ch-remove-dataset").forEach((button) => {
    button.addEventListener("click", () => {
      pendingId = button.getAttribute("data-id");
      showFlash(dialogError, "");
      showFlash(errorEl, "");
      showFlash(successEl, "");
      if (dialog?.showModal) dialog.showModal();
    });
  });

  document.getElementById("removeDatasetConfirmBtn")?.addEventListener("click", async () => {
    const id = pendingId;
    if (!id) return;
    const btn = document.getElementById("removeDatasetConfirmBtn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Removing…";
    }
    showFlash(dialogError, "");
    try {
      await postRemove(id);
      if (dialog?.open) dialog.close();
      const card = document.querySelector(`.ch-card[data-id="${CSS.escape(id)}"]`);
      card?.remove();
      showFlash(successEl, "Removed from dataset pool. Photo is still Approved in Customer History.");
      const grid = document.getElementById("contribGrid");
      if (grid && !grid.querySelector(".ch-card")) {
        window.setTimeout(() => window.location.reload(), 700);
      }
    } catch (error) {
      showFlash(dialogError, error.message || "Remove failed.");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Remove from Dataset";
      }
      pendingId = null;
    }
  });

  dialog?.addEventListener("close", () => {
    pendingId = null;
    showFlash(dialogError, "");
  });
})();
