/**
 * Live camera with zoom + lighting/focus/stability guidance (mobile).
 * Integrates with classify form field #fileGal and preview helpers via CustomEvent.
 */
(function () {
  if (typeof createCameraGuidance !== "function") return;

  var config = typeof CAMERA_GUIDANCE_CONFIG !== "undefined" ? CAMERA_GUIDANCE_CONFIG : {};
  var openCamera = document.getElementById("openCamera");
  var cameraPanel = document.getElementById("cameraPanel");
  var cameraFrame = document.getElementById("cameraFrame");
  var cameraPreview = document.getElementById("cameraPreview");
  var cameraGuide = document.getElementById("cameraGuide");
  var cameraNotice = document.getElementById("cameraNotice");
  var guidanceHeadline = document.getElementById("cameraGuidanceHeadline");
  var checklist = document.getElementById("cameraChecklist");
  var calibrationPanel = document.getElementById("cameraCalibration");
  var captureButton = document.getElementById("captureButton");
  var closeCamera = document.getElementById("closeCamera");
  var zoomControls = document.getElementById("cameraZoomControls");
  var zoomSlider = document.getElementById("cameraZoom");
  var zoomStatus = document.getElementById("cameraZoomStatus");
  var fileInput = document.getElementById("fileGal");
  if (!openCamera || !cameraPanel || !cameraPreview || !captureButton) return;

  var HTTPS_MESSAGE =
    "Live camera needs HTTPS. Open this site as https:// (not http://), " +
    "tap Advanced > Proceed on the certificate warning, then try Camera again. " +
    "Or use Gallery.";

  var form = document.getElementById("classifyForm");
  var guidance = createCameraGuidance(config);
  var CHECK_SYMBOLS = { good: "✓", adjust: "△", bad: "✕" };
  var LEVEL_CLASSES = ["is-red", "is-yellow", "is-green"];
  var cameraStream = null;
  var zoomRange = null;
  var analysisTimer = null;
  var lastStatus = null;

  function setCameraOpen(open) {
    if (form) form.classList.toggle("camera-open", !!open);
    document.body.classList.toggle("camera-live-open", !!open);
    if (open && cameraPanel) {
      try {
        cameraPanel.scrollIntoView({ block: "center", behavior: "smooth" });
      } catch (err) {
        // ignore
      }
    }
  }

  function showCameraNotice(message) {
    if (!cameraNotice) return;
    cameraNotice.textContent = message || "";
    cameraNotice.hidden = !message;
  }

  function formatZoom(value) {
    return (Math.round(value * 10) / 10).toString() + "x";
  }

  function setLevel(element, level) {
    if (!element) return;
    element.classList.remove.apply(element.classList, LEVEL_CLASSES);
    element.classList.add("is-" + level);
  }

  function stopAnalysis() {
    if (analysisTimer !== null) {
      clearTimeout(analysisTimer);
      analysisTimer = null;
    }
  }

  function stopCamera() {
    stopAnalysis();
    if (cameraStream) {
      cameraStream.getTracks().forEach(function (track) {
        track.stop();
      });
    }
    cameraStream = null;
    zoomRange = null;
    lastStatus = null;
    guidance.reset();
    cameraPreview.srcObject = null;
    cameraPanel.hidden = true;
    setCameraOpen(false);
    openCamera.disabled = false;
    captureButton.disabled = true;
    if (guidanceHeadline) {
      guidanceHeadline.disabled = true;
      guidanceHeadline.classList.remove("is-ready");
    }
  }

  function guideRegionInVideo() {
    var videoWidth = cameraPreview.videoWidth;
    var videoHeight = cameraPreview.videoHeight;
    if (!videoWidth || !videoHeight || !cameraFrame || !cameraGuide) return null;
    var frameBox = cameraFrame.getBoundingClientRect();
    var guideBox = cameraGuide.getBoundingClientRect();
    if (!frameBox.width || !frameBox.height) return null;
    var scale = Math.max(frameBox.width / videoWidth, frameBox.height / videoHeight);
    var offsetX = (videoWidth * scale - frameBox.width) / 2;
    var offsetY = (videoHeight * scale - frameBox.height) / 2;
    var x = Math.max(0, (guideBox.left - frameBox.left + offsetX) / scale);
    var y = Math.max(0, (guideBox.top - frameBox.top + offsetY) / scale);
    var width = Math.min(videoWidth - x, guideBox.width / scale);
    var height = Math.min(videoHeight - y, guideBox.height / scale);
    return {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.round(width),
      height: Math.round(height),
    };
  }

  function renderStatus(status) {
    setLevel(cameraGuide, status.level === "green" ? "green" : status.level);
    setLevel(guidanceHeadline, status.level);
    guidanceHeadline.textContent = status.headline;
    var ready = !!status.canCapture;
    guidanceHeadline.disabled = !ready;
    if (ready) {
      guidanceHeadline.textContent = "Click This to Capture";
      guidanceHeadline.classList.add("is-ready");
    } else {
      guidanceHeadline.classList.remove("is-ready");
    }
    if (checklist) {
      Object.keys(status.checks || {}).forEach(function (name) {
        var item = checklist.querySelector('[data-check="' + name + '"]');
        if (!item) return;
        var state = status.checks[name].state;
        item.className = "check-" + state;
        var span = item.querySelector("span");
        if (span) span.textContent = CHECK_SYMBOLS[state];
        item.title = status.checks[name].message;
        if (name === "glare") item.hidden = state === "good";
      });
    }
    captureButton.disabled = !ready;
  }

  function analysisLoop() {
    analysisTimer = null;
    if (!cameraStream || document.hidden) return;
    var region = guideRegionInVideo();
    if (region && region.width > 0 && region.height > 0) {
      var started = performance.now();
      var metrics = guidance.analyze(cameraPreview, region);
      var status = guidance.evaluate(metrics, started);
      lastStatus = status;
      renderStatus(status);
    }
    analysisTimer = setTimeout(analysisLoop, config.ANALYSIS_INTERVAL_MS || 250);
  }

  async function applyZoom(track, requested) {
    if (!zoomRange) return;
    var value = Math.min(Math.max(requested, zoomRange.min), zoomRange.allowedMax);
    try {
      await track.applyConstraints({ advanced: [{ zoom: value }] });
    } catch (error) {
      zoomControls.hidden = true;
      if (zoomStatus) zoomStatus.textContent = "Browser zoom control unavailable";
      return;
    }
    var settings = track.getSettings ? track.getSettings() : {};
    var applied = typeof settings.zoom === "number" ? settings.zoom : value;
    zoomSlider.value = applied;
    guidance.reset();
    if (zoomStatus) {
      zoomStatus.textContent = "Zoom: " + formatZoom(applied);
    }
  }

  function setupZoom(track) {
    var capabilities =
      track && typeof track.getCapabilities === "function" ? track.getCapabilities() : {};
    var zoom = capabilities.zoom;
    if (!zoom || typeof zoom.max !== "number" || zoom.max <= zoom.min) {
      if (zoomControls) zoomControls.hidden = true;
      if (zoomStatus) zoomStatus.textContent = "Browser zoom control unavailable";
      return;
    }
    zoomRange = {
      min: zoom.min,
      max: zoom.max,
      allowedMax: Math.min(zoom.max, config.MAX_REQUESTED_ZOOM || zoom.max),
    };
    zoomSlider.min = zoomRange.min;
    zoomSlider.max = zoomRange.allowedMax;
    zoomSlider.step = zoom.step || 0.1;
    zoomControls.hidden = false;
    var initialZoom =
      typeof config.INITIAL_ZOOM === "number" ? config.INITIAL_ZOOM : 4;
    applyZoom(track, initialZoom);
    if (zoomStatus) {
      zoomStatus.textContent = "Zoom: " + formatZoom(
        Math.min(Math.max(initialZoom, zoomRange.min), zoomRange.allowedMax)
      );
    }
  }

  function cameraErrorMessage(error) {
    var name = error && error.name;
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      return window.isSecureContext
        ? "Camera permission was denied. Allow camera access, or use Gallery."
        : HTTPS_MESSAGE;
    }
    if (name === "SecurityError") return HTTPS_MESSAGE;
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return "No camera was found. Use Gallery instead.";
    }
    if (name === "NotReadableError" || name === "TrackStartError") {
      return "Camera is in use by another app. Close it and try again.";
    }
    return "Camera could not be started. Use Gallery instead.";
  }

  function applyCapturedFile(file) {
    if (!file || !fileInput) return;
    try {
      var transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
    } catch (err) {
      // ignore
    }
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    document.dispatchEvent(
      new CustomEvent("barong:camera-captured", { detail: { file: file } })
    );
  }

  function fallbackNativeCapture() {
    var camInput = document.getElementById("fileCam");
    if (!camInput) {
      showCameraNotice(
        window.isSecureContext
          ? "Camera access is unavailable in this browser."
          : HTTPS_MESSAGE
      );
      return;
    }
    showCameraNotice("");
    try {
      camInput.click();
    } catch (err) {
      showCameraNotice(
        window.isSecureContext
          ? "Camera access is unavailable in this browser."
          : HTTPS_MESSAGE
      );
    }
  }

  function requestUserMedia(constraints) {
    return navigator.mediaDevices.getUserMedia(constraints);
  }

  function withTimeout(promise, ms) {
    return new Promise(function (resolve, reject) {
      var done = false;
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        reject(new Error("Camera request timed out"));
      }, ms);
      promise.then(
        function (value) {
          if (done) return;
          done = true;
          clearTimeout(timer);
          resolve(value);
        },
        function (error) {
          if (done) return;
          done = true;
          clearTimeout(timer);
          reject(error);
        }
      );
    });
  }

  async function openCameraStreamTimed() {
    var attempts = [
      {
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      },
      {
        audio: false,
        video: { facingMode: { ideal: "environment" } },
      },
      { audio: false, video: true },
    ];
    var lastError = null;
    for (var i = 0; i < attempts.length; i += 1) {
      try {
        return await withTimeout(requestUserMedia(attempts[i]), 10000);
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("Camera unavailable");
  }

  async function startCamera() {
    if (!window.isSecureContext) {
      showCameraNotice(HTTPS_MESSAGE);
      fallbackNativeCapture();
      return;
    }
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
      fallbackNativeCapture();
      return;
    }

    openCamera.disabled = true;
    cameraPanel.hidden = false;
    setCameraOpen(true);
    showCameraNotice("Starting camera… allow access if prompted.");
    if (guidanceHeadline) {
      guidanceHeadline.textContent = "Starting camera…";
      setLevel(guidanceHeadline, "red");
    }
    if (calibrationPanel) calibrationPanel.hidden = true;
    captureButton.disabled = true;

    try {
      cameraStream = await openCameraStreamTimed();
    } catch (error) {
      openCamera.disabled = false;
      setCameraOpen(false);
      cameraPanel.hidden = true;
      showCameraNotice(cameraErrorMessage(error));
      fallbackNativeCapture();
      return;
    }

    showCameraNotice("");
    cameraPreview.srcObject = cameraStream;
    if (guidanceHeadline) {
      guidanceHeadline.textContent = "Point the camera at the textile";
      setLevel(guidanceHeadline, "red");
    }
    setLevel(cameraGuide, "red");
    guidance.reset();
    try {
      await cameraPreview.play();
    } catch (error) {}
    setupZoom(cameraStream.getVideoTracks()[0]);
    stopAnalysis();
    analysisTimer = setTimeout(analysisLoop, config.ANALYSIS_INTERVAL_MS || 250);
    openCamera.disabled = false;
  }

  if (guidanceHeadline) {
    guidanceHeadline.addEventListener("click", function () {
      if (lastStatus && lastStatus.canCapture) captureButton.click();
    });
  }

  if (zoomSlider) {
    zoomSlider.addEventListener("change", function () {
      var track = cameraStream && cameraStream.getVideoTracks()[0];
      if (track && zoomRange) applyZoom(track, parseFloat(zoomSlider.value));
    });
  }

  openCamera.addEventListener("click", startCamera);
  if (closeCamera) closeCamera.addEventListener("click", stopCamera);

  captureButton.addEventListener("click", function () {
    var videoWidth = cameraPreview.videoWidth;
    var videoHeight = cameraPreview.videoHeight;
    if (!cameraStream || !videoWidth || !videoHeight) {
      showCameraNotice("Camera is not ready yet.");
      return;
    }
    if (!(lastStatus && lastStatus.canCapture)) return;
    var region = config.CROP_TO_GUIDE
      ? guideRegionInVideo()
      : { x: 0, y: 0, width: videoWidth, height: videoHeight };
    if (!region || !region.width || !region.height) {
      showCameraNotice("Camera is not ready yet.");
      return;
    }
    var canvas = document.createElement("canvas");
    canvas.width = region.width;
    canvas.height = region.height;
    canvas.getContext("2d").drawImage(
      cameraPreview,
      region.x,
      region.y,
      region.width,
      region.height,
      0,
      0,
      region.width,
      region.height
    );
    canvas.toBlob(
      function (blob) {
        if (!blob) {
          showCameraNotice("Photo could not be captured.");
          return;
        }
        var capturedFile = new File([blob], "camera-capture-" + Date.now() + ".webp", {
          type: "image/webp",
        });
        stopCamera();
        showCameraNotice("");
        applyCapturedFile(capturedFile);
      },
      "image/webp",
      0.9
    );
  });

  window.addEventListener("pagehide", stopCamera);
  document.addEventListener("visibilitychange", function () {
    if (!cameraStream) return;
    if (document.hidden) stopAnalysis();
    else if (analysisTimer === null) {
      guidance.reset();
      analysisTimer = setTimeout(analysisLoop, config.ANALYSIS_INTERVAL_MS || 250);
    }
  });
})();
