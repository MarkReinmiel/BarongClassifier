(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- Splash → landing ---- */
  var splash = document.getElementById("appSplash");
  var landing = document.querySelector(".auth-shell--hero");
  if (splash) {
    var seen = false;
    try { seen = sessionStorage.getItem("bc_splash_seen") === "1"; } catch (e) {}
    if (reduce || seen) {
      splash.classList.add("is-done");
      if (landing) landing.classList.add("is-ready");
    } else {
      if (landing) landing.classList.add("is-waiting");
      window.setTimeout(function () {
        splash.classList.add("is-done");
        if (landing) {
          landing.classList.remove("is-waiting");
          landing.classList.add("is-ready");
        }
        try { sessionStorage.setItem("bc_splash_seen", "1"); } catch (e) {}
      }, reduce ? 0 : 1400);
    }
  } else if (landing) {
    landing.classList.add("is-ready");
  }

  /* ---- Count-up / count-down ---- */
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
  bootNumbers(document);
  window.bcMotion = { animateNum: animateNum, bootNumbers: bootNumbers };

  /* ---- OTP success: reverse deal — row → middle pile one-by-one → next page ---- */
  function otpLayout(otpEl, count) {
    var width = otpEl.clientWidth || 320;
    var gap = 8;
    var box = Math.min(56, (width - gap * (count - 1)) / count);
    var total = box * count + gap * (count - 1);
    var startX = (width - total) / 2;
    var slots = [];
    for (var i = 0; i < count; i++) {
      slots.push(startX + i * (box + gap) + box / 2 - width / 2);
    }
    return { width: width, box: box, slots: slots };
  }

  function setOtpTransform(el, x, y, rot) {
    el.style.transform =
      "translateX(calc(-50% + " + x + "px)) translateY(" + y + "px)" +
      (rot ? " rotate(" + rot + "deg)" : "");
  }

  window.bcStackOtp = function (otpEl, done) {
    if (!otpEl) {
      if (done) done();
      return;
    }
    var inputs = Array.prototype.slice.call(otpEl.querySelectorAll("input"));
    if (!inputs.length || reduce) {
      if (done) done();
      return;
    }

    var layout = otpLayout(otpEl, inputs.length);
    var stackGap = 8;
    otpEl.classList.add("is-stack-enter");

    // Freeze boxes in their current row slots
    inputs.forEach(function (input, index) {
      input.style.width = layout.box + "px";
      input.style.zIndex = String(inputs.length - index);
      setOtpTransform(input, layout.slots[index], 0, 0);
    });

    function gatherToMiddle(index) {
      if (index >= inputs.length) {
        // Hold the pile, then go to next page / landing
        window.setTimeout(function () {
          if (done) done();
        }, 520);
        return;
      }

      var input = inputs[index];
      input.classList.add("is-stacked");
      input.style.zIndex = String(10 + index);
      var pileY = index * stackGap;
      var pileR = (index % 2 === 0 ? -1 : 1) * Math.min(index * 1.4, 6);
      setOtpTransform(input, 0, pileY, pileR);

      window.setTimeout(function () {
        gatherToMiddle(index + 1);
      }, 160);
    }

    window.setTimeout(function () {
      gatherToMiddle(0);
    }, 60);
  };
})();
