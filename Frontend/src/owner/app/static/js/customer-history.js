(function () {
  const page = document.querySelector(".ch-page");
  const modal = document.getElementById("reviewModal");
  const approveDialog = document.getElementById("approveDialog");
  const rejectDialog = document.getElementById("rejectDialog");
  const batchApproveDialog = document.getElementById("batchApproveDialog");
  const batchRejectDialog = document.getElementById("batchRejectDialog");
  const restoreDialog = document.getElementById("restoreDialog");
  const datasetDialog = document.getElementById("datasetDialog");
  if (!page) return;

  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  const apiBase =
    document.querySelector('meta[name="review-api-base"]')?.getAttribute("content") ||
    "/api/classifications";
  const panel =
    document.querySelector('meta[name="history-panel"]')?.getAttribute("content") ||
    page.getAttribute("data-panel") ||
    "pending";

  let currentId = null;
  let currentStatus = "pending_review";
  let pendingConfirmChange = false;
  let submitting = false;
  let pendingDatasetIds = [];
  let pendingBatchIds = [];
  const confirmButtonDefaults = {
    approveConfirmBtn: "Approve",
    rejectConfirmBtn: "Reject",
    batchApproveConfirmBtn: "Confirm Approval",
    batchRejectConfirmBtn: "Confirm Rejection",
    restoreConfirmBtn: "Move to Pending",
    datasetConfirmBtn: "Add to Dataset",
  };

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
    previewActions: document.getElementById("previewActions"),
    batchBar: document.getElementById("batchBar"),
    selectedCount: document.getElementById("selectedCount"),
    selectAll: document.getElementById("selectAllPage"),
  };

  function detailUrl(id) {
    return `${apiBase}/${encodeURIComponent(id)}`;
  }
  function actionUrl(id) {
    return `${apiBase}/${encodeURIComponent(id)}/review`;
  }
  function batchReviewUrl() {
    return `${apiBase}/review/batch`;
  }
  function batchDatasetUrl() {
    return `${apiBase}/dataset/batch`;
  }

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
    }, 3600);
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
      added_to_dataset: "In Dataset Pool",
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

  function eligibleChecks() {
    return Array.from(document.querySelectorAll(".ch-card-check")).filter(
      (input) => !input.disabled
    );
  }

  function selectedIds() {
    return eligibleChecks()
      .filter((input) => input.checked)
      .map((input) => input.value)
      .filter(Boolean);
  }

  function selectedDatasetIds() {
    return eligibleChecks()
      .filter(
        (input) =>
          input.checked &&
          (input.getAttribute("data-status") || "") === "approved"
      )
      .map((input) => input.value)
      .filter(Boolean);
  }

  function syncSelectionUi() {
    const ids = selectedIds();
    const checks = eligibleChecks();
    if (els.batchBar) {
      els.batchBar.hidden = ids.length === 0;
    }
    if (els.selectedCount) {
      els.selectedCount.textContent = String(ids.length);
    }
    if (els.selectAll) {
      els.selectAll.checked = checks.length > 0 && checks.every((c) => c.checked);
      els.selectAll.indeterminate =
        ids.length > 0 && ids.length < checks.length;
    }
    document.querySelectorAll(".ch-card").forEach((card) => {
      const check = card.querySelector(".ch-card-check");
      card.classList.toggle("is-selected", Boolean(check && check.checked));
    });
  }

  function clearSelection() {
    eligibleChecks().forEach((input) => {
      input.checked = false;
    });
    syncSelectionUi();
  }

  function removeCards(ids) {
    const idSet = new Set(ids);
    document.querySelectorAll(".ch-card").forEach((card) => {
      if (idSet.has(card.getAttribute("data-id"))) {
        card.remove();
      }
    });
    syncSelectionUi();
  }

  function setBusy(isBusy, action) {
    submitting = Boolean(isBusy);
    const buttons = document.querySelectorAll(
      ".ch-approve, .ch-reject, .ch-restore, #approveBtn, #rejectBtn, #approveConfirmBtn, #rejectConfirmBtn, #batchApproveBtn, #batchRejectBtn, #batchDatasetBtn, #batchRestoreBtn, #batchApproveConfirmBtn, #batchRejectConfirmBtn, #restoreConfirmBtn, #datasetConfirmBtn"
    );
    buttons.forEach((button) => {
      button.disabled = submitting;
    });
    const loadingLabels = {
      approve: {
        approveConfirmBtn: "Approving…",
        batchApproveConfirmBtn: "Approving…",
        approveBtn: "Approving…",
      },
      reject: {
        rejectConfirmBtn: "Rejecting…",
        batchRejectConfirmBtn: "Rejecting…",
        rejectBtn: "Rejecting…",
      },
      dataset: {
        datasetConfirmBtn: "Adding…",
      },
      restore: {
        restoreConfirmBtn: "Moving…",
      },
    };
    Object.entries(confirmButtonDefaults).forEach(([id, defaultLabel]) => {
      const button = document.getElementById(id);
      if (!button) return;
      const loading = submitting ? loadingLabels[action]?.[id] : null;
      button.textContent = loading || defaultLabel;
    });
    if (els.approveBtn && !submitting) els.approveBtn.textContent = "Approve";
    if (els.rejectBtn && !submitting) els.rejectBtn.textContent = "Reject";
    if (els.approveBtn && submitting && action === "approve") {
      els.approveBtn.textContent = "Approving…";
    }
    if (els.rejectBtn && submitting && action === "reject") {
      els.rejectBtn.textContent = "Rejecting…";
    }
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
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
    if (!response.ok && data.ok === false && !data.results) {
      const error = new Error(data.error || "Request failed.");
      error.status = response.status;
      error.payload = data;
      throw error;
    }
    if (!response.ok && !data.succeeded_count && !data.skipped_count) {
      const error = new Error(data.error || "Request failed.");
      error.status = response.status;
      error.payload = data;
      throw error;
    }
    return data;
  }

  async function submitReview(id, payload) {
    const data = await postJson(actionUrl(id), payload);
    if (!data.ok || !data.item) {
      const error = new Error(data.error || "Review could not be saved.");
      error.payload = data;
      throw error;
    }
    return data.item;
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
    if (els.previewActions) {
      const canReview = (item.review_status || "pending_review") === "pending_review";
      els.previewActions.hidden = panel !== "pending" && !canReview;
    }
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

  async function runReview(action, { confirmChange, errorEl, closeDialog } = {}) {
    if (!currentId || submitting) return;
    setBusy(true, action);
    showError(errorEl, "");
    try {
      const item = await submitReview(currentId, {
        action,
        confirm_change: Boolean(confirmChange),
      });
      fill(item);
      pendingConfirmChange = needsChangeConfirm(item.review_status);
      showToast(
        action === "approve" ? "Photo approved." : "Photo rejected.",
        action === "approve" ? "ok" : "bad"
      );
      if (typeof closeDialog === "function") closeDialog();
      if (panel === "pending") {
        removeCards([item.id]);
        if (action === "approve") {
          openDatasetPrompt([item.id], 1);
        }
      }
      return item;
    } catch (error) {
      console.error("[customer-history] Review failed", error);
      showError(errorEl, error.message || `${action} failed.`);
      throw error;
    } finally {
      setBusy(false);
    }
  }

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
      /* shown in panel */
    }
  }

  function openApproveConfirm({ id, status, imageUrl, customer, predicted }) {
    if (modal?.open) {
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
    if (approveDialog?.showModal) approveDialog.showModal();
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
    if (rejectDialog?.showModal) rejectDialog.showModal();
  }

  function openDatasetPrompt(ids, count) {
    pendingDatasetIds = Array.from(new Set(ids || []));
    if (!pendingDatasetIds.length || !datasetDialog?.showModal) return;
    const line = document.getElementById("datasetCountLine");
    if (line) {
      line.textContent = `You have approved ${count} photo${
        count === 1 ? "" : "s"
      }. Do you want to add these approved images to the dataset pool for future model training?`;
    }
    showError(document.getElementById("datasetError"), "");
    datasetDialog.showModal();
  }

  async function runBatch(action) {
    if (submitting) return;
    const ids = pendingBatchIds.length ? pendingBatchIds.slice() : selectedIds();
    if (!ids.length) {
      showToast("Select at least one photo.", "bad");
      return;
    }
    setBusy(true, action);
    const errorEl =
      action === "approve"
        ? document.getElementById("batchApproveError")
        : document.getElementById("batchRejectError");
    showError(errorEl, "");
    try {
      const data = await postJson(batchReviewUrl(), { action, ids });
      const succeeded = data.succeeded || [];
      const failed = data.failed || [];
      if (!succeeded.length && failed.length) {
        const first = failed[0]?.error || "Batch update failed.";
        throw new Error(first);
      }
      removeCards(succeeded);
      clearSelection();
      pendingBatchIds = [];
      if (batchApproveDialog?.open) batchApproveDialog.close();
      if (batchRejectDialog?.open) batchRejectDialog.close();
      showToast(
        action === "approve"
          ? `Approved ${succeeded.length} photo${succeeded.length === 1 ? "" : "s"}.`
          : `Rejected ${succeeded.length} photo${succeeded.length === 1 ? "" : "s"}.`,
        action === "approve" ? "ok" : "bad"
      );
      if (failed.length) {
        console.error("[customer-history] Partial batch failures", failed);
        showToast(`${failed.length} photo(s) could not be updated.`, "bad");
      }
      if (action === "approve" && succeeded.length) {
        openDatasetPrompt(succeeded, succeeded.length);
      } else if (!document.querySelector(".ch-card")) {
        window.location.reload();
      }
    } catch (error) {
      console.error("[customer-history] Batch failed", error);
      showError(errorEl, error.message || "Batch update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runDatasetBatch(ids) {
    const list = Array.from(new Set(ids || []));
    if (!list.length) return;
    setBusy(true, "dataset");
    const errorEl = document.getElementById("datasetError");
    showError(errorEl, "");
    try {
      const data = await postJson(batchDatasetUrl(), { ids: list });
      const added = data.succeeded_count || 0;
      const skipped = data.skipped_count || 0;
      const failed = data.failed || [];
      if (datasetDialog?.open) datasetDialog.close();
      if (panel === "approved") {
        removeCards(data.succeeded || []);
        clearSelection();
      }
      showToast(
        `Added ${added} to dataset pool${skipped ? ` (${skipped} already there)` : ""}.`,
        "ok"
      );
      if (failed.length) {
        console.error("[customer-history] Dataset partial failures", failed);
        showToast(`${failed.length} photo(s) could not be added.`, "bad");
      }
      pendingDatasetIds = [];
      if (panel === "approved" && !document.querySelector(".ch-card")) {
        window.location.reload();
      }
    } catch (error) {
      console.error("[customer-history] Dataset batch failed", error);
      showError(errorEl, error.message || "Could not add to dataset.");
    } finally {
      setBusy(false);
    }
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
    button.addEventListener("click", () => {
      openApproveConfirm({
        id: button.getAttribute("data-id"),
        status: button.getAttribute("data-status"),
        imageUrl: button.getAttribute("data-image") || "",
        customer: button.getAttribute("data-customer"),
        predicted: button.getAttribute("data-predicted"),
      });
    });
  });

  document.querySelectorAll(".ch-reject").forEach((button) => {
    button.addEventListener("click", () => {
      openRejectConfirm({
        id: button.getAttribute("data-id"),
        status: button.getAttribute("data-status"),
        imageUrl: button.getAttribute("data-image") || "",
        customer: button.getAttribute("data-customer"),
        predicted: button.getAttribute("data-predicted"),
      });
    });
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
      /* keep open */
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
      /* keep open */
    }
  });

  document.getElementById("approveBtn")?.addEventListener("click", () => {
    submitFromPreview("approve");
  });
  document.getElementById("rejectBtn")?.addEventListener("click", () => {
    submitFromPreview("reject");
  });

  document.querySelectorAll(".ch-card-check").forEach((input) => {
    input.addEventListener("change", syncSelectionUi);
  });

  els.selectAll?.addEventListener("change", () => {
    const checked = Boolean(els.selectAll.checked);
    eligibleChecks().forEach((input) => {
      input.checked = checked;
    });
    syncSelectionUi();
  });

  function selectAllApprovedForDataset({ openConfirm = true } = {}) {
    const targets = eligibleChecks().filter(
      (input) => (input.getAttribute("data-status") || "") === "approved"
    );
    if (!targets.length) {
      showToast("No approved photos on this page are waiting for the dataset pool.", "bad");
      return [];
    }
    eligibleChecks().forEach((input) => {
      input.checked = false;
    });
    targets.forEach((input) => {
      input.checked = true;
    });
    syncSelectionUi();
    const ids = selectedDatasetIds();
    if (openConfirm && ids.length) {
      openDatasetPrompt(ids, ids.length);
    }
    return ids;
  }

  document.getElementById("selectAllApprovedBtn")?.addEventListener("click", () => {
    selectAllApprovedForDataset({ openConfirm: true });
  });

  document.getElementById("clearSelectionBtn")?.addEventListener("click", clearSelection);

  document.getElementById("batchApproveBtn")?.addEventListener("click", () => {
    const ids = selectedIds();
    if (!ids.length) return;
    pendingBatchIds = ids.slice();
    const line = document.getElementById("batchApproveCountLine");
    if (line) {
      line.textContent = `${ids.length} photo${ids.length === 1 ? "" : "s"} will move to the Approved panel.`;
    }
    showError(document.getElementById("batchApproveError"), "");
    if (batchApproveDialog?.showModal) batchApproveDialog.showModal();
  });

  document.getElementById("batchRejectBtn")?.addEventListener("click", () => {
    const ids = selectedIds();
    if (!ids.length) return;
    pendingBatchIds = ids.slice();
    const line = document.getElementById("batchRejectCountLine");
    if (line) {
      line.textContent = `${ids.length} photo${ids.length === 1 ? "" : "s"} will move to the Rejected panel.`;
    }
    showError(document.getElementById("batchRejectError"), "");
    if (batchRejectDialog?.showModal) batchRejectDialog.showModal();
  });

  document.getElementById("batchApproveConfirmBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    runBatch("approve");
  });
  document.getElementById("batchRejectConfirmBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    runBatch("reject");
  });

  batchApproveDialog?.addEventListener("close", () => {
    if (!submitting) pendingBatchIds = [];
  });
  batchRejectDialog?.addEventListener("close", () => {
    if (!submitting) pendingBatchIds = [];
  });

  document.getElementById("batchDatasetBtn")?.addEventListener("click", () => {
    const ids = selectedDatasetIds();
    if (!ids.length) {
      showToast("Select approved photos that are not already in the dataset pool.", "bad");
      return;
    }
    openDatasetPrompt(ids, ids.length);
  });

  function openRestorePrompt(ids) {
    pendingBatchIds = Array.from(new Set(ids || []));
    if (!pendingBatchIds.length) return;
    const line = document.getElementById("restoreCountLine");
    if (line) {
      line.textContent = `${pendingBatchIds.length} photo${
        pendingBatchIds.length === 1 ? "" : "s"
      } will return to the Pending panel.`;
    }
    showError(document.getElementById("restoreError"), "");
    if (restoreDialog?.showModal) restoreDialog.showModal();
  }

  async function runRestoreBatch() {
    if (submitting) return;
    const ids = pendingBatchIds.length ? pendingBatchIds.slice() : selectedIds();
    if (!ids.length) {
      showToast("Select at least one photo.", "bad");
      return;
    }
    setBusy(true, "restore");
    const errorEl = document.getElementById("restoreError");
    showError(errorEl, "");
    try {
      const data = await postJson(batchReviewUrl(), { action: "restore", ids });
      const succeeded = data.succeeded || [];
      const failed = data.failed || [];
      if (!succeeded.length && failed.length) {
        throw new Error(failed[0]?.error || "Could not move photos to Pending.");
      }
      removeCards(succeeded);
      clearSelection();
      pendingBatchIds = [];
      if (restoreDialog?.open) restoreDialog.close();
      showToast(
        `Moved ${succeeded.length} photo${succeeded.length === 1 ? "" : "s"} to Pending.`,
        "ok"
      );
      if (failed.length) {
        console.error("[customer-history] Restore partial failures", failed);
        showToast(`${failed.length} photo(s) could not be moved.`, "bad");
      }
      if (!document.querySelector(".ch-card")) {
        window.location.reload();
      }
    } catch (error) {
      console.error("[customer-history] Restore failed", error);
      showError(errorEl, error.message || "Could not move photos to Pending.");
    } finally {
      setBusy(false);
    }
  }

  document.getElementById("batchRestoreBtn")?.addEventListener("click", () => {
    const ids = selectedIds();
    if (!ids.length) return;
    openRestorePrompt(ids);
  });

  document.querySelectorAll(".ch-restore").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.getAttribute("data-id");
      if (!id) return;
      openRestorePrompt([id]);
    });
  });

  document.getElementById("restoreConfirmBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    runRestoreBatch();
  });

  restoreDialog?.addEventListener("close", () => {
    if (!submitting) pendingBatchIds = [];
  });

  document.getElementById("datasetConfirmBtn")?.addEventListener("click", () => {
    const ids = pendingDatasetIds.length ? pendingDatasetIds : selectedDatasetIds();
    runDatasetBatch(ids);
  });

  document.getElementById("datasetNotNowBtn")?.addEventListener("click", () => {
    pendingDatasetIds = [];
  });

  syncSelectionUi();
})();
