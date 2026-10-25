(() => {
  function tokenFrom(form) {
    const input = form.querySelector('textarea[name="cf-turnstile-response"], input[name="cf-turnstile-response"]');
    return (input && input.value ? input.value : "").trim();
  }

  function showStatus(form, message) {
    let status = form.querySelector("[data-turnstile-status]");
    if (!status) {
      status = document.createElement("p");
      status.className = "sm";
      status.setAttribute("data-turnstile-status", "1");
      status.style.color = "var(--err, #b42318)";
      status.style.minHeight = "18px";
      status.style.margin = "0 0 8px";
      const btn = form.querySelector('button[type="submit"]');
      if (btn) form.insertBefore(status, btn);
      else form.appendChild(status);
    }
    status.textContent = message || "";
  }

  document.querySelectorAll("form[data-require-turnstile]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!tokenFrom(form)) {
        event.preventDefault();
        showStatus(form, "Complete the human verification checkbox.");
      }
    });
  });
})();
