/**
 * Barongcognition — multi-section guided tour engine
 *
 * Sections: main | classify | textile | history | profile
 * State: server tour_progress + sessionStorage mirror
 *
 * Dashboard (main) ends with a required Classify click (allowNavigate)
 * that opens /classify and starts the classify page tour.
 */
(function () {
  const PAD = 10;
  const CURSOR_MOVE_MS = 1100;
  const PRE_CLICK_MS = 220;
  const CLICK_HOLD_MS = 380;
  const BETWEEN_STEPS_MS = 420;
  const SCROLL_SETTLE_MS = 420;

  const ARROW_LAYOUT = [
    { angle: -28, orbit: 82, spin: 12 },
    { angle: 28, orbit: 82, spin: -12 },
    { angle: 118, orbit: 86, spin: -12 },
    { angle: 180, orbit: 78, spin: 0 },
    { angle: 242, orbit: 86, spin: 12 },
  ];

  const CURVED_ARROW_SVG =
    '<svg viewBox="0 0 48 48" fill="none" aria-hidden="true">' +
    '<path class="tour-curve" d="M14 8 C 18 22, 30 28, 24 40"/>' +
    '<path class="tour-head" d="M18.5 34.5 L24 42 L29.5 34.5 Z"/>' +
    "</svg>";

  const CURSOR_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path fill="currentColor" stroke="#fff" stroke-width="1.2" ' +
    'd="M4 3.5 L4 18.5 L8.2 14.8 L11.2 21.2 L13.6 20.2 L10.5 13.6 L16.5 13.6 Z"/>' +
    "</svg>";

  /* ------------------------------------------------------------------
     SECTION → STEP MAP
     Edit targets/copy here. Profile / textile / history tours start
     when that area is opened for the first time (see bindTriggers).
     ------------------------------------------------------------------ */
  const SECTION_STEPS = {
    /* Dashboard: only Classify is interactive — one click → /classify */
    main: [
      {
        target: '[data-tour="classify"]',
        title: "Classify a textile",
        body: "Click Classify Textile to open the classifier.",
        mode: "user-navigate",
        allowNavigate: true,
        navigateTo: "/classify",
      },
    ],
    classify: [
      {
        target: '[data-tour="classify-header"]',
        title: "Classify Textile",
        body: "This page identifies whether a Barong photo looks like Piña, Jusi, or Cocoon.",
        mode: "auto",
      },
      {
        target: '[data-tour="classify-preview"], #drop',
        title: "Photo preview",
        body: "Your selected or captured image appears here before analysis.",
        mode: "auto",
      },
      {
        /* Desktop upload control */
        target: "#galBtn, .classify-source-desktop",
        title: "Upload from Gallery",
        body: "Choose a clear JPG or PNG photo of the Barong textile from your files.",
        mode: "auto",
        desktopOnly: true,
      },
      {
        /* Mobile gallery — customer picks Gallery or Camera */
        target: '#galBtnMobile, [data-tour="classify-gallery"].classify-source-mobile',
        title: "Gallery",
        body: "Tap Gallery to pick an existing textile photo from your phone.",
        mode: "auto",
        mobileOnly: true,
      },
      {
        target: '#openCamera, [data-tour="classify-camera"]',
        title: "Camera",
        body: "Tap Camera to take a live photo of the textile. Use whichever option you prefer — Gallery or Camera.",
        mode: "auto",
        mobileOnly: true,
      },
      {
        target: '[data-tour="classify-tips"], .classify-tips',
        title: "For best results",
        body: "Good light, a close-up shot, and flat fabric help the model read the weave.",
        mode: "auto",
      },
      {
        target: '[data-tour="classify-analyze"], #analyze',
        title: "Analyze Textile",
        body: "After a photo appears in the preview, tap Analyze to get the fabric prediction.",
        mode: "auto",
      },
    ],
    textile: [
      {
        target: '[data-tour="textile-grid"]',
        title: "Textile library",
        body: "Browse each Barong fabric type the model can recognize, with short descriptions.",
        mode: "auto",
      },
      {
        target: '[data-tour="textile-card"]:first-of-type, .textile-card:first-of-type',
        title: "Open a fabric card",
        body: "Tap a card to read more about that textile’s look and feel.",
        mode: "demo-then-user",
        userPrompt: "Click a textile card to continue.",
        allowNavigate: false,
      },
    ],
    history: [
      {
        target: '[data-tour="history-header"], .history-page-header',
        title: "History",
        body: "This page keeps every textile you’ve classified so you can review them later.",
        mode: "auto",
      },
      {
        target:
          '[data-tour="history-preview"], .history-action-btn--preview, [data-history-preview].history-thumb-btn',
        title: "Preview",
        body: "Tap Preview (or the thumbnail) to open the classified photo full size.",
        mode: "auto",
      },
      {
        target: '[data-tour="history-delete"], .history-action-btn--delete[data-history-delete]',
        title: "Delete",
        body: "Tap Delete to remove a classification from your history. You’ll confirm before it’s removed.",
        mode: "auto",
      },
    ],
    profile: [
      {
        target: '[data-tour="profile-btn"], #profileBtn',
        title: "Your account menu",
        body: "Open your profile for account options and sign out.",
        mode: "demo-then-user",
        userPrompt: "Click your profile picture to finish.",
        allowNavigate: false,
        openProfile: true,
      },
    ],
  };

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const host = document.getElementById("tour-state");
    if (host && host.getAttribute("data-csrf")) return host.getAttribute("data-csrf");
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
  }

  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function isElementVisible(el) {
    if (!el || el.hidden) return false;
    if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === "none" || style.visibility === "hidden") return false;
    return el.getClientRects().length > 0;
  }

  function isMobileTourView() {
    return window.matchMedia("(max-width: 899px)").matches;
  }

  function resolveTarget(selector) {
    if (!selector) return null;
    const parts = String(selector).split(",");
    let fallback = null;
    for (let i = 0; i < parts.length; i++) {
      const nodes = document.querySelectorAll(parts[i].trim());
      for (let j = 0; j < nodes.length; j++) {
        const el = nodes[j];
        if (isElementVisible(el)) return el;
        if (!fallback) fallback = el;
      }
    }
    return fallback;
  }

  function stepAllowed(step) {
    if (!step) return false;
    if (step.mobileOnly && !isMobileTourView()) return false;
    if (step.desktopOnly && isMobileTourView()) return false;
    return !!resolveTarget(step.target);
  }

  /** Many arrows only for clickable controls — not headers / info panels. */
  function stepWantsArrows(step, el) {
    if (!step) return false;
    if (step.arrows === false) return false;
    if (step.arrows === true) return true;
    if (!el) return false;
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "BUTTON" || tag === "A" || tag === "LABEL" || tag === "SUMMARY") {
      return true;
    }
    if (el.getAttribute("role") === "button") return true;
    if (el.classList.contains("classify-button")) return true;
    if (el.classList.contains("classify-source-btn")) return true;
    if (el.classList.contains("classify-analyze")) return true;
    if (el.classList.contains("history-action-btn")) return true;
    if (el.classList.contains("history-thumb-btn")) return true;
    if (el.classList.contains("textile-card")) return true;
    if (el.classList.contains("avatar-btn")) return true;
    return false;
  }

  /* ===================== State manager ===================== */
  const TourState = {
    progress: {
      main: false,
      classify: false,
      textile: false,
      history: false,
      profile: false,
    },
    userId: "",
    completeUrl: "",

    bootFromDom: function () {
      const host = document.getElementById("tour-state");
      if (!host) return;
      this.userId = host.getAttribute("data-user-id") || "";
      this.completeUrl = host.getAttribute("data-complete-url") || "";
      try {
        const server = JSON.parse(host.getAttribute("data-progress") || "{}");
        this.progress = Object.assign({}, this.progress, server);
      } catch (err) {
        /* keep defaults */
      }
      // Mirror into sessionStorage for fast client checks across pages.
      try {
        const key = "bc_tour_progress_" + this.userId;
        const cached = sessionStorage.getItem(key);
        if (cached) {
          const local = JSON.parse(cached);
          Object.keys(this.progress).forEach((k) => {
            this.progress[k] = !!(this.progress[k] || local[k]);
          });
        }
        sessionStorage.setItem(key, JSON.stringify(this.progress));
      } catch (err2) {
        /* private mode */
      }
    },

    needs: function (section) {
      return !this.progress[section];
    },

    markLocal: function (section) {
      this.progress[section] = true;
      try {
        sessionStorage.setItem(
          "bc_tour_progress_" + this.userId,
          JSON.stringify(this.progress)
        );
      } catch (err) {
        /* ignore */
      }
    },

    persist: function (section, skipped) {
      this.markLocal(section);
      if (!this.completeUrl) return Promise.resolve();
      return fetch(this.completeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ section: section, skipped: !!skipped }),
        credentials: "same-origin",
      }).catch(function () {});
    },
  };

  /* ===================== Runner ===================== */
  function createRunner(sectionId, steps) {
    const list = (steps || []).filter(stepAllowed);
    if (!list.length) return null;

    let index = 0;
    let root = null;
    let block = null;
    let spotlight = null;
    let tip = null;
    let arrowsHost = null;
    let cursorEl = null;
    let rippleEl = null;
    let hitProxy = null;
    let liveTarget = null;
    let onBlockClick = null;
    let onKeyDown = null;
    let onUserClick = null;
    let blockEventTypes = [];
    let moveRaf = 0;
    let timers = [];
    let cursorPos = { x: window.innerWidth * 0.5, y: window.innerHeight * 0.55 };
    let running = false;
    let inputLocked = true;
    let skipBtn = null;
    let onSkipClick = null;

    function clearTimers() {
      timers.forEach(window.clearTimeout);
      timers = [];
      if (moveRaf) window.cancelAnimationFrame(moveRaf);
      moveRaf = 0;
    }

    function later(ms, fn) {
      const id = window.setTimeout(fn, ms);
      timers.push(id);
      return id;
    }

    function wantsVirtualCursor() {
      return window.matchMedia("(min-width: 900px)").matches;
    }

    function setCursorPos(x, y) {
      cursorPos = { x: x, y: y };
      if (!cursorEl) return;
      cursorEl.style.transform =
        "translate3d(" + Math.round(x) + "px, " + Math.round(y) + "px, 0)";
      if (rippleEl) {
        rippleEl.style.left = Math.round(x) + "px";
        rippleEl.style.top = Math.round(y) + "px";
      }
    }

    function showVirtualCursor() {
      if (!wantsVirtualCursor() || !cursorEl) return;
      cursorEl.classList.add("is-visible");
      if (rippleEl) rippleEl.classList.add("is-visible");
    }

    function hideVirtualCursor() {
      if (cursorEl) cursorEl.classList.remove("is-visible", "is-pressing");
      if (rippleEl) rippleEl.classList.remove("is-visible", "is-on");
    }

    function moveCursorTo(x, y, duration, done) {
      if (!wantsVirtualCursor() || !cursorEl) {
        if (done) done();
        return;
      }
      showVirtualCursor();
      const fromX = cursorPos.x;
      const fromY = cursorPos.y;
      const start = performance.now();
      const dur = Math.max(180, duration || CURSOR_MOVE_MS);
      if (moveRaf) window.cancelAnimationFrame(moveRaf);
      function tick(now) {
        const t = Math.min(1, (now - start) / dur);
        const e = easeInOutCubic(t);
        setCursorPos(fromX + (x - fromX) * e, fromY + (y - fromY) * e);
        if (t < 1) {
          moveRaf = window.requestAnimationFrame(tick);
        } else {
          moveRaf = 0;
          if (done) done();
        }
      }
      moveRaf = window.requestAnimationFrame(tick);
    }

    function playCursorClickPulse() {
      if (!cursorEl || !wantsVirtualCursor()) return;
      cursorEl.classList.add("is-pressing");
      if (rippleEl) {
        rippleEl.classList.remove("is-on");
        void rippleEl.offsetWidth;
        rippleEl.classList.add("is-on");
      }
      later(CLICK_HOLD_MS, function () {
        if (cursorEl) cursorEl.classList.remove("is-pressing");
      });
    }

    function requestInputLock() {
      inputLocked = true;
      if (block) block.style.pointerEvents = "auto";
      document.body.classList.add("tour-locked");
      /* Do not use Pointer Lock — it hides the real mouse on laptop. */
      if (document.pointerLockElement) {
        try {
          document.exitPointerLock();
        } catch (err) {
          /* ignore */
        }
      }
    }

    function releaseInputLock() {
      inputLocked = false;
      document.body.classList.remove("tour-locked");
      if (document.pointerLockElement) {
        try {
          document.exitPointerLock();
        } catch (err) {
          /* ignore */
        }
      }
      /* Keep the dim shield interactive so only the hit-proxy is clickable */
      if (block) block.style.pointerEvents = "auto";
    }

    function buildDom() {
      root = document.createElement("div");
      root.className = "tour-root";
      root.setAttribute("role", "dialog");
      root.setAttribute("aria-modal", "true");
      root.setAttribute("aria-label", "Guided tour");

      block = document.createElement("div");
      block.className = "tour-block";
      onBlockClick = function (event) {
        /* Swallow every background interaction — only .tour-hit-proxy may act */
        event.preventDefault();
        event.stopPropagation();
      };
      blockEventTypes = [
        "click",
        "mousedown",
        "mouseup",
        "pointerdown",
        "pointerup",
        "contextmenu",
      ];
      blockEventTypes.forEach(function (type) {
        block.addEventListener(type, onBlockClick, true);
      });
      block.addEventListener("touchstart", onBlockClick, { capture: true, passive: false });
      block.addEventListener("wheel", onBlockClick, { capture: true, passive: false });

      spotlight = document.createElement("div");
      spotlight.className = "tour-spotlight";

      arrowsHost = document.createElement("div");
      arrowsHost.className = "tour-arrows";
      ARROW_LAYOUT.forEach(function (spec, i) {
        const node = document.createElement("div");
        node.className = "tour-curved-arrow";
        node.style.setProperty("--orbit-angle", spec.angle + "deg");
        node.style.setProperty("--orbit", spec.orbit + "px");
        node.style.setProperty("--spin", spec.spin + "deg");
        node.style.setProperty("--delay", i * 0.08 + "s");
        node.innerHTML = CURVED_ARROW_SVG;
        arrowsHost.appendChild(node);
      });

      cursorEl = document.createElement("div");
      cursorEl.className = "tour-cursor";
      cursorEl.setAttribute("aria-hidden", "true");
      cursorEl.innerHTML = CURSOR_SVG;

      rippleEl = document.createElement("div");
      rippleEl.className = "tour-cursor-ripple";
      rippleEl.setAttribute("aria-hidden", "true");

      /* Description card with Next inside (advances; does not exit the tour) */
      tip = document.createElement("div");
      tip.className = "tour-tip";
      tip.setAttribute("role", "status");
      tip.innerHTML =
        '<p class="tour-tip-step"></p>' +
        '<h3 class="tour-tip-title"></h3>' +
        '<p class="tour-tip-body"></p>' +
        '<p class="tour-tip-nudge" hidden></p>' +
        '<div class="tour-tip-actions">' +
        '<button type="button" class="tour-skip tour-next" aria-label="Next step">Next</button>' +
        "</div>";
      skipBtn = tip.querySelector(".tour-skip");
      onSkipClick = function (event) {
        event.preventDefault();
        event.stopPropagation();
        goNext();
      };
      skipBtn.addEventListener("click", onSkipClick);

      /* Sole highlight hit target while the tour is open */
      hitProxy = document.createElement("button");
      hitProxy.type = "button";
      hitProxy.className = "tour-hit-proxy";
      hitProxy.setAttribute("aria-label", "Classify Textile");
      hitProxy.hidden = true;

      root.appendChild(block);
      root.appendChild(spotlight);
      root.appendChild(arrowsHost);
      root.appendChild(hitProxy);
      root.appendChild(tip);
      root.appendChild(rippleEl);
      root.appendChild(cursorEl);

      document.body.appendChild(root);
      setCursorPos(cursorPos.x, cursorPos.y);

      onKeyDown = function (event) {
        if (event.key === "Escape" || event.key === "Esc") {
          event.preventDefault();
          event.stopPropagation();
          skipTour();
          return;
        }
        if (
          !inputLocked &&
          hitProxy &&
          !hitProxy.hidden &&
          (event.key === "Enter" || event.key === " ")
        ) {
          event.preventDefault();
          hitProxy.click();
          return;
        }
        event.preventDefault();
        event.stopPropagation();
      };
      document.addEventListener("keydown", onKeyDown, true);
    }

    function updateTip(step) {
      if (!tip || !step) return;
      const stepEl = tip.querySelector(".tour-tip-step");
      const titleEl = tip.querySelector(".tour-tip-title");
      const bodyEl = tip.querySelector(".tour-tip-body");
      const nudgeEl = tip.querySelector(".tour-tip-nudge");
      const nextEl = tip.querySelector(".tour-skip");
      const isLast = index >= list.length - 1;
      const requireClick = step.mode === "user-navigate";
      if (stepEl) stepEl.textContent = "Step " + (index + 1) + " of " + list.length;
      if (titleEl) titleEl.textContent = step.title || "Guided tour";
      if (bodyEl) bodyEl.textContent = step.body || "";
      if (nextEl) {
        nextEl.hidden = !!requireClick;
        nextEl.textContent = isLast ? "Done" : "Next";
        nextEl.setAttribute(
          "aria-label",
          isLast ? "Finish tutorial step" : "Next step"
        );
      }
      if (nudgeEl) {
        const nudge = step.userPrompt || "";
        nudgeEl.textContent = nudge;
        nudgeEl.hidden = !nudge;
      }
      tip.hidden = false;
    }

    function placeTip(rect) {
      if (!tip || tip.hidden) return;
      const gap = 14;
      const tipWidth = Math.min(300, window.innerWidth - 32);
      tip.style.width = tipWidth + "px";
      tip.style.visibility = "hidden";
      tip.style.left = "0px";
      tip.style.top = "0px";
      const tipHeight = tip.offsetHeight || 140;
      let left = rect.left + rect.width / 2 - tipWidth / 2;
      left = Math.max(16, Math.min(left, window.innerWidth - tipWidth - 16));
      let top = rect.bottom + gap;
      if (top + tipHeight > window.innerHeight - 16) {
        top = rect.top - tipHeight - gap;
      }
      if (top < 16) top = 16;
      tip.style.left = left + "px";
      tip.style.top = top + "px";
      tip.style.visibility = "";
    }

    function placeChrome(rect, showArrows) {
      const top = Math.max(0, rect.top - PAD);
      const left = Math.max(0, rect.left - PAD);
      const width = rect.width + PAD * 2;
      const height = rect.height + PAD * 2;
      spotlight.style.top = top + "px";
      spotlight.style.left = left + "px";
      spotlight.style.width = width + "px";
      spotlight.style.height = height + "px";
      if (arrowsHost) {
        const step = list[index];
        const wantArrows =
          typeof showArrows === "boolean"
            ? showArrows
            : stepWantsArrows(step, liveTarget);
        arrowsHost.hidden = !wantArrows;
        if (wantArrows) {
          arrowsHost.style.top = top + "px";
          arrowsHost.style.left = left + "px";
          arrowsHost.style.width = width + "px";
          arrowsHost.style.height = height + "px";
          Array.prototype.forEach.call(arrowsHost.children, function (node) {
            node.style.animation = "none";
            void node.offsetWidth;
            node.style.animation = "";
          });
        }
      }
      if (hitProxy && !hitProxy.hidden) {
        hitProxy.style.top = top + "px";
        hitProxy.style.left = left + "px";
        hitProxy.style.width = width + "px";
        hitProxy.style.height = height + "px";
      }
      placeTip({ top: top, left: left, width: width, height: height, bottom: top + height });
    }

    function clearLiveTarget() {
      hideVirtualCursor();
      if (hitProxy) {
        hitProxy.hidden = true;
        if (onUserClick) {
          hitProxy.removeEventListener("click", onUserClick);
          hitProxy.onclick = null;
        }
      }
      if (liveTarget) {
        liveTarget.classList.remove(
          "tour-target-live",
          "tour-target-user",
          "tour-target-pressed"
        );
        /* Target is visual-only; never leave a tour click listener on the page node */
        if (onUserClick) liveTarget.removeEventListener("click", onUserClick, true);
      }
      onUserClick = null;
      liveTarget = null;
    }

    function advanceOrFinish() {
      if (index + 1 < list.length) {
        later(BETWEEN_STEPS_MS, function () {
          if (running) runStep(index + 1);
        });
      } else {
        finish();
      }
    }

    function teardownChrome() {
      clearTimers();
      clearLiveTarget();
      releaseInputLock();
      document.body.classList.remove("tour-active", "tour-user-phase", "tour-locked");
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onResize, true);
      if (onKeyDown) {
        document.removeEventListener("keydown", onKeyDown, true);
        onKeyDown = null;
      }
      if (skipBtn && onSkipClick) {
        skipBtn.removeEventListener("click", onSkipClick);
        onSkipClick = null;
      }
      skipBtn = null;
      if (block && onBlockClick) {
        blockEventTypes.forEach(function (type) {
          block.removeEventListener(type, onBlockClick, true);
        });
        block.removeEventListener("touchstart", onBlockClick, true);
        block.removeEventListener("wheel", onBlockClick, true);
        onBlockClick = null;
      }
      hideVirtualCursor();
      if (root && root.parentNode) root.parentNode.removeChild(root);
      root = null;
      block = null;
      spotlight = null;
      arrowsHost = null;
      hitProxy = null;
      tip = null;
      cursorEl = null;
      rippleEl = null;
      activeRunner = null;
    }

    function skipTour() {
      if (!running) return;
      running = false;
      teardownChrome();
      TourState.persist(sectionId, true);
      clearReplayAfterSection(sectionId);
    }

    /** Advance to the next tip (Next / Done). Does not exit the tour early. */
    function goNext() {
      if (!running) return;
      const step = list[index];
      if (step && step.mode === "user-navigate") return;
      clearTimers();
      clearLiveTarget();
      document.body.classList.remove("tour-user-phase");
      if (hitProxy) hitProxy.hidden = true;
      advanceOrFinish();
    }

    /** Persist section, then go to Classify Textile (/classify). */
    function completeAndNavigate(href) {
      running = false;
      const target = href || "/classify";
      teardownChrome();
      /* Section already marked on start — do not reset replay session. */
      clearReplayAfterSection(sectionId);
      const go = function () {
        window.location.assign(target);
      };
      const saved = TourState.persist(sectionId);
      if (saved && typeof saved.finally === "function") saved.finally(go);
      else go();
    }

    /**
     * Interactive highlight — ONLY the hit-proxy over the target is clickable.
     * allowNavigate / user-navigate: one click → /classify (or step.navigateTo / href)
     * allowNative: forward to the real control (file picker, etc.)
     */
    function armUserPhase(step, el, rect) {
      releaseInputLock();
      document.body.classList.add("tour-user-phase");
      updateTip(step);
      liveTarget = el;
      liveTarget.classList.add("tour-target-live", "tour-target-user");

      onUserClick = function (event) {
        event.preventDefault();
        event.stopPropagation();
        playCursorClickPulse();
        if (step.allowNavigate || step.mode === "user-navigate") {
          const href =
            step.navigateTo ||
            el.getAttribute("href") ||
            (el.href ? String(el.href) : "") ||
            "/classify";
          document.body.classList.remove("tour-user-phase");
          hideVirtualCursor();
          if (hitProxy) hitProxy.hidden = true;
          completeAndNavigate(href);
          return;
        }

        if (step.allowNative) {
          document.body.classList.remove("tour-user-phase");
          hideVirtualCursor();
          if (hitProxy) hitProxy.hidden = true;
          try {
            el.click();
          } catch (err) {
            /* ignore */
          }
          later(320, function () {
            if (!running) return;
            /* Classify: end tour so the source sheet / file picker stays usable */
            if (sectionId === "classify") finish();
            else advanceOrFinish();
          });
          return;
        }

        if (step.openProfile) {
          try {
            el.click();
          } catch (err) {
            /* ignore */
          }
        }
        document.body.classList.remove("tour-user-phase");
        hideVirtualCursor();
        if (hitProxy) hitProxy.hidden = true;
        advanceOrFinish();
      };

      hitProxy.hidden = false;
      hitProxy.setAttribute(
        "aria-label",
        step.title || step.userPrompt || "Continue tour"
      );
      hitProxy.addEventListener("click", onUserClick);
      placeChrome(rect, stepWantsArrows(step, el));

      /* Laptop: animate a guide pointer onto Classify, and keep the real mouse visible */
      if (wantsVirtualCursor() && rect) {
        const tx = rect.left + rect.width * 0.62;
        const ty = rect.top + rect.height * 0.55;
        moveCursorTo(tx, ty, CURSOR_MOVE_MS, function () {
          if (!running) return;
          playCursorClickPulse();
        });
      }
    }

    function beginSpotlightStep(step, el, afterPlace) {
      requestInputLock();
      updateTip(step);
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      later(SCROLL_SETTLE_MS, function () {
        if (!running) return;
        const rect = el.getBoundingClientRect();
        liveTarget = el;
        liveTarget.classList.add("tour-target-live");
        const isClickable = stepWantsArrows(step, el);
        placeChrome(rect, isClickable);
        /* Animated guide cursor only on clickable controls — not headers */
        if (isClickable && wantsVirtualCursor() && rect) {
          const tx = rect.left + rect.width * 0.55;
          const ty = rect.top + rect.height * 0.55;
          moveCursorTo(tx, ty, CURSOR_MOVE_MS);
        } else {
          hideVirtualCursor();
        }
        afterPlace(rect);
      });
    }

    function runAutoStep(step, el) {
      beginSpotlightStep(step, el, function () {
        /* Wait for Next / Done — no auto-advance timer */
      });
    }

    function runDemoThenUserStep(step, el) {
      beginSpotlightStep(step, el, function (rect) {
        later(700, function () {
          if (!running) return;
          armUserPhase(step, el, el.getBoundingClientRect() || rect);
        });
      });
    }

    /** Immediate interactive highlight (dashboard Classify). */
    function runUserNavigateStep(step, el) {
      beginSpotlightStep(step, el, function (rect) {
        if (!running) return;
        armUserPhase(step, el, el.getBoundingClientRect() || rect);
      });
    }

    function runStep(i) {
      clearTimers();
      clearLiveTarget();
      index = i;
      const step = list[index];
      const el = resolveTarget(step.target);
      if (!el) {
        if (index + 1 < list.length) return runStep(index + 1);
        return finish();
      }
      if (step.mode === "user-navigate") runUserNavigateStep(step, el);
      else if (step.mode === "demo-then-user") runDemoThenUserStep(step, el);
      else runAutoStep(step, el);
    }

    function onResize() {
      if (!liveTarget) return;
      placeChrome(liveTarget.getBoundingClientRect());
    }

    function finish() {
      running = false;
      teardownChrome();
      TourState.persist(sectionId, false);
      clearReplayAfterSection(sectionId);
    }

    function start() {
      if (activeRunner) return;
      running = true;
      activeRunner = { sectionId: sectionId, stop: finish, skip: skipTour };
      /* First show counts — 2nd visit to this page must not relaunch the tour */
      TourState.markLocal(sectionId);
      clearReplayAfterSection(sectionId);
      buildDom();
      document.body.classList.add("tour-active");
      window.addEventListener("resize", onResize);
      window.addEventListener("scroll", onResize, true);
      requestInputLock();
      runStep(0);
    }

    return { start: start, finish: finish, skip: skipTour };
  }

  let activeRunner = null;

  const REPLAY_KEY = "bc_tour_replay";
  const REPLAY_DONE_KEY = "bc_tour_replay_done";
  const REPLAY_SECTIONS = ["main", "classify", "textile", "history", "profile"];

  function isReplay() {
    try {
      return sessionStorage.getItem(REPLAY_KEY) === "1";
    } catch (err) {
      return false;
    }
  }

  function getReplayDone() {
    try {
      return JSON.parse(sessionStorage.getItem(REPLAY_DONE_KEY) || "{}") || {};
    } catch (err) {
      return {};
    }
  }

  function setReplayDone(map) {
    try {
      sessionStorage.setItem(REPLAY_DONE_KEY, JSON.stringify(map || {}));
    } catch (err) {
      /* private mode */
    }
  }

  function replayStillPending(sectionId) {
    if (!isReplay()) return false;
    const done = getReplayDone();
    return !done[sectionId];
  }

  function endReplay() {
    try {
      sessionStorage.removeItem(REPLAY_KEY);
      sessionStorage.removeItem(REPLAY_DONE_KEY);
    } catch (err) {
      /* private mode */
    }
  }

  /** Fresh ? click only — resets which pages may tour once. */
  function beginReplaySession() {
    try {
      sessionStorage.setItem(REPLAY_KEY, "1");
      setReplayDone({});
    } catch (err) {
      /* private mode */
    }
  }

  function startSection(sectionId) {
    if (activeRunner) return;
    if (isReplay()) {
      if (!replayStillPending(sectionId)) return;
    } else if (!TourState.needs(sectionId)) {
      return;
    }
    const steps = SECTION_STEPS[sectionId];
    if (!steps) return;
    const runner = createRunner(sectionId, steps);
    if (runner) runner.start();
  }

  function clearReplayAfterSection(sectionId) {
    if (!sectionId) return;
    if (isReplay()) {
      const done = getReplayDone();
      done[sectionId] = true;
      setReplayDone(done);
      const allDone = REPLAY_SECTIONS.every(function (key) {
        return !!done[key];
      });
      if (allDone) endReplay();
    }
  }

  /** Start the guided tour again for returning users (from the ? button). */
  function replayTutorial() {
    if (activeRunner) return;
    beginReplaySession();
    /* Allow each section once again even if already completed before */
    REPLAY_SECTIONS.forEach(function (key) {
      TourState.progress[key] = false;
    });
    try {
      sessionStorage.setItem(
        "bc_tour_progress_" + TourState.userId,
        JSON.stringify(TourState.progress)
      );
    } catch (err) {
      /* ignore */
    }
    const pageHost = document.getElementById("onboarding-tour");
    const section = pageHost
      ? pageHost.getAttribute("data-section") || ""
      : "";
    if (section === "main") {
      startSection("main");
      return;
    }
    const helpBtn = document.getElementById("tourHelpBtn");
    const homeUrl =
      (helpBtn && helpBtn.getAttribute("data-home-url")) || "/";
    const join = homeUrl.indexOf("?") >= 0 ? "&" : "?";
    window.location.assign(homeUrl + join + "tour_replay=1");
  }

  /**
   * TRIGGER MAP
   * -----------
   * main     → dashboard data-launch after nickname
   * classify → /classify after main tour (required Classify click)
   * textile  → first visit to /textiletypes
   * history  → first visit to /history
   * profile  → first click on profile button
   * help ?   → replayTutorial: Home → Classify, then first visit/click
   *            of Textile Types, History, and Profile also tour again
   */
  function bindTriggers() {
    const pageHost = document.getElementById("onboarding-tour");
    let fromReplayLink = false;
    try {
      const params = new URLSearchParams(window.location.search || "");
      if (params.get("tour_replay") === "1") {
        beginReplaySession();
        REPLAY_SECTIONS.forEach(function (key) {
          TourState.progress[key] = false;
        });
        try {
          sessionStorage.setItem(
            "bc_tour_progress_" + TourState.userId,
            JSON.stringify(TourState.progress)
          );
        } catch (err2) {
          /* ignore */
        }
        fromReplayLink = true;
        params.delete("tour_replay");
        const next = params.toString();
        const clean =
          window.location.pathname + (next ? "?" + next : "") + window.location.hash;
        window.history.replaceState({}, "", clean);
      }
    } catch (err) {
      /* ignore */
    }

    if (pageHost) {
      const section = pageHost.getAttribute("data-section") || "main";
      const serverWants = pageHost.getAttribute("data-launch") === "1";
      const shouldLaunch = isReplay()
        ? replayStillPending(section)
        : TourState.needs(section) && (serverWants || fromReplayLink);
      if (shouldLaunch) {
        window.setTimeout(function () {
          startSection(section);
        }, 450);
      }
    }

    const profileBtn =
      document.querySelector('[data-tour="profile-btn"]') ||
      document.getElementById("profileBtn");
    if (profileBtn) {
      profileBtn.setAttribute("data-tour", "profile-btn");
      profileBtn.addEventListener(
        "click",
        function (event) {
          const wantProfile = isReplay()
            ? replayStillPending("profile")
            : TourState.needs("profile");
          if (!wantProfile) return;
          if (activeRunner) return;
          event.preventDefault();
          event.stopPropagation();
          startSection("profile");
        },
        true
      );
    }

    const helpBtn = document.getElementById("tourHelpBtn");
    if (helpBtn) {
      helpBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        replayTutorial();
      });
    }
  }

  function boot() {
    TourState.bootFromDom();
    bindTriggers();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.BarongTour = {
    startSection: startSection,
    replay: replayTutorial,
    state: TourState,
    sections: SECTION_STEPS,
  };
})();
