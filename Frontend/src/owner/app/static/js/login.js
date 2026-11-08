(() => {
  const REMEMBER_EMAIL_KEY = "bc_owner_remember_email";
  const form = document.getElementById("loginForm");
  if (!form) return;

  const emailInput = document.getElementById("loginEmail") || form.querySelector('[name="email"]');
  const rememberInput = document.getElementById("loginRemember");

  function readRememberedEmail() {
    try {
      return (localStorage.getItem(REMEMBER_EMAIL_KEY) || "").trim();
    } catch (err) {
      return "";
    }
  }

  function writeRememberedEmail(email) {
    try {
      const value = String(email || "").trim();
      if (value) localStorage.setItem(REMEMBER_EMAIL_KEY, value);
      else localStorage.removeItem(REMEMBER_EMAIL_KEY);
    } catch (err) {
      /* private mode */
    }
  }

  const remembered = readRememberedEmail();
  if (emailInput && remembered && !String(emailInput.value || "").trim()) {
    emailInput.value = remembered;
    if (rememberInput) rememberInput.checked = true;
  }

  form.addEventListener("submit", (event) => {
    if (form.dataset.submitted === "1") {
      event.preventDefault();
      return;
    }
    const email = emailInput || form.querySelector('[name="email"]');
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

    const emailValue = email ? email.value.trim() : "";
    if (rememberInput && rememberInput.checked && emailValue) {
      writeRememberedEmail(emailValue);
    } else {
      writeRememberedEmail("");
    }

    form.dataset.submitted = "1";
  });
})();
