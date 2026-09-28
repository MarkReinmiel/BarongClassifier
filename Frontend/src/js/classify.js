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

    function applySelectedFile(file) {
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

        classifyButton.disabled = false;

        uploadArea.classList.add("has-file");

        uploadArea.querySelector("h3").textContent =
            "Image selected";

        uploadArea.querySelector("span").textContent =
            "Review your image, then classify";

        setFeedback("", "");
    }

    textileImage.addEventListener("change", function () {
        applySelectedFile(textileImage.files[0]);
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

        applySelectedFile(file);
    });

    removeImage.addEventListener("click", function () {
        selectedFile = null;

        textileImage.value = "";

        imagePreview.src = "";

        fileName.textContent = "";

        previewSection.hidden = true;

        classifyButton.disabled = true;

        uploadArea.classList.remove("has-file");

        resetUploadCopy();

        setFeedback("", "");
    });

    function resetClassifyButton() {
        classifyButton.disabled = false;
        classifyButton.innerHTML =
            'Classify Textile <span>→</span>';
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
    // LIVE CAMERA
    // =================================

    const openCamera = document.getElementById("openCamera");
    const cameraPanel = document.getElementById("cameraPanel");
    const cameraPreview = document.getElementById("cameraPreview");
    const cameraNotice = document.getElementById("cameraNotice");
    const captureButton = document.getElementById("captureButton");
    const closeCamera = document.getElementById("closeCamera");
    const zoomControls = document.getElementById("cameraZoomControls");
    const zoomSlider = document.getElementById("cameraZoom");
    const zoomStatus = document.getElementById("cameraZoomStatus");

    const TARGET_ZOOM = 10;
    const HTTPS_MESSAGE =
        "Camera access may require HTTPS on this device/browser. " +
        "You can still upload an image from your gallery.";

    let cameraStream = null;
    let zoomRange = null;

    function showCameraNotice(message) {
        cameraNotice.textContent = message || "";
        cameraNotice.hidden = !message;
    }

    function formatZoom(value) {
        return (Math.round(value * 10) / 10).toString() + "x";
    }

    function stopCamera() {
        if (cameraStream) {
            cameraStream.getTracks().forEach(function (track) {
                track.stop();
            });
        }

        cameraStream = null;
        zoomRange = null;
        cameraPreview.srcObject = null;
        cameraPanel.hidden = true;
        uploadArea.hidden = false;
        openCamera.disabled = false;
    }

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

        if (zoomRange.max >= TARGET_ZOOM) {
            zoomStatus.textContent =
                applied >= TARGET_ZOOM - 0.05
                    ? "Zoom: " + formatZoom(applied) + " ✓"
                    : "Zoom: " + formatZoom(applied) +
                      " (up to " + formatZoom(TARGET_ZOOM) + " available)";
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
            allowedMax: Math.min(zoom.max, TARGET_ZOOM)
        };

        zoomSlider.min = zoomRange.min;
        zoomSlider.max = zoomRange.allowedMax;
        zoomSlider.step = zoom.step || 0.1;
        zoomControls.hidden = false;

        applyZoom(track, zoomRange.allowedMax);
    }

    zoomSlider.addEventListener("change", function () {
        const track = cameraStream && cameraStream.getVideoTracks()[0];

        if (track && zoomRange) {
            applyZoom(track, parseFloat(zoomSlider.value));
        }
    });

    openCamera.addEventListener("click", async function () {
        showCameraNotice("");

        if (
            !navigator.mediaDevices ||
            typeof navigator.mediaDevices.getUserMedia !== "function"
        ) {
            showCameraNotice(
                window.isSecureContext
                    ? "Camera is not available in this browser. You can still upload an image from your gallery."
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
                    width: { ideal: 1920 },
                    height: { ideal: 1080 }
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

        try {
            await cameraPreview.play();
        } catch (error) {
            // Autoplay can be deferred on some browsers; the stream still attaches.
        }

        setupZoom(cameraStream.getVideoTracks()[0]);
    });

    captureButton.addEventListener("click", function () {
        const width = cameraPreview.videoWidth;
        const height = cameraPreview.videoHeight;

        if (!cameraStream || !width || !height) {
            showCameraNotice("The camera is not ready yet. Wait a moment and try again.");
            return;
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        canvas.getContext("2d").drawImage(cameraPreview, 0, 0, width, height);

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
            applySelectedFile(capturedFile);
        }, "image/jpeg", 0.92);
    });

    closeCamera.addEventListener("click", stopCamera);

    window.addEventListener("pagehide", stopCamera);


    // =================================
    // CLASSIFICATION SERVER CHECK
    // =================================

    const serverStatus = document.getElementById("serverStatus");

    function setServerStatus(message, state) {
        serverStatus.textContent = message;
        serverStatus.className = "server-status" + (state ? " " + state : "");
    }

    const healthController =
        typeof AbortController !== "undefined" ? new AbortController() : null;

    const healthTimeout = setTimeout(function () {
        if (healthController) {
            healthController.abort();
        }
    }, 6000);

    fetch(CLASSIFIER_BASE_URL + "/health", {
        signal: healthController ? healthController.signal : undefined
    })
        .then(function (response) {
            return response.json();
        })
        .then(function (payload) {
            if (payload && payload.status === "ok") {
                setServerStatus(
                    "Classification server connected (" +
                        CLASSIFIER_HOST + ":" + CLASSIFIER_PORT + ")",
                    "ok"
                );
            } else {
                throw new Error("Unexpected health response");
            }
        })
        .catch(function () {
            setServerStatus(classifierOfflineMessage(), "error");
        })
        .finally(function () {
            clearTimeout(healthTimeout);
        });

});
