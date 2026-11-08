(function () {
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    var input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
  }

  document.querySelectorAll(".pw-toggle").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById(button.dataset.target);
      if (!input) return;
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide" : "Show";
    });
  });

  function setLoading(button, loading, label) {
    if (!button) return;
    button.disabled = loading;
    if (loading) {
      button.dataset.label = button.textContent;
      button.innerHTML = '<span class="spin" aria-hidden="true"></span> Please wait...';
    } else {
      button.textContent = label || button.dataset.label || button.textContent;
    }
  }

  var REMEMBER_EMAIL_KEY = "bc_customer_remember_email";

  function readRememberedEmail() {
    try {
      return (localStorage.getItem(REMEMBER_EMAIL_KEY) || "").trim();
    } catch (err) {
      return "";
    }
  }

  function writeRememberedEmail(email) {
    try {
      var value = String(email || "").trim();
      if (value) localStorage.setItem(REMEMBER_EMAIL_KEY, value);
      else localStorage.removeItem(REMEMBER_EMAIL_KEY);
    } catch (err) {
      /* private mode */
    }
  }

  var loginForm = document.getElementById("loginForm");
  var loginBtn = document.getElementById("loginBtn");
  var loginEmail = document.getElementById("loginEmail");
  var loginRemember = document.getElementById("loginRemember");
  if (loginForm && loginEmail) {
    var remembered = readRememberedEmail();
    /* Prefill last email only when Remember me was used before */
    if (remembered && !loginEmail.value) {
      loginEmail.value = remembered;
      if (loginRemember) loginRemember.checked = true;
    }
  }
  if (loginForm && loginBtn) {
    loginForm.addEventListener("submit", function (event) {
      if (!loginForm.checkValidity()) return;
      // Don't lock the button if CSRF token is missing (would force a hard refresh).
      var csrf = loginForm.querySelector('input[name="csrf_token"]');
      if (!csrf || !csrf.value) {
        event.preventDefault();
        window.location.reload();
        return;
      }
      var emailValue = loginEmail ? loginEmail.value.trim() : "";
      if (loginRemember && loginRemember.checked && emailValue) {
        writeRememberedEmail(emailValue);
      } else {
        writeRememberedEmail("");
      }
      setLoading(loginBtn, true);
    });
  }
  var registerForm = document.getElementById("registerForm");
  var registerBtn = document.getElementById("registerBtn");
  if (registerForm && registerBtn) {
    registerForm.addEventListener("submit", function (event) {
      if (!registerForm.checkValidity()) return;
      var csrf = registerForm.querySelector('input[name="csrf_token"]');
      if (!csrf || !csrf.value) {
        event.preventDefault();
        window.location.reload();
        return;
      }
      setLoading(registerBtn, true);
    });
  }

  // After Back/forward cache or a failed 400, unlock buttons so user can retry.
  window.addEventListener("pageshow", function () {
    if (loginBtn) setLoading(loginBtn, false, "Sign in");
    if (registerBtn) setLoading(registerBtn, false, "Create account");
  });

  var otp = document.getElementById("otp");
  if (!otp) return;

  var inputs = Array.prototype.slice.call(otp.querySelectorAll("input"));
  var status = document.getElementById("verifyStatus");
  var verifyBtn = document.getElementById("verifyBtn");
  var resendBtn = document.getElementById("resendBtn");
  var purpose = otp.dataset.purpose || "registration";
  var timerId = null;
  var remaining = Number(otp.dataset.resend || 0);
  var submitting = false;

  function show(message, type) {
    if (!status) return;
    status.textContent = message || "";
    status.className = "status " + (type || "");
  }

  function codeValue() {
    return inputs.map(function (input) { return input.value; }).join("");
  }

  function formatWait(seconds) {
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  function tick() {
    remaining -= 1;
    if (remaining <= 0) {
      clearInterval(timerId);
      timerId = null;
      resendBtn.disabled = false;
      resendBtn.textContent = "Resend Verification Email";
      return;
    }
    resendBtn.disabled = true;
    resendBtn.textContent = "Resend code in " + formatWait(remaining);
  }

  function startCountdown(seconds) {
    clearInterval(timerId);
    remaining = Math.max(0, Number(seconds) || 0);
    if (remaining <= 0) {
      resendBtn.disabled = false;
      resendBtn.textContent = "Resend Verification Email";
      return;
    }
    resendBtn.disabled = true;
    resendBtn.textContent = "Resend code in " + formatWait(remaining);
    timerId = setInterval(tick, 1000);
  }

  fetch("/auth/verification-status?purpose=" + encodeURIComponent(purpose), {
    headers: { Accept: "application/json" },
    credentials: "same-origin"
  })
    .then(function (response) { return response.json().then(function (payload) { return { ok: response.ok, payload: payload }; }); })
    .then(function (result) {
      if (!result.ok) {
        show(result.payload.error || "Verification session expired.", "error");
        startCountdown(0);
        return;
      }
      startCountdown(result.payload.resend_after_seconds || 0);
    })
    .catch(function () {
      startCountdown(remaining || 60);
    });

  inputs.forEach(function (input, index) {
    input.addEventListener("input", function () {
      input.value = input.value.replace(/\D/g, "").slice(0, 1);
      if (input.value && index < inputs.length - 1) inputs[index + 1].focus();
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Backspace" && !input.value && index > 0) inputs[index - 1].focus();
    });
    input.addEventListener("paste", function (event) {
      var text = (event.clipboardData || window.clipboardData).getData("text") || "";
      var digits = text.replace(/\D/g, "").slice(0, 6);
      if (!digits) return;
      event.preventDefault();
      digits.split("").forEach(function (digit, i) {
        if (inputs[i]) inputs[i].value = digit;
      });
      inputs[Math.min(digits.length, 5)].focus();
    });
  });

  verifyBtn.addEventListener("click", async function () {
    if (submitting) return;
    var code = codeValue();
    if (!/^\d{6}$/.test(code)) {
      show("Enter the six-digit code from your email.", "error");
      return;
    }
    submitting = true;
    setLoading(verifyBtn, true);
    show("Checking the code...", "");
    var verified = false;
    try {
      var response = await fetch("/auth/verify-code", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRFToken": csrfToken()
        },
        body: JSON.stringify({ code: code, purpose: purpose })
      });
      if (response.redirected) {
        window.location.href = response.url;
        return;
      }
      var payload = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        show(payload.error || "That code could not be verified.", "error");
        return;
      }
      verified = true;
      show("Verified.", "success");
      var finish = function () {
        if (purpose === "registration") {
          var modal = document.getElementById("successModal");
          if (modal) modal.classList.add("open");
          show("Email verified successfully.", "success");
          submitting = false;
          setLoading(verifyBtn, false, "Verify Email");
          return;
        }
        window.location.href = payload.redirect || "/dashboard";
      };
      if (typeof window.bcStackOtp === "function") {
        window.bcStackOtp(otp, finish);
      } else {
        finish();
      }
    } catch (error) {
      show("The server could not be reached.", "error");
    } finally {
      if (!verified) {
        submitting = false;
        setLoading(verifyBtn, false, purpose === "device" ? "Verify Device" : "Verify Email");
      }
    }
  });

  resendBtn.addEventListener("click", async function () {
    if (resendBtn.disabled || submitting) return;
    resendBtn.disabled = true;
    show("Sending a new code...", "");
    try {
      var response = await fetch("/auth/resend-code", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRFToken": csrfToken()
        },
        body: JSON.stringify({ purpose: purpose })
      });
      var payload = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        show(payload.error || "A new code was not sent.", "error");
        startCountdown(payload.retry_after_seconds || (response.status === 429 ? 60 : 0));
        return;
      }
      show("A new code was sent. It expires in 24 hours.", "success");
      startCountdown(payload.resend_after_seconds || 60);
    } catch (error) {
      show("The server could not be reached. A new code was not sent.", "error");
      resendBtn.disabled = false;
      resendBtn.textContent = "Resend Verification Email";
    }
  });
})();
