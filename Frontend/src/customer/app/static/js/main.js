document.documentElement.classList.add("js");

(function () {
  const profileRoot = document.querySelector("[data-profile]");
  const profileBtn = profileRoot && profileRoot.querySelector("#profileBtn");
  const profileMenu = profileRoot && profileRoot.querySelector("#profileMenu");

  const topMenuRoot = document.querySelector("[data-top-menu]");
  const topMenuBtn = topMenuRoot && topMenuRoot.querySelector("#topMenuBtn");
  const topMenuPanel = topMenuRoot && topMenuRoot.querySelector("#topMenuPanel");

  const navDdRoot = document.querySelector("[data-nav-dd]");
  const navDdBtn = navDdRoot && navDdRoot.querySelector("#navHomeBtn");
  const navDdMenu = navDdRoot && navDdRoot.querySelector("#navHomeMenu");

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

  function setNavDdOpen(open) {
    if (!navDdBtn || !navDdMenu) return;
    navDdMenu.hidden = !open;
    navDdBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeAllMenus() {
    setProfileOpen(false);
    setTopMenuOpen(false);
    setNavDdOpen(false);
  }

  if (profileBtn && profileMenu) {
    profileBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const willOpen = profileMenu.hidden;
      setTopMenuOpen(false);
      setNavDdOpen(false);
      setProfileOpen(willOpen);
    });
  }

  if (topMenuBtn && topMenuPanel) {
    topMenuBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const willOpen = topMenuPanel.hidden;
      setProfileOpen(false);
      setNavDdOpen(false);
      setTopMenuOpen(willOpen);
    });
  }

  if (navDdBtn && navDdMenu) {
    navDdBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      const willOpen = navDdMenu.hidden;
      setProfileOpen(false);
      setTopMenuOpen(false);
      setNavDdOpen(willOpen);
    });
  }

  document.addEventListener("click", function (event) {
    if (profileRoot && !profileRoot.contains(event.target)) setProfileOpen(false);
    if (topMenuRoot && !topMenuRoot.contains(event.target)) setTopMenuOpen(false);
    if (navDdRoot && !navDdRoot.contains(event.target)) setNavDdOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeAllMenus();
  });
})();
