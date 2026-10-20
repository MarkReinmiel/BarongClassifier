(() => {
  const form = document.getElementById("loginForm");
  if (!form) return;
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitted === "1") {
      event.preventDefault();
      return;
    }
    const email = form.querySelector('[name="email"]');
    const password = form.querySelector('[name="password"]');
    if (email && !email.value.trim()) {
      event.preventDefault();
      return;
    }
    if (password && password.value.length < 12) {
      event.preventDefault();
      const status = document.getElementById("loginStatus");
      if (status) status.textContent = "Use at least 12 characters for the password.";
      return;
    }
    form.dataset.submitted = "1";
  });
})();
