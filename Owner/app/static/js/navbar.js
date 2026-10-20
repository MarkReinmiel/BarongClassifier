document.addEventListener("DOMContentLoaded", () => {
  const navbar = document.getElementById("ownerNavbar") || document.querySelector(".navbar");
  const accountButton = document.getElementById("accountButton");
  const accountDropdown = document.getElementById("accountDropdown");
  const menuToggle = document.getElementById("menuToggle");

  function setMenuOpen(isOpen) {
    if (!navbar || !menuToggle) return;
    navbar.classList.toggle("is-open", isOpen);
    document.body.classList.toggle("nav-open", isOpen);
    menuToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }

  if (accountButton && accountDropdown) {
    accountButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = accountDropdown.hasAttribute("hidden");
      if (open) accountDropdown.removeAttribute("hidden");
      else accountDropdown.setAttribute("hidden", "");
      accountButton.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  if (menuToggle && navbar) {
    menuToggle.addEventListener("click", (event) => {
      event.stopPropagation();
      setMenuOpen(!navbar.classList.contains("is-open"));
    });
  }

  document.addEventListener("click", (event) => {
    if (
      accountDropdown &&
      accountButton &&
      !accountButton.contains(event.target) &&
      !accountDropdown.contains(event.target)
    ) {
      accountDropdown.setAttribute("hidden", "");
      accountButton.setAttribute("aria-expanded", "false");
    }
  });
});
