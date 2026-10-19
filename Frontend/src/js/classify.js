document.addEventListener("DOMContentLoaded", function () {

    const textileImage =
        document.getElementById("textileImage");

    const uploadArea =
        document.getElementById("uploadArea");

    const classifyButton =
        document.getElementById("classifyButton");

    const previewSection =
        document.getElementById("previewSection");

    const imagePreview =
        document.getElementById("imagePreview");

    const fileName =
        document.getElementById("fileName");

    const removeImage =
        document.getElementById("removeImage");

    const retakeImage =
        document.getElementById("retakeImage");

    const saveImage =
        document.getElementById("saveImage");

    const uploadFeedback =
        document.getElementById("uploadFeedback");

    const allowedTypes = [
        "image/jpeg",
        "image/png"
    ];

    let selectedFile = null;



    function setFeedback(message, type) {
        if (!uploadFeedback) {
            return;
        }

        uploadFeedback.textContent = message || "";
        uploadFeedback.hidden = !message;
        uploadFeedback.className =
            "upload-feedback" + (type ? " " + type : "");
    }

    function resetUploadCopy() {
        uploadArea.querySelector("h3").textContent =
            "Choose an image";

        uploadArea.querySelector("span").textContent =
            "JPG or PNG files · drag & drop supported";
    }

    function applySelectedFile(file, fromCamera) {
        if (!file) {
            return;
        }

        const isAllowed =
            allowedTypes.includes(file.type) ||
            (!file.type && /\.(jpe?g|png)$/i.test(file.name));

        if (!isAllowed) {
            setFeedback(
                "Unsupported image format. Please select a JPG or PNG image.",
                "error"
            );
            textileImage.value = "";
            return;
        }

        selectedFile = file;

        const imageURL = URL.createObjectURL(file);

        imagePreview.src = imageURL;

        fileName.textContent = "Selected file: " + file.name;

        previewSection.hidden = false;

        retakeImage.hidden = !fromCamera;

        saveImage.hidden = !fromCamera;

        classifyButton.disabled = false;

        uploadArea.classList.add("has-file");

        uploadArea.querySelector("h3").textContent =
            "Image selected";

        uploadArea.querySelector("span").textContent =
            "Review your image, then analyze";

        setFeedback("", "");
    }

    textileImage.addEventListener("change", function () {
        applySelectedFile(textileImage.files[0], false);
    });

    ["dragenter", "dragover"].forEach(function (eventName) {
        uploadArea.addEventListener(eventName, function (event) {
            event.preventDefault();
            event.stopPropagation();
            uploadArea.classList.add("is-dragging");
        });
    });

    ["dragleave", "drop"].forEach(function (eventName) {
        uploadArea.addEventListener(eventName, function (event) {
            event.preventDefault();
            event.stopPropagation();
            uploadArea.classList.remove("is-dragging");
        });
    });

    uploadArea.addEventListener("drop", function (event) {
        const file = event.dataTransfer.files[0];

        if (!file) {
            return;
        }

        applySelectedFile(file, false);
    });

    function clearSelection() {
        selectedFile = null;

        textileImage.value = "";

        imagePreview.src = "";

        fileName.textContent = "";

        previewSection.hidden = true;

        retakeImage.hidden = true;

        saveImage.hidden = true;

        classifyButton.disabled = true;

        uploadArea.classList.remove("has-file");

        resetUploadCopy();

        setFeedback("", "");
    }

    removeImage.addEventListener("click", clearSelection);

    saveImage.addEventListener("click", async function () {
        if (!selectedFile) {
            return;
        }

        const photo = new File(
            [selectedFile],
            selectedFile.name || "textile-photo.jpg",
            { type: selectedFile.type || "image/jpeg" }
        );

        if (navigator.canShare && navigator.canShare({ files: [photo] })) {
            try {
                await navigator.share({
                    files: [photo],
                    title: "Textile photo"
                });
                return;
            } catch (error) {
                if (error && error.name === "AbortError") {
                    return;
                }
            }
        }

        const link = document.createElement("a");
        const url = URL.createObjectURL(photo);
        link.href = url;
        link.download = photo.name;
        link.click();
        setTimeout(function () {
            URL.revokeObjectURL(url);
        }, 1000);
    });

    function resetClassifyButton() {
        classifyButton.disabled = false;
        classifyButton.innerHTML =
            'Analyze Textile <span>→</span>';
    }

    classifyButton.addEventListener("click", function () {
        const file = selectedFile;

        if (!file) {
            setFeedback("Please select an image first.", "error");
            return;
        }

        classifyButton.disabled = true;
        classifyButton.textContent = "Preparing...";

        const reader = new FileReader();

        reader.onload = function (event) {

            // New classification
            sessionStorage.removeItem(
                "classificationSaved"
            );

            saveClassifiedImage(event.target.result)
                .then(function () {
                    sessionStorage.setItem(
                        "classifiedFileName",
                        file.name
                    );

                    window.location.href = "result.html";
                })
                .catch(function () {
                    resetClassifyButton();
                    setFeedback(
                        "Image upload failed. This photo could not be prepared on this device. Try a smaller photo.",
                        "error"
                    );
                });
        };

        reader.onerror = function () {
            resetClassifyButton();
            setFeedback("Could not read that image. Try again.", "error");
        };

        reader.readAsDataURL(file);
    });


    // =================================
    // LIVE CAMERA WITH CAPTURE GUIDANCE
    // =================================

    const config = CAMERA_GUIDANCE_CONFIG;

    const openCamera = document.getElementById("openCamera");
    const cameraPanel = document.getElementById("cameraPanel");
    const cameraFrame = document.getElementById("cameraFrame");
    const cameraPreview = document.getElementById("cameraPreview");
    const cameraGuide = document.getElementById("cameraGuide");
    const cameraNotice = document.getElementById("cameraNotice");
    const guidanceHeadline = document.getElementById("cameraGuidanceHeadline");
    const checklist = document.getElementById("cameraChecklist");
    const calibrationPanel = document.getElementById("cameraCalibration");
    const captureButton = document.getElementById("captureButton");
    const closeCamera = document.getElementById("closeCamera");
    const zoomControls = document.getElementById("cameraZoomControls");
    const zoomSlider = document.getElementById("cameraZoom");
    const zoomStatus = document.getElementById("cameraZoomStatus");

    const HTTPS_MESSAGE =
        "Camera access may require HTTPS on this device/browser. " +
        "You can still upload an image from your gallery.";

    const calibrationMode =
        config.CALIBRATION_MODE_ALLOWED &&
        new URLSearchParams(window.location.search).get("calibrate") === "1";

    const guidance = createCameraGuidance(config);

    const CHECK_SYMBOLS = { good: "✓", adjust: "△", bad: "✕" };
    const LEVEL_CLASSES = ["is-red", "is-yellow", "is-green"];

    let cameraStream = null;
    let zoomRange = null;
    let analysisTimer = null;
    let lastStatus = null;

    // The headline is a real <button>: when the guide is green it is enabled
    // and acts as the capture button (Enter / Space work natively).
    guidanceHeadline.addEventListener("click", function () {
        if ((lastStatus && lastStatus.canCapture) || calibrationMode) {
            captureButton.click();
        }
    });

    function showCameraNotice(message) {
        cameraNotice.textContent = message || "";
        cameraNotice.hidden = !message;
    }

    function formatZoom(value) {
        return (Math.round(value * 10) / 10).toString() + "x";
    }

    function setLevel(element, level) {
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
        uploadArea.hidden = false;
        openCamera.disabled = false;
        captureButton.disabled = true;
        guidanceHeadline.disabled = true;
        guidanceHeadline.classList.remove("is-ready");
    }

    // Maps the on-screen guide rectangle to pixels of the camera video,
    // accounting for object-fit: cover cropping of the preview.
    function guideRegionInVideo() {
        const videoWidth = cameraPreview.videoWidth;
        const videoHeight = cameraPreview.videoHeight;

        if (!videoWidth || !videoHeight) {
            return null;
        }

        const frameBox = cameraFrame.getBoundingClientRect();
        const guideBox = cameraGuide.getBoundingClientRect();

        if (!frameBox.width || !frameBox.height) {
            return null;
        }

        const scale = Math.max(
            frameBox.width / videoWidth,
            frameBox.height / videoHeight
        );
        const offsetX = (videoWidth * scale - frameBox.width) / 2;
        const offsetY = (videoHeight * scale - frameBox.height) / 2;

        const x = Math.max(0, (guideBox.left - frameBox.left + offsetX) / scale);
        const y = Math.max(0, (guideBox.top - frameBox.top + offsetY) / scale);
        const width = Math.min(videoWidth - x, guideBox.width / scale);
        const height = Math.min(videoHeight - y, guideBox.height / scale);

        return {
            x: Math.round(x),
            y: Math.round(y),
            width: Math.round(width),
            height: Math.round(height)
        };
    }

    function renderStatus(status) {
        setLevel(
            cameraGuide,
            status.level === "green" ? "green" : status.level
        );

        setLevel(guidanceHeadline, status.level);

        // Show the normal guidance message
        guidanceHeadline.textContent = status.headline;

        // Make READY TO CAPTURE behave like a button
        const ready = status.canCapture || calibrationMode;

        guidanceHeadline.disabled = !ready;

        if (ready) {
            guidanceHeadline.textContent = "Click This to Capture";
            guidanceHeadline.classList.add("is-ready");
            guidanceHeadline.setAttribute("aria-label", "Capture image");
        } else {
            guidanceHeadline.classList.remove("is-ready");
            guidanceHeadline.removeAttribute("aria-label");
        }

        Object.keys(status.checks).forEach(function (name) {
            const item = checklist.querySelector(
                '[data-check="' + name + '"]'
            );

            if (!item) {
                return;
            }

            const state = status.checks[name].state;

            item.className = "check-" + state;

            item.querySelector("span").textContent =
                CHECK_SYMBOLS[state];

            item.title = status.checks[name].message;

            if (name === "glare") {
                item.hidden = state === "good";
            }
        });

        captureButton.disabled =
            !(status.canCapture || calibrationMode);
    }

    function renderCalibration(metrics, region, elapsedMs) {
        const settings = cameraStream
            ? cameraStream.getVideoTracks()[0].getSettings()
            : {};

        calibrationPanel.textContent = [
            "CALIBRATION MODE",
            "Coverage:   " + Math.round(metrics.coverage * 100) + "%  (good ≥ " +
                Math.round(config.COVERAGE_GOOD_MIN * 100) + "%)",
            "Scale:      " + metrics.scale.toFixed(3) + "  (good " +
                config.SCALE_GOOD_MIN + "–" + config.SCALE_GOOD_MAX + ")",
            "Sharpness:  " + metrics.sharpness.toFixed(1) + "  (good ≥ " +
                config.SHARPNESS_GOOD_MIN + ")",
            "Brightness: " + metrics.brightness.toFixed(0) + "  (good " +
                config.BRIGHTNESS_DIM + "–" + config.BRIGHTNESS_BRIGHT + ")",
            "Glare:      " + (metrics.glare * 100).toFixed(1) + "%",
            "Motion:     " + (metrics.motion === null ? "–" : metrics.motion.toFixed(3)) +
                "  (stable ≤ " + config.MOTION_STABLE_MAX + ")",
            "Texture:    " + metrics.texture.toFixed(1),
            "Video:      " + cameraPreview.videoWidth + "×" + cameraPreview.videoHeight +
                (settings.zoom ? "  zoom " + formatZoom(settings.zoom) : ""),
            "Guide:      " + region.width + "×" + region.height + " px",
            "Analysis:   " + elapsedMs.toFixed(0) + " ms"
        ].join("\n");
    }

    function analysisLoop() {
        analysisTimer = null;

        if (!cameraStream || document.hidden) {
            return;
        }

        const region = guideRegionInVideo();

        if (region && region.width > 0 && region.height > 0) {
            const started = performance.now();
            const metrics = guidance.analyze(cameraPreview, region);
            const status = guidance.evaluate(metrics, started);

            lastStatus = status;
            renderStatus(status);

            if (calibrationMode) {
                renderCalibration(metrics, region, performance.now() - started);
            }
        }

        analysisTimer = setTimeout(analysisLoop, config.ANALYSIS_INTERVAL_MS);
    }

    async function applyZoom(track, requested) {
        const value = Math.min(
            Math.max(requested, zoomRange.min),
            zoomRange.allowedMax
        );

        try {
            await track.applyConstraints({ advanced: [{ zoom: value }] });
        } catch (error) {
            zoomControls.hidden = true;
            zoomStatus.textContent = "Browser zoom control unavailable";
            return;
        }

        const settings = track.getSettings ? track.getSettings() : {};
        const applied =
            typeof settings.zoom === "number" ? settings.zoom : value;

        zoomSlider.value = applied;
        guidance.reset();

        const target = config.MAX_REQUESTED_ZOOM;

        if (zoomRange.max >= target) {
            zoomStatus.textContent =
                applied >= target - 0.05
                    ? "Zoom: " + formatZoom(applied) + " ✓"
                    : "Zoom: " + formatZoom(applied) +
                      " (up to " + formatZoom(target) + " available)";
        } else {
            zoomStatus.textContent =
                "Maximum supported browser zoom: " +
                formatZoom(zoomRange.max) +
                " · Applied: " + formatZoom(applied);
        }
    }

    function setupZoom(track) {
        const capabilities =
            track && typeof track.getCapabilities === "function"
                ? track.getCapabilities()
                : {};

        const zoom = capabilities.zoom;

        if (
            !zoom ||
            typeof zoom.max !== "number" ||
            typeof zoom.min !== "number" ||
            zoom.max <= zoom.min
        ) {
            zoomControls.hidden = true;
            zoomStatus.textContent = "Browser zoom control unavailable";
            return;
        }

        zoomRange = {
            min: zoom.min,
            max: zoom.max,
            allowedMax: Math.min(zoom.max, config.MAX_REQUESTED_ZOOM)
        };

        zoomSlider.min = zoomRange.min;
        zoomSlider.max = zoomRange.allowedMax;
        zoomSlider.step = zoom.step || 0.1;
        zoomControls.hidden = false;

        applyZoom(track, config.INITIAL_ZOOM);
    }

    zoomSlider.addEventListener("change", function () {
        const track = cameraStream && cameraStream.getVideoTracks()[0];

        if (track && zoomRange) {
            applyZoom(track, parseFloat(zoomSlider.value));
        }
    });

    function cameraErrorMessage(error) {
        const name = error && error.name;

        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
            return window.isSecureContext
                ? "Camera permission was denied. Allow camera access for this site in your browser settings, or upload an image from your gallery."
                : HTTPS_MESSAGE;
        }

        if (name === "SecurityError") {
            return HTTPS_MESSAGE;
        }

        if (
            name === "NotFoundError" ||
            name === "DevicesNotFoundError" ||
            name === "OverconstrainedError"
        ) {
            return "No camera was found on this device. You can still upload an image from your gallery.";
        }

        if (name === "NotReadableError" || name === "TrackStartError") {
            return "The camera is being used by another app. Close it and try again, or upload an image from your gallery.";
        }

        return "The camera could not be started. You can still upload an image from your gallery.";
    }

    async function startCamera() {
        showCameraNotice("");

        if (
            !navigator.mediaDevices ||
            typeof navigator.mediaDevices.getUserMedia !== "function"
        ) {
            showCameraNotice(
                window.isSecureContext
                    ? "Camera access is unavailable in this browser. You can still upload an image from your gallery."
                    : HTTPS_MESSAGE
            );
            return;
        }

        openCamera.disabled = true;

        try {
            cameraStream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    facingMode: { ideal: "environment" },
                    width: { ideal: 2560 },
                    height: { ideal: 1440 }
                }
            });
        } catch (error) {
            openCamera.disabled = false;
            showCameraNotice(cameraErrorMessage(error));
            return;
        }

        cameraPreview.srcObject = cameraStream;
        cameraPanel.hidden = false;
        uploadArea.hidden = true;
        calibrationPanel.hidden = !calibrationMode;
        captureButton.disabled = !calibrationMode;
        guidanceHeadline.textContent = "Point the camera at the textile";
        setLevel(guidanceHeadline, "red");
        setLevel(cameraGuide, "red");
        guidance.reset();

        try {
            await cameraPreview.play();
        } catch (error) {
            // Autoplay can be deferred on some browsers; the stream still attaches.
        }

        setupZoom(cameraStream.getVideoTracks()[0]);

        stopAnalysis();
        analysisTimer = setTimeout(analysisLoop, config.ANALYSIS_INTERVAL_MS);
    }

    openCamera.addEventListener("click", startCamera);

    retakeImage.addEventListener("click", function () {
        clearSelection();
        startCamera();
    });

    captureButton.addEventListener("click", function () {
        const videoWidth = cameraPreview.videoWidth;
        const videoHeight = cameraPreview.videoHeight;

        if (!cameraStream || !videoWidth || !videoHeight) {
            showCameraNotice("The camera is not ready yet. Wait a moment and try again.");
            return;
        }

        if (!calibrationMode && !(lastStatus && lastStatus.canCapture)) {
            return;
        }

        const region = config.CROP_TO_GUIDE
            ? guideRegionInVideo()
            : { x: 0, y: 0, width: videoWidth, height: videoHeight };

        if (!region || !region.width || !region.height) {
            showCameraNotice("The camera is not ready yet. Wait a moment and try again.");
            return;
        }

        const canvas = document.createElement("canvas");
        canvas.width = region.width;
        canvas.height = region.height;
        canvas.getContext("2d").drawImage(
            cameraPreview,
            region.x, region.y, region.width, region.height,
            0, 0, region.width, region.height
        );

        canvas.toBlob(function (blob) {
            if (!blob) {
                showCameraNotice("The photo could not be captured. Please try again.");
                return;
            }

            const capturedFile = new File(
                [blob],
                "camera-capture-" + Date.now() + ".jpg",
                { type: "image/jpeg" }
            );

            stopCamera();
            showCameraNotice("");
            textileImage.value = "";
            applySelectedFile(capturedFile, true);
            previewSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }, "image/jpeg", 0.92);
    });

    closeCamera.addEventListener("click", stopCamera);

    window.addEventListener("pagehide", stopCamera);

    document.addEventListener("visibilitychange", function () {
        if (!cameraStream) {
            return;
        }

        if (document.hidden) {
            stopAnalysis();
        } else if (analysisTimer === null) {
            guidance.reset();
            analysisTimer = setTimeout(analysisLoop, config.ANALYSIS_INTERVAL_MS);
        }
    });


});
