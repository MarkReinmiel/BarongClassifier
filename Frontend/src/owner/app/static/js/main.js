document.addEventListener("click", (event) => {
  const toggle = event.target.closest(".pw-toggle, .password-toggle");
  if (!toggle) return;
  const input = document.getElementById(toggle.dataset.target);
  if (!input) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  toggle.textContent = show ? "Hide" : "Show";
});

document.querySelectorAll("form[data-loading]").forEach((form) => {
  form.addEventListener("submit", () => {
    const btn = form.querySelector('[type="submit"]');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    if (!btn.querySelector(".spin")) {
      const spin = document.createElement("span");
      spin.className = "spin";
      spin.setAttribute("aria-hidden", "true");
      btn.prepend(spin);
    }
  });
});

(function () {
  const profileRoot = document.querySelector("[data-profile]");
  const profileBtn = profileRoot?.querySelector("#profileBtn");
  const profileMenu = profileRoot?.querySelector("#profileMenu");
  const modelsRoot = document.querySelector("[data-nav-dd]");
  const modelsBtn = modelsRoot?.querySelector("#modelsNavBtn");
  const modelsMenu = modelsRoot?.querySelector("#modelsNavMenu");
  const historyTopRoot = document.querySelector("[data-history-top-dd]");
  const historyTopBtn = historyTopRoot?.querySelector("#historyTopNavBtn");
  const historyTopMenu = historyTopRoot?.querySelector("#historyTopNavMenu");
  const historyBottomRoot = document.querySelector("[data-history-dd]");
  const historyBottomBtn = historyBottomRoot?.querySelector("#historyNavBtn");
  const historyBottomMenu = historyBottomRoot?.querySelector("#historyNavMenu");

  function setProfileOpen(open) {
    if (!profileBtn || !profileMenu) return;
    profileMenu.hidden = !open;
    profileBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function setModelsOpen(open) {
    if (!modelsBtn || !modelsMenu) return;
    modelsMenu.hidden = !open;
    modelsBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function setHistoryTopOpen(open) {
    if (!historyTopBtn || !historyTopMenu) return;
    historyTopMenu.hidden = !open;
    historyTopBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function setHistoryBottomOpen(open) {
    if (!historyBottomBtn || !historyBottomMenu) return;
    historyBottomMenu.hidden = !open;
    historyBottomBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeAllMenus() {
    setProfileOpen(false);
    setModelsOpen(false);
    setHistoryTopOpen(false);
    setHistoryBottomOpen(false);
  }

  if (profileBtn && profileMenu) {
    profileBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const next = profileMenu.hidden;
      setModelsOpen(false);
      setHistoryTopOpen(false);
      setHistoryBottomOpen(false);
      setProfileOpen(next);
    });
  }

  if (modelsBtn && modelsMenu) {
    modelsBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const next = modelsMenu.hidden;
      setProfileOpen(false);
      setHistoryTopOpen(false);
      setHistoryBottomOpen(false);
      setModelsOpen(next);
    });
  }

  if (historyTopBtn && historyTopMenu) {
    historyTopBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const next = historyTopMenu.hidden;
      setProfileOpen(false);
      setModelsOpen(false);
      setHistoryBottomOpen(false);
      setHistoryTopOpen(next);
    });
  }

  if (historyBottomBtn && historyBottomMenu) {
    historyBottomBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const next = historyBottomMenu.hidden;
      setProfileOpen(false);
      setModelsOpen(false);
      setHistoryTopOpen(false);
      setHistoryBottomOpen(next);
    });
  }

  document.addEventListener("click", function (event) {
    if (profileRoot && !profileRoot.contains(event.target)) setProfileOpen(false);
    if (modelsRoot && !modelsRoot.contains(event.target)) setModelsOpen(false);
    if (historyTopRoot && !historyTopRoot.contains(event.target)) setHistoryTopOpen(false);
    if (historyBottomRoot && !historyBottomRoot.contains(event.target)) setHistoryBottomOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeAllMenus();
  });

  const logoutForm = document.getElementById("logoutForm");
  const logoutOpen = document.getElementById("logoutConfirmOpen");
  const logoutDialog = document.getElementById("logoutConfirmDialog");
  const logoutOk = document.getElementById("logoutConfirmOk");

  logoutOpen?.addEventListener("click", function (event) {
    event.preventDefault();
    event.stopPropagation();
    setProfileOpen(false);
    if (logoutDialog?.showModal) logoutDialog.showModal();
  });

  logoutOk?.addEventListener("click", function () {
    if (logoutForm) logoutForm.submit();
  });
})();
