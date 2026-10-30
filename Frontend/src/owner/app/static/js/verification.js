(() => {
  const boxes = Array.from(document.querySelectorAll(".otp input"));
  if (!boxes.length) return;

  const syncHidden = () => {
    const hidden = document.getElementById("codeHidden");
    if (hidden) hidden.value = boxes.map((b) => b.value).join("");
  };

  boxes.forEach((box, index) => {
    box.addEventListener("input", () => {
      box.value = box.value.replace(/\D/g, "").slice(0, 1);
      if (box.value && index < boxes.length - 1) boxes[index + 1].focus();
      syncHidden();
    });
    box.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !box.value && index > 0) {
        boxes[index - 1].focus();
      }
    });
    box.addEventListener("paste", (event) => {
      event.preventDefault();
      const text = (event.clipboardData || window.clipboardData).getData("text") || "";
      const digits = text.replace(/\D/g, "").slice(0, boxes.length).split("");
      digits.forEach((digit, i) => {
        boxes[i].value = digit;
      });
      const focusAt = Math.min(digits.length, boxes.length - 1);
      boxes[focusAt].focus();
      syncHidden();
    });
  });

  const resend = document.getElementById("resendBtn");
  let wait = Number(resend?.dataset.wait || 0);
  const tick = () => {
    if (!resend) return;
    if (wait <= 0) {
      resend.disabled = false;
      resend.textContent = "Resend code";
      return;
    }
    resend.disabled = true;
    resend.textContent = `Resend in ${wait}s`;
    wait -= 1;
    setTimeout(tick, 1000);
  };
  if (resend && wait > 0) tick();
})();
