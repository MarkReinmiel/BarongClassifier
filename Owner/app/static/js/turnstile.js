(() => {
  function tokenFrom(form) {
    const input = form.querySelector('textarea[name="cf-turnstile-response"], input[name="cf-turnstile-response"]');
    return (input && input.value ? input.value : "").trim();
  }

  function showStatus(form, message) {
    const status =
      form.querySelector("#loginStatus") ||
      form.querySelector("[data-turnstile-status]") ||
      null;
    if (status) status.textContent = message || "";
  }

  document.querySelectorAll("form[data-require-turnstile]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!tokenFrom(form)) {
        event.preventDefault();
        showStatus(form, "Complete the human verification checkbox.");
        form.dataset.submitted = "0";
      }
    });
  });
})();
