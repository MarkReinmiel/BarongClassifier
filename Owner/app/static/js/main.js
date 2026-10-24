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
  const root = document.querySelector("[data-profile]");
  if (!root) return;
  const button = root.querySelector("#profileBtn");
  const menu = root.querySelector("#profileMenu");
  if (!button || !menu) return;

  function setOpen(open) {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  button.addEventListener("click", function (event) {
    event.stopPropagation();
    setOpen(menu.hidden);
  });

  document.addEventListener("click", function (event) {
    if (!root.contains(event.target)) setOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setOpen(false);
  });
})();
