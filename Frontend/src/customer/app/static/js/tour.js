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
    main: [
      {
        target: '[data-tour="textile-types"]',
        title: "Explore textile types",
        body: "Compare Piña, Jusi, and Cocoon — the three fabrics this classifier can identify.",
        mode: "auto",
      },
      {
        target: '[data-tour="history"]',
        title: "Check your history",
        body: "Every saved classification is stored here so you can review results later.",
        mode: "auto",
      },
      {
        target: '[data-tour="how-it-works"]',
        title: "How it works",
        body: "A short four-step overview of capture → analyze → result on your home page.",
        mode: "auto",
      },
      {
        target: '[data-tour="classify"]',
        title: "Classify a textile",
        body: "Ready to try it? Open Classify Textile to upload or capture a Barong photo.",
        mode: "demo-then-user",
        userPrompt: "Click Classify Textile to open the classifier.",
        allowNavigate: true,
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
        target: '[data-tour="classify-gallery"], #galBtn',
        title: "Upload from gallery",
        body: "Pick a clear JPG, PNG, or WEBP photo of the fabric from your device.",
        mode: "demo-then-user",
        userPrompt: "Click Upload from Gallery to choose a photo (or continue after picking).",
        allowNavigate: false,
        allowNative: true,
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
        target: '[data-tour="history-stats"], .history-stats',
        title: "History snapshot",
        body: "See totals, your most common fabric, and average confidence at a glance.",
        mode: "auto",
      },
      {
        target: '[data-tour="history-panel"], .history-panel',
        title: "Your classifications",
        body: "Filter by date or fabric, then open any result to review confidence.",
        mode: "demo-then-user",
        userPrompt: "Click Classifications to continue.",
        allowNavigate: false,
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

  function resolveTarget(selector) {
    if (!selector) return null;
    const parts = String(selector).split(",");
    for (let i = 0; i < parts.length; i++) {
      const el = document.querySelector(parts[i].trim());
      if (el) return el;
    }
    return null;
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

    persist: function (section) {
      this.markLocal(section);
      if (!this.completeUrl) return Promise.resolve();
      return fetch(this.completeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ section: section, skipped: false }),
        credentials: "same-origin",
      }).catch(function () {});
    },
  };

  /* ===================== Runner ===================== */
  function createRunner(sectionId, steps) {
    const list = (steps || []).filter((step) => resolveTarget(step.target));
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
    let moveRaf = 0;
    let timers = [];
    let cursorPos = { x: window.innerWidth * 0.5, y: window.innerHeight * 0.55 };
    let running = false;
    let inputLocked = true;

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

    function requestInputLock() {
      inputLocked = true;
      if (block) block.style.pointerEvents = "auto";
      document.body.classList.add("tour-locked");
      if (!block || !block.requestPointerLock) return;
      try {
        const p = block.requestPointerLock({ unadjustedMovement: true });
        if (p && p.catch) p.catch(function () {});
      } catch (err) {
        try {
          block.requestPointerLock();
        } catch (err2) {
          /* capture layer only */
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
      /* Keep a soft shield, but punch a hole by raising the live target */
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
        if (!inputLocked && liveTarget && liveTarget.contains(event.target)) return;
        event.preventDefault();
        event.stopPropagation();
      };
      ["click", "mousedown", "mouseup", "pointerdown", "pointerup", "contextmenu"].forEach(
        function (type) {
          block.addEventListener(type, onBlockClick, true);
        }
      );
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

      tip = document.createElement("div");
      tip.className = "tour-tip";
      tip.innerHTML =
        '<h3 class="tour-tip-title"></h3>' +
        '<p class="tour-tip-body"></p>' +
        '<span class="tour-tip-step"></span>' +
        '<span class="tour-tip-nudge"></span>';

      cursorEl = null;
      rippleEl = null;

      /* Fixed hit target above the dim layer — page z-index traps can't block it */
      hitProxy = document.createElement("button");
      hitProxy.type = "button";
      hitProxy.className = "tour-hit-proxy";
      hitProxy.setAttribute("aria-label", "Continue tour");
      hitProxy.hidden = true;

      root.appendChild(block);
      root.appendChild(spotlight);
      root.appendChild(arrowsHost);
      root.appendChild(tip);
      root.appendChild(hitProxy);
      document.body.appendChild(root);

      onKeyDown = function (event) {
        if (!inputLocked && (event.key === "Enter" || event.key === " ")) return;
        event.preventDefault();
        event.stopPropagation();
      };
      document.addEventListener("keydown", onKeyDown, true);
    }

    function placeChrome(rect) {
      const top = Math.max(0, rect.top - PAD);
      const left = Math.max(0, rect.left - PAD);
      const width = rect.width + PAD * 2;
      const height = rect.height + PAD * 2;
      spotlight.style.top = top + "px";
      spotlight.style.left = left + "px";
      spotlight.style.width = width + "px";
      spotlight.style.height = height + "px";
      arrowsHost.style.top = top + "px";
      arrowsHost.style.left = left + "px";
      arrowsHost.style.width = width + "px";
      arrowsHost.style.height = height + "px";
      Array.prototype.forEach.call(arrowsHost.children, function (node) {
        node.style.animation = "none";
        void node.offsetWidth;
        node.style.animation = "";
      });
      if (hitProxy && !hitProxy.hidden) {
        hitProxy.style.top = top + "px";
        hitProxy.style.left = left + "px";
        hitProxy.style.width = width + "px";
        hitProxy.style.height = height + "px";
      }
      if (tip) {
        const tipH = tip.offsetHeight || 110;
        const tipW = Math.min(300, window.innerWidth - 32);
        let tipTop = rect.bottom + 56;
        let tipLeft = rect.left;
        if (tipTop + tipH > window.innerHeight - 12) {
          tipTop = Math.max(12, rect.top - tipH - 56);
        }
        if (tipLeft + tipW > window.innerWidth - 12) {
          tipLeft = window.innerWidth - tipW - 12;
        }
        tip.style.top = Math.max(12, tipTop) + "px";
        tip.style.left = Math.max(12, tipLeft) + "px";
      }
    }

    function setTip(step, nudge) {
      if (!tip) return;
      tip.querySelector(".tour-tip-title").textContent = step.title || "";
      tip.querySelector(".tour-tip-body").textContent = step.body || "";
      tip.querySelector(".tour-tip-step").textContent =
        "Step " + (index + 1) + " of " + list.length;
      tip.querySelector(".tour-tip-nudge").textContent = nudge || "";
    }

    function clearLiveTarget() {
      if (hitProxy) {
        hitProxy.hidden = true;
        if (onUserClick) hitProxy.removeEventListener("click", onUserClick);
      }
      if (liveTarget) {
        liveTarget.classList.remove(
          "tour-target-live",
          "tour-target-user",
          "tour-target-pressed"
        );
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
      if (onKeyDown) document.removeEventListener("keydown", onKeyDown, true);
      if (root && root.parentNode) root.parentNode.removeChild(root);
      root = null;
      activeRunner = null;
    }

    /** Persist section, then go to the link (dashboard → Classify page). */
    function completeAndNavigate(href) {
      running = false;
      teardownChrome();
      const go = function () {
        window.location.assign(href);
      };
      const saved = TourState.persist(sectionId);
      if (saved && typeof saved.finally === "function") saved.finally(go);
      else go();
    }

    /**
     * Interactive highlight — user must click the glowing control.
     * allowNavigate: leave for the target href after saving progress
     * allowNative: let the real control handle the click (file picker, etc.)
     */
    function armUserPhase(step, el, rect) {
      releaseInputLock();
      document.body.classList.add("tour-user-phase");
      setTip(step, step.userPrompt || "Click the highlighted control to continue.");
      liveTarget = el;
      liveTarget.classList.add("tour-target-live", "tour-target-user");

      onUserClick = function (event) {
        if (step.allowNavigate) {
          event.preventDefault();
          event.stopPropagation();
          const href =
            el.getAttribute("href") ||
            (el.href ? String(el.href) : "") ||
            "/classify";
          document.body.classList.remove("tour-user-phase");
          if (hitProxy) hitProxy.hidden = true;
          completeAndNavigate(href);
          return;
        }

        if (step.allowNative) {
          /* File picker / native control — forward proxy clicks to the real element */
          const fromProxy = hitProxy && event.currentTarget === hitProxy;
          if (fromProxy) {
            event.preventDefault();
            event.stopPropagation();
          }
          document.body.classList.remove("tour-user-phase");
          if (hitProxy) hitProxy.hidden = true;
          if (fromProxy) {
            try {
              el.click();
            } catch (err) {
              /* ignore */
            }
          }
          later(320, function () {
            if (running) advanceOrFinish();
          });
          return;
        }

        event.preventDefault();
        event.stopPropagation();
        if (step.openProfile) {
          try {
            el.click();
          } catch (err) {
            /* ignore */
          }
        }
        document.body.classList.remove("tour-user-phase");
        if (hitProxy) hitProxy.hidden = true;
        advanceOrFinish();
      };

      hitProxy.hidden = false;
      hitProxy.addEventListener("click", onUserClick);
      placeChrome(rect);
      liveTarget.addEventListener("click", onUserClick, true);
    }

    function beginSpotlightStep(step, el, afterPlace) {
      requestInputLock();
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      later(SCROLL_SETTLE_MS, function () {
        if (!running) return;
        const rect = el.getBoundingClientRect();
        setTip(step, "");
        placeChrome(rect);
        liveTarget = el;
        liveTarget.classList.add("tour-target-live");
        afterPlace(rect);
      });
    }

    function runAutoStep(step, el) {
      beginSpotlightStep(step, el, function () {
        later(1600, function () {
          if (!running) return;
          advanceOrFinish();
        });
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
      if (step.mode === "demo-then-user") runDemoThenUserStep(step, el);
      else runAutoStep(step, el);
    }

    function onResize() {
      if (!liveTarget) return;
      placeChrome(liveTarget.getBoundingClientRect());
    }

    function finish() {
      running = false;
      teardownChrome();
      TourState.persist(sectionId);
    }

    function start() {
      if (activeRunner) return;
      running = true;
      activeRunner = { sectionId: sectionId, stop: finish };
      buildDom();
      document.body.classList.add("tour-active");
      window.addEventListener("resize", onResize);
      window.addEventListener("scroll", onResize, true);
      requestInputLock();
      runStep(0);
    }

    return { start, finish };
  }

  let activeRunner = null;

  function startSection(sectionId) {
    if (!TourState.needs(sectionId)) return;
    if (activeRunner) return;
    const steps = SECTION_STEPS[sectionId];
    if (!steps) return;
    const runner = createRunner(sectionId, steps);
    if (runner) runner.start();
  }

  /**
   * TRIGGER MAP
   * -----------
   * main     → dashboard data-launch after nickname
   * classify → /classify after main tour (required Classify click)
   * textile  → first visit to /textiletypes
   * history  → first visit to /history
   * profile  → first click on profile button
   */
  function bindTriggers() {
    const pageHost = document.getElementById("onboarding-tour");
    if (pageHost && pageHost.getAttribute("data-launch") === "1") {
      const section = pageHost.getAttribute("data-section") || "main";
      window.setTimeout(function () {
        startSection(section);
      }, 450);
    }

    const profileBtn =
      document.querySelector('[data-tour="profile-btn"]') ||
      document.getElementById("profileBtn");
    if (profileBtn) {
      profileBtn.setAttribute("data-tour", "profile-btn");
      profileBtn.addEventListener(
        "click",
        function (event) {
          if (!TourState.needs("profile")) return;
          if (activeRunner) return;
          event.preventDefault();
          event.stopPropagation();
          startSection("profile");
        },
        true
      );
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
    state: TourState,
    sections: SECTION_STEPS,
  };
})();
