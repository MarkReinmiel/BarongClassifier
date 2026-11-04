(() => {
  const form = document.getElementById("verifyResetForm");
  const hidden = document.getElementById("codeHidden");
  const inputs = Array.from(document.querySelectorAll(".otp input"));
  const resendBtn = document.getElementById("resendBtn");

  function syncCode() {
    if (hidden) hidden.value = inputs.map((el) => (el.value || "").trim()).join("");
  }

  inputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      input.value = input.value.replace(/\D/g, "").slice(0, 1);
      if (input.value && index < inputs.length - 1) inputs[index + 1].focus();
      syncCode();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !input.value && index > 0) {
        inputs[index - 1].focus();
      }
    });
    input.addEventListener("paste", (event) => {
      const text = (event.clipboardData || window.clipboardData).getData("text") || "";
      const digits = text.replace(/\D/g, "").slice(0, inputs.length);
      if (!digits) return;
      event.preventDefault();
      digits.split("").forEach((digit, i) => {
        if (inputs[i]) inputs[i].value = digit;
      });
      const focusAt = Math.min(digits.length, inputs.length - 1);
      inputs[focusAt].focus();
      syncCode();
    });
  });

  if (form) {
    form.addEventListener("submit", () => syncCode());
  }

  if (resendBtn) {
    let wait = Number(resendBtn.getAttribute("data-wait") || 0);
    const tick = () => {
      if (wait <= 0) {
        resendBtn.disabled = false;
        resendBtn.textContent = "Resend code";
        return;
      }
      resendBtn.disabled = true;
      const mins = String(Math.floor(wait / 60)).padStart(2, "0");
      const secs = String(wait % 60).padStart(2, "0");
      resendBtn.textContent = `Resend code in ${mins}:${secs}`;
      wait -= 1;
      window.setTimeout(tick, 1000);
    };
    tick();
  }
})();
