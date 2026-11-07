document.documentElement.classList.add("js");

(function () {
  const profileRoot = document.querySelector("[data-profile]");
  const profileBtn = profileRoot && profileRoot.querySelector("#profileBtn");
  const profileMenu = profileRoot && profileRoot.querySelector("#profileMenu");

  const topMenuRoot = document.querySelector("[data-top-menu]");
  const topMenuBtn = topMenuRoot && topMenuRoot.querySelector("#topMenuBtn");
  const topMenuPanel = topMenuRoot && topMenuRoot.querySelector("#topMenuPanel");

  function setProfileOpen(open) {
    if (!profileBtn || !profileMenu) return;
    profileMenu.hidden = !open;
    profileBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function setTopMenuOpen(open) {
    if (!topMenuBtn || !topMenuPanel) return;
    topMenuPanel.hidden = !open;
    topMenuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeAllMenus() {
    setProfileOpen(false);
    setTopMenuOpen(false);
  }

  if (profileBtn && profileMenu) {
    profileBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const willOpen = profileMenu.hidden;
      setTopMenuOpen(false);
      setProfileOpen(willOpen);
    });
  }

  if (topMenuBtn && topMenuPanel) {
    topMenuBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const willOpen = topMenuPanel.hidden;
      setProfileOpen(false);
      setTopMenuOpen(willOpen);
    });
  }

  document.addEventListener("click", function (event) {
    if (profileRoot && !profileRoot.contains(event.target)) setProfileOpen(false);
    if (topMenuRoot && !topMenuRoot.contains(event.target)) setTopMenuOpen(false);
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
    closeAllMenus();
    if (logoutDialog?.showModal) logoutDialog.showModal();
  });

  logoutOk?.addEventListener("click", function () {
    if (logoutForm) logoutForm.submit();
  });
})();
