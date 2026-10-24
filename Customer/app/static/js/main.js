document.documentElement.classList.add("js");

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
