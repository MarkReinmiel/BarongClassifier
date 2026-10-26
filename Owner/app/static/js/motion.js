(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function parseDisplay(text) {
    var raw = String(text || "").trim();
    var match = raw.match(/^([^\d-]*)(-?\d+(?:\.\d+)?)(.*)$/);
    if (!match) return null;
    var digits = match[2];
    return {
      prefix: match[1],
      value: Number(digits),
      suffix: match[3],
      decimals: (digits.split(".")[1] || "").length,
      pad: /^0\d+$/.test(digits) ? digits.length : 0
    };
  }

  function formatNum(parsed, value) {
    var shown;
    if (parsed.decimals) {
      shown = value.toFixed(parsed.decimals);
    } else {
      shown = String(Math.round(value));
      if (parsed.pad) shown = shown.padStart(parsed.pad, "0");
    }
    return parsed.prefix + shown + parsed.suffix;
  }

  function animateNum(el) {
    if (!el || el.dataset.motionDone === "1") return;
    var parsed = parseDisplay(el.textContent);
    if (!parsed || !isFinite(parsed.value)) return;
    el.dataset.motionDone = "1";
    if (reduce) return;

    var to = parsed.value;
    var fromAttr = el.getAttribute("data-from");
    var from = fromAttr != null && fromAttr !== "" ? Number(fromAttr) : 0;
    if (!isFinite(from)) from = 0;

    el.classList.add("is-counting");
    el.textContent = formatNum(parsed, from);

    var start = performance.now();
    var duration = Math.min(1400, Math.max(600, Math.abs(to - from) * 40));
    function frame(now) {
      var t = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - t, 3);
      var current = from + (to - from) * eased;
      el.textContent = formatNum(parsed, current);
      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        el.textContent = formatNum(parsed, to);
        el.classList.remove("is-counting");
      }
    }
    requestAnimationFrame(frame);
  }

  function bootNumbers(root) {
    (root || document).querySelectorAll(".num").forEach(animateNum);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { bootNumbers(document); });
  } else {
    bootNumbers(document);
  }

  window.bcMotion = { animateNum: animateNum, bootNumbers: bootNumbers };
})();
