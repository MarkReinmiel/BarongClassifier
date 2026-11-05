(function () {
  const modal = document.getElementById("reviewModal");
  const approveDialog = document.getElementById("approveDialog");
  const rejectDialog = document.getElementById("rejectDialog");
  if (!modal && !approveDialog && !rejectDialog) return;

  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  const apiBase =
    document.querySelector('meta[name="review-api-base"]')?.getAttribute("content") ||
    "/api/classifications";
  let currentId = null;
  let currentStatus = "pending_review";
  let pendingConfirmChange = false;
  let submitting = false;

  function detailUrl(id) {
    return `${apiBase}/${encodeURIComponent(id)}`;
  }
  function actionUrl(id) {
    return `${apiBase}/${encodeURIComponent(id)}/review`;
  }

  const els = {
    image: document.getElementById("reviewImage"),
    noImage: document.getElementById("reviewNoImage"),
    customer: document.getElementById("reviewCustomer"),
    email: document.getElementById("reviewEmail"),
    predicted: document.getElementById("reviewPredicted"),
    confidence: document.getElementById("reviewConfidence"),
    when: document.getElementById("reviewWhen"),
    status: document.getElementById("reviewStatus"),
    error: document.getElementById("reviewError"),
    events: document.getElementById("reviewEvents"),
    approveBtn: document.getElementById("approveBtn"),
    rejectBtn: document.getElementById("rejectBtn"),
  };

  function showError(target, message) {
    if (!target) return;
    if (!message) {
      target.hidden = true;
      target.textContent = "";
      return;
    }
    target.hidden = false;
    target.textContent = message;
  }

  function showToast(message, kind) {
    let toast = document.getElementById("chToast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "chToast";
      toast.className = "ch-toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = `ch-toast ch-toast--${kind || "ok"}`;
    toast.hidden = false;
    window.clearTimeout(showToast._timer);
    showToast._timer = window.setTimeout(() => {
      toast.hidden = true;
    }, 3200);
  }

  function needsChangeConfirm(status) {
    return Boolean(status) && status !== "pending_review";
  }

  function statusLabel(status) {
    const key = String(status || "pending_review").toLowerCase();
    const labels = {
      pending_review: "Pending Review",
      approved: "Approved",
      rejected: "Rejected",
      uncertain: "Uncertain",
      added_to_dataset: "Added to Dataset",
    };
    return labels[key] || key.replace(/_/g, " ");
  }

  function setPreview(imgEl, emptyEl, url) {
    const hasImage = Boolean(url);
    if (imgEl) {
      imgEl.hidden = !hasImage;
      imgEl.src = url || "";
    }
    if (emptyEl) emptyEl.hidden = hasImage;
  }

  function setBusy(isBusy, activeAction) {
    submitting = Boolean(isBusy);
    const buttons = [
      els.approveBtn,
      els.rejectBtn,
      document.getElementById("approveConfirmBtn"),
      document.getElementById("rejectConfirmBtn"),
      ...document.querySelectorAll(".ch-approve, .ch-reject"),
    ];
    buttons.forEach((button) => {
      if (!button) return;
      button.disabled = submitting;
    });
    if (els.approveBtn) {
      els.approveBtn.textContent =
        submitting && activeAction === "approve" ? "Approving…" : "Approve";
    }
    if (els.rejectBtn) {
      els.rejectBtn.textContent =
        submitting && activeAction === "reject" ? "Rejecting…" : "Reject";
    }
    const approveConfirm = document.getElementById("approveConfirmBtn");
    const rejectConfirm = document.getElementById("rejectConfirmBtn");
    if (approveConfirm) {
      approveConfirm.textContent =
        submitting && activeAction === "approve" ? "Approving…" : "Approve";
    }
    if (rejectConfirm) {
      rejectConfirm.textContent =
        submitting && activeAction === "reject" ? "Rejecting…" : "Reject";
    }
  }

  function updateCard(item) {
    const card = document.querySelector(`.ch-card[data-id="${item.id}"]`);
    if (!card) return;
    const badge = card.querySelector(".ch-badge");
    if (badge) {
      badge.className = `ch-badge ch-badge--${item.review_status}`;
      badge.textContent = statusLabel(item.review_status);
    }
    card.querySelectorAll(".ch-approve, .ch-reject").forEach((btn) => {
      btn.setAttribute("data-status", item.review_status || "pending_review");
    });
  }

  function fill(item) {
    currentId = item.id;
    currentStatus = item.review_status || "pending_review";
    const hasImage = Boolean(item.image_url);
    if (els.image) {
      els.image.hidden = !hasImage;
      els.image.src = item.image_url || "";
      els.image.alt = item.predicted_display || "Classification image";
    }
    if (els.noImage) els.noImage.hidden = hasImage;
    if (els.customer) els.customer.textContent = item.customer_name || "—";
    if (els.email) els.email.textContent = item.customer_email || "—";
    if (els.predicted) els.predicted.textContent = item.predicted_display || "—";
    if (els.confidence) {
      els.confidence.textContent =
        item.confidence_pct != null ? `${item.confidence_pct}%` : "—";
    }
    if (els.when) els.when.textContent = item.created_at_display || "—";
    if (els.status) els.status.textContent = statusLabel(item.review_status);
    if (els.events) {
      const events = item.events || [];
      if (!events.length) {
        els.events.innerHTML = "<li>No review decisions yet.</li>";
      } else {
        els.events.innerHTML = events
          .map(
            (event) =>
              `<li><strong>${statusLabel(event.new_status)}</strong> by ${
                event.actor_email || "owner"
              } · ${event.created_at || ""}</li>`
          )
          .join("");
      }
    }
    showError(els.error, "");
  }

  async function loadDetail(id) {
    showError(els.error, "");
    const response = await fetch(detailUrl(id), {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Could not load classification.");
    }
    fill(data.item);
    pendingConfirmChange = needsChangeConfirm(data.item.review_status);
    if (modal && typeof modal.showModal === "function") modal.showModal();
  }

  async function submitReview(id, payload) {
    const response = await fetch(actionUrl(id), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrf,
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      const error = new Error(data.error || "Review could not be saved.");
      error.status = response.status;
      error.payload = data;
      throw error;
    }
    return data.item;
  }

  async function runReview(action, { confirmChange, errorEl, closeDialog } = {}) {
    if (!currentId) {
      console.error("[customer-history] Missing classification id for", action);
      return;
    }
    if (submitting) return;

    setBusy(true, action);
    showError(errorEl, "");
    try {
      const item = await submitReview(currentId, {
        action,
        confirm_change: Boolean(confirmChange),
      });
      updateCard(item);
      fill(item);
      pendingConfirmChange = needsChangeConfirm(item.review_status);
      showToast(
        action === "approve" ? "Photo approved." : "Photo rejected.",
        action === "approve" ? "ok" : "bad"
      );
      if (typeof closeDialog === "function") closeDialog();
      return item;
    } catch (error) {
      console.error("[customer-history] Review failed", {
        action,
        classificationId: currentId,
        status: error.status,
        message: error.message,
        payload: error.payload,
      });
      showError(errorEl, error.message || `${action} failed.`);
      throw error;
    } finally {
      setBusy(false);
    }
  }

  /**
   * HTML allows only one modal <dialog> at a time. Opening approve/reject
   * confirm while the preview is open throws InvalidStateError and blocks
   * the request. Preview actions therefore confirm + submit in-place.
   */
  async function submitFromPreview(action) {
    if (!currentId || submitting) return;
    const mustConfirmChange = needsChangeConfirm(currentStatus);
    const prompt =
      action === "approve"
        ? mustConfirmChange
          ? "This photo was already reviewed. Approve it anyway?"
          : "Approve this photo for future dataset use?"
        : mustConfirmChange
          ? "This photo was already reviewed. Reject it anyway?"
          : "Reject this photo?";
    if (!window.confirm(prompt)) return;
    try {
      await runReview(action, {
        confirmChange: mustConfirmChange,
        errorEl: els.error,
      });
    } catch (_error) {
      // Error already shown in the preview panel and logged.
    }
  }

  function openApproveConfirm({ id, status, imageUrl, customer, predicted }) {
    if (modal?.open) {
      // Avoid nested modal dialogs — handle from the open preview instead.
      currentId = id;
      currentStatus = status || currentStatus;
      submitFromPreview("approve");
      return;
    }
    currentId = id;
    pendingConfirmChange = needsChangeConfirm(status);
    setPreview(
      document.getElementById("approvePreview"),
      document.getElementById("approveNoImage"),
      imageUrl || ""
    );
    const customerLine = document.getElementById("approveCustomerLine");
    const predictedLine = document.getElementById("approvePredictedLine");
    const warn = document.getElementById("approveChangeWarn");
    if (customerLine) {
      customerLine.textContent = `Customer: ${customer || "Customer"}`;
    }
    if (predictedLine) {
      predictedLine.textContent = `CNN predicted: ${predicted || "—"}`;
    }
    if (warn) warn.hidden = !pendingConfirmChange;
    showError(document.getElementById("approveError"), "");
    if (approveDialog && typeof approveDialog.showModal === "function") {
      approveDialog.showModal();
    }
  }

  function openRejectConfirm({ id, status, imageUrl, customer, predicted }) {
    if (modal?.open) {
      currentId = id;
      currentStatus = status || currentStatus;
      submitFromPreview("reject");
      return;
    }
    currentId = id;
    pendingConfirmChange = needsChangeConfirm(status);
    setPreview(
      document.getElementById("rejectPreview"),
      document.getElementById("rejectNoImage"),
      imageUrl || ""
    );
    const customerLine = document.getElementById("rejectCustomerLine");
    const predictedLine = document.getElementById("rejectPredictedLine");
    const warn = document.getElementById("rejectChangeWarn");
    if (customerLine) {
      customerLine.textContent = `Customer: ${customer || "Customer"}`;
    }
    if (predictedLine) {
      predictedLine.textContent = `CNN predicted: ${predicted || "—"}`;
    }
    if (warn) warn.hidden = !pendingConfirmChange;
    showError(document.getElementById("rejectError"), "");
    try {
      if (rejectDialog && typeof rejectDialog.showModal === "function") {
        rejectDialog.showModal();
      }
    } catch (error) {
      console.error("[customer-history] Could not open reject dialog", error);
      showToast("Could not open reject dialog. Try again.", "bad");
    }
  }

  function openApproveFromButton(button) {
    openApproveConfirm({
      id: button.getAttribute("data-id"),
      status: button.getAttribute("data-status"),
      imageUrl: button.getAttribute("data-image") || "",
      customer: button.getAttribute("data-customer"),
      predicted: button.getAttribute("data-predicted"),
    });
  }

  function openRejectFromButton(button) {
    openRejectConfirm({
      id: button.getAttribute("data-id"),
      status: button.getAttribute("data-status"),
      imageUrl: button.getAttribute("data-image") || "",
      customer: button.getAttribute("data-customer"),
      predicted: button.getAttribute("data-predicted"),
    });
  }

  document.querySelectorAll(".ch-open").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.getAttribute("data-id");
      if (!id) return;
      loadDetail(id).catch((error) => {
        console.error("[customer-history] Open preview failed", error);
        window.alert(error.message || "Could not open review.");
      });
    });
  });

  document.querySelectorAll(".ch-approve").forEach((button) => {
    button.addEventListener("click", () => openApproveFromButton(button));
  });

  document.querySelectorAll(".ch-reject").forEach((button) => {
    button.addEventListener("click", () => openRejectFromButton(button));
  });

  document.getElementById("approveConfirmBtn")?.addEventListener("click", async () => {
    try {
      await runReview("approve", {
        confirmChange: pendingConfirmChange,
        errorEl: document.getElementById("approveError"),
        closeDialog: () => {
          if (approveDialog?.open) approveDialog.close();
        },
      });
    } catch (_error) {
      // Kept open with error message.
    }
  });

  document.getElementById("rejectConfirmBtn")?.addEventListener("click", async () => {
    try {
      await runReview("reject", {
        confirmChange: pendingConfirmChange,
        errorEl: document.getElementById("rejectError"),
        closeDialog: () => {
          if (rejectDialog?.open) rejectDialog.close();
        },
      });
    } catch (_error) {
      // Kept open with error message.
    }
  });

  document.getElementById("approveBtn")?.addEventListener("click", () => {
    submitFromPreview("approve");
  });
  document.getElementById("rejectBtn")?.addEventListener("click", () => {
    submitFromPreview("reject");
  });
})();
