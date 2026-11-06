(function () {
  const apiBase =
    document.querySelector('meta[name="model-api-base"]')?.getAttribute("content") ||
    "/api/model-management";
  const csrf =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  const dialog = document.getElementById("mmConfirmDialog");
  const errorEl = document.getElementById("mmError");
  const successEl = document.getElementById("mmSuccess");
  const lockNoteEl = document.getElementById("mmLockNote");
  let pendingAction = null;
  let pollTimer = null;
  let lastJobStatus = (
    document.getElementById("mmJobStatus")?.textContent || ""
  )
    .trim()
    .toLowerCase();

  let buttonNotes = {};
  try {
    const raw = document.getElementById("mmButtonNotes")?.textContent || "{}";
    buttonNotes = JSON.parse(raw);
  } catch (_error) {
    buttonNotes = {};
  }

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

  function showLockNote(message) {
    showFlash(lockNoteEl, message);
    showFlash(errorEl, message);
    if (lockNoteEl) {
      lockNoteEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function isEnabled(button) {
    return button?.getAttribute("data-enabled") === "1";
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
    showFlash(lockNoteEl, "");
    try {
      const result = await action();
      showFlash(successEl, result.message || "Done.");
      window.setTimeout(() => window.location.reload(), 900);
    } catch (error) {
      console.error("[model-management]", error);
      showFlash(errorEl, error.message || "Action failed.");
    }
  });

  const actions = {
    start_train: () =>
      askConfirm(
        "Train / Retrain?",
        "If a cancelled/rejected candidate exists, this reuses the same revision number (e.g. stays v1.2) and overwrites its weights to save disk. A new revision number is created only when needed. Production stays live.",
        () => post("/train", { retry: false, new_major: false })
      ),
    start_major: () =>
      askConfirm(
        "Start New Major Version?",
        "Creates a new major generation with the current live dataset pool. Prefer Train Next Revision for routine updates.",
        () => post("/train", { retry: false, new_major: true })
      ),
    retry: () =>
      askConfirm(
        "Retry Training?",
        "Reuses the same revision slot (e.g. v1.2 again), refreshes training data from the live dataset pool, and overwrites the old candidate weights. Production stays unchanged.",
        () => post("/train", { retry: true, new_major: false })
      ),
    evaluate: (button) => {
      const versionId = button.getAttribute("data-version-id");
      askConfirm(
        "Re-evaluate Candidate?",
        "Re-check held-out metrics against the minimum accuracy gate. Failed evaluation blocks deployment.",
        () => post("/evaluate", { version_id: versionId || null })
      );
    },
    deploy: (button) => {
      const versionId = button.getAttribute("data-version-id");
      if (!versionId) {
        showLockNote("Missing candidate id for deploy.");
        return;
      }
      askConfirm(
        "Approve and Deploy?",
        "Switches Customer and Owner inference to this candidate after a health check. Previous production stays available to restore.",
        () => post("/deploy", { version_id: versionId })
      );
    },
    cancel: (button) => {
      const versionId = button.getAttribute("data-version-id");
      if (!versionId) {
        showLockNote("Missing candidate id for cancel.");
        return;
      }
      askConfirm(
        "Cancel Training?",
        "Stops the running job and rejects this candidate. Then you can Train Next Revision with the latest dataset pool.",
        () => post("/reject", { version_id: versionId })
      );
    },
    reject: (button) => {
      const versionId = button.getAttribute("data-version-id");
      if (!versionId) {
        showLockNote("Missing candidate id for reject.");
        return;
      }
      askConfirm(
        "Reject Candidate?",
        "Archives this candidate and unlocks Train Next Revision / Retry with the latest dataset pool.",
        () => post("/reject", { version_id: versionId })
      );
    },
    rollback: () =>
      askConfirm(
        "Restore Previous Production?",
        "Restores the last archived previously-deployed production model. Current live model is kept in history.",
        () => post("/rollback", {})
      ),
    restore_version: (button) => {
      const versionId = button.getAttribute("data-version-id");
      if (!versionId) {
        showLockNote("Missing version id to restore.");
        return;
      }
      askConfirm(
        "Restore This Archived Model?",
        "Makes this previously deployed revision live again. Current production is archived but kept.",
        () => post("/restore", { version_id: versionId })
      );
    },
    view_logs: async (button) => {
      const versionId = button.getAttribute("data-version-id");
      try {
        const data = await get(
          `/logs${versionId ? `?version_id=${encodeURIComponent(versionId)}` : ""}`
        );
        const card = document.getElementById("mmLogCard");
        const body = document.getElementById("mmLogBody");
        if (body) body.textContent = data.log || "No log.";
        if (card) card.hidden = false;
        showFlash(lockNoteEl, "");
        showFlash(errorEl, "");
      } catch (error) {
        showLockNote(error.message || "Could not load logs.");
      }
    },
  };

  document.querySelectorAll(".mm-action").forEach((button) => {
    button.addEventListener("click", (event) => {
      const actionKey = button.getAttribute("data-action");
      if (!isEnabled(button)) {
        event.preventDefault();
        const note =
          buttonNotes[actionKey] ||
          button.getAttribute("title") ||
          "This action is not available in the current state.";
        showLockNote(note);
        return;
      }
      showFlash(lockNoteEl, "");
      showFlash(errorEl, "");
      const handler = actions[actionKey];
      if (!handler) {
        showLockNote("Unknown action.");
        return;
      }
      handler(button);
    });
  });

  document.getElementById("mmHideLogs")?.addEventListener("click", () => {
    const card = document.getElementById("mmLogCard");
    if (card) card.hidden = true;
  });

  function setTrainingUi({ busy, pct, status, message, candidateStatus }) {
    const card = document.getElementById("mmCandidateCard");
    const block = document.getElementById("mmLoadingBlock");
    const label = document.getElementById("mmLoadingLabel");
    const loadingPct = document.getElementById("mmLoadingPct");
    const loadingMsg = document.getElementById("mmLoadingMsg");
    const track = document.getElementById("mmProgressTrack");
    const bar = document.getElementById("mmProgressBar");
    const statusEl = document.getElementById("mmJobStatus");
    const pctEl = document.getElementById("mmProgressPct");
    const msgEl = document.getElementById("mmProgressMsg");
    const badge = document.getElementById("mmCandidateBadge");
    const safePct = Math.max(0, Math.min(100, Math.round(pct || 0)));

    if (card) card.classList.toggle("is-training", busy);
    if (block) {
      block.hidden = !busy;
      block.classList.toggle("is-idle", !busy);
    }
    if (label) label.textContent = busy ? "Processing training…" : "Training idle";
    if (loadingPct) loadingPct.textContent = `${safePct}%`;
    if (loadingMsg) loadingMsg.textContent = message || (busy ? "Waiting for worker updates…" : "—");
    if (statusEl) statusEl.textContent = status || "—";
    if (pctEl) pctEl.textContent = String(safePct);
    if (msgEl) msgEl.textContent = message || "—";
    if (bar) bar.style.width = `${safePct}%`;
    if (track) {
      track.setAttribute("aria-valuenow", String(safePct));
      track.classList.toggle("is-indeterminate", busy && safePct < 5);
    }
    if (badge && candidateStatus) {
      badge.textContent = String(candidateStatus).replace(/_/g, " ");
      badge.className = `mm-badge mm-badge--${candidateStatus}`;
    }
  }

  async function pollStatus() {
    try {
      const data = await get("/status");
      const job = data.active_job || {};
      const candidate = data.candidate || {};
      const pct = Number(job.progress_pct ?? candidate.progress_pct ?? 0);
      const status = (job.status || candidate.job_status || "").toLowerCase();
      const candStatus = (candidate.status || "").toLowerCase();
      const message = job.progress_message || candidate.progress_message || "";
      const busy =
        ["queued", "running"].includes(status) ||
        ["training", "queued"].includes(candStatus);

      setTrainingUi({
        busy,
        pct,
        status: job.status || candidate.job_status || "—",
        message,
        candidateStatus: candidate.status || candStatus || "idle",
      });

      if (!busy) {
        if (pollTimer) window.clearInterval(pollTimer);
        pollTimer = null;
        if (["queued", "running", "training"].includes(lastJobStatus)) {
          window.setTimeout(() => window.location.reload(), 700);
        }
      }
      lastJobStatus = status || candStatus || lastJobStatus;
    } catch (_error) {
      /* keep quiet while polling */
    }
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = window.setInterval(pollStatus, 2500);
    pollStatus();
  }

  const initialBusy = Boolean(
    document.getElementById("mmCandidateCard")?.classList.contains("is-training") ||
      document.getElementById("mmJobStatus")?.textContent?.match(/queued|running|training/i)
  );
  if (initialBusy) {
    startPolling();
  }

  // After confirming Train/Retry, keep the loading UI alive until reload.
  const originalConfirm = document.getElementById("mmConfirmOk");
  if (originalConfirm) {
    originalConfirm.addEventListener(
      "click",
      () => {
        const actionTitle =
          document.getElementById("mmConfirmTitle")?.textContent || "";
        if (/train|retry/i.test(actionTitle)) {
          setTrainingUi({
            busy: true,
            pct: 1,
            status: "queued",
            message: "Starting training process…",
            candidateStatus: "training",
          });
          startPolling();
        }
      },
      true
    );
  }
})();
