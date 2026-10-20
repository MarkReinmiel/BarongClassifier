(() => {
  const password = document.getElementById("newPassword");
  const meter = document.getElementById("strengthMeter");
  const label = document.getElementById("strengthLabel");
  if (!password || !meter) return;

  const score = (value) => {
    const length = value.length;
    const classes = [
      /[a-z]/.test(value),
      /[A-Z]/.test(value),
      /\d/.test(value),
      /[^A-Za-z0-9]/.test(value),
    ].filter(Boolean).length;
    if (length < 12 || classes < 2) return "weak";
    if (length >= 14 && classes >= 3) return "strong";
    return "medium";
  };

  password.addEventListener("input", () => {
    const level = score(password.value);
    meter.className = `strength ${level}`;
    if (label) label.textContent = level.charAt(0).toUpperCase() + level.slice(1);
  });
})();
