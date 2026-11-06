(function () {
  const apiBase =
    document.querySelector('meta[name="model-api-base"]')?.getAttribute("content") ||
    "/api/model-management";
  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  const dialog = document.getElementById("mmConfirmDialog");
  const errorEl = document.getElementById("mmError");
  const successEl = document.getElementById("mmSuccess");
  let pendingAction = null;
  let pollTimer = null;

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

  async function post(path, body) {
    const response = await fetch(`${apiBase}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrf,
      },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || data.message || "Request failed.");
    }
    return data;
  }

  async function get(path) {
    const response = await fetch(`${apiBase}${path}`, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || "Request failed.");
    }
    return data;
  }

  function askConfirm(title, body, action) {
    pendingAction = action;
    const titleEl = document.getElementById("mmConfirmTitle");
    const bodyEl = document.getElementById("mmConfirmBody");
    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.textContent = body;
    if (dialog?.showModal) dialog.showModal();
  }

  document.getElementById("mmConfirmOk")?.addEventListener("click", async () => {
    const action = pendingAction;
    pendingAction = null;
    if (dialog?.open) dialog.close();
    if (!action) return;
    showFlash(errorEl, "");
    showFlash(successEl, "");
    try {
      const result = await action();
      showFlash(successEl, result.message || "Done.");
      window.setTimeout(() => window.location.reload(), 900);
    } catch (error) {
      console.error("[model-management]", error);
      showFlash(errorEl, error.message || "Action failed.");
    }
  });

  document.getElementById("mmStartTrain")?.addEventListener("click", () => {
    askConfirm(
      "Train Next Revision?",
      "Creates the next revision under the current major version (for example v2.2 after v2.1). Production stays live and its weights are not overwritten.",
      () => post("/train", { retry: false, new_major: false })
    );
  });

  document.getElementById("mmStartMajor")?.addEventListener("click", () => {
    askConfirm(
      "Start New Major Version?",
      "Creates a new major generation (for example v3.1). Use this only for a significant new generation. Prefer Train Next Revision for routine dataset updates.",
      () => post("/train", { retry: false, new_major: true })
    );
  });

  document.getElementById("mmRetryTrain")?.addEventListener("click", () => {
    askConfirm(
      "Retry Training?",
      "Starts another revision under the current major. Previous logs and artifacts are preserved. Production weights stay unchanged.",
      () => post("/train", { retry: true, new_major: false })
    );
  });

  document.getElementById("mmEvaluate")?.addEventListener("click", () => {
    const versionId = document.getElementById("mmEvaluate")?.getAttribute("data-version-id");
    askConfirm(
      "Evaluate Candidate?",
      "Run held-out evaluation and compare against the production model. Failed evaluation blocks deployment.",
      () => post("/evaluate", { version_id: versionId || null })
    );
  });

  document.getElementById("mmDeploy")?.addEventListener("click", () => {
    const versionId = document.getElementById("mmDeploy")?.getAttribute("data-version-id");
    if (!versionId) return;
    askConfirm(
      "Approve and Deploy?",
      "This switches Customer and Owner inference to the candidate after a health check. The previous production model remains available for rollback.",
      () => post("/deploy", { version_id: versionId })
    );
  });

  document.getElementById("mmReject")?.addEventListener("click", () => {
    const versionId = document.getElementById("mmReject")?.getAttribute("data-version-id");
    if (!versionId) return;
    askConfirm(
      "Reject Candidate?",
      "Mark this candidate as rejected. Production stays on the current active model.",
      () => post("/reject", { version_id: versionId })
    );
  });

  document.getElementById("mmRollback")?.addEventListener("click", () => {
    askConfirm(
      "Rollback Production?",
      "Restore the previous working model version after verifying its artifacts. Current live model will be archived but kept.",
      () => post("/rollback", {})
    );
  });

  document.getElementById("mmViewLogs")?.addEventListener("click", async () => {
    const versionId = document.getElementById("mmViewLogs")?.getAttribute("data-version-id");
    try {
      const data = await get(`/logs${versionId ? `?version_id=${encodeURIComponent(versionId)}` : ""}`);
      const card = document.getElementById("mmLogCard");
      const body = document.getElementById("mmLogBody");
      if (body) body.textContent = data.log || "No log.";
      if (card) card.hidden = false;
    } catch (error) {
      showFlash(errorEl, error.message || "Could not load logs.");
    }
  });

  document.getElementById("mmHideLogs")?.addEventListener("click", () => {
    const card = document.getElementById("mmLogCard");
    if (card) card.hidden = true;
  });

  async function pollStatus() {
    try {
      const data = await get("/status");
      const job = data.active_job || {};
      const candidate = data.candidate || {};
      const pct = Number(job.progress_pct ?? candidate.progress_pct ?? 0);
      const statusEl = document.getElementById("mmJobStatus");
      const pctEl = document.getElementById("mmProgressPct");
      const msgEl = document.getElementById("mmProgressMsg");
      const bar = document.getElementById("mmProgressBar");
      if (statusEl) statusEl.textContent = job.status || candidate.job_status || "—";
      if (pctEl) pctEl.textContent = String(Math.round(pct));
      if (msgEl) msgEl.textContent = job.progress_message || candidate.progress_message || "—";
      if (bar) bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
      if (!job.status || !["queued", "running"].includes(job.status)) {
        if (pollTimer) window.clearInterval(pollTimer);
        pollTimer = null;
      }
    } catch (_error) {
      /* keep quiet while polling */
    }
  }

  const initialBusy = Boolean(
    document.getElementById("mmJobStatus")?.textContent?.match(/queued|running/i)
  );
  if (initialBusy) {
    pollTimer = window.setInterval(pollStatus, 4000);
  }
})();
