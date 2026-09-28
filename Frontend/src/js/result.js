document.addEventListener("DOMContentLoaded", async function () {

    const resultImage =
        document.getElementById("resultImage");

    const fullResultImage =
        document.getElementById("fullResultImage");

    const resultFileName =
        document.getElementById("resultFileName");

    const viewImageButton =
        document.getElementById("viewImageButton");

    const imageModal =
        document.getElementById("imageModal");

    const closeImageModal =
        document.getElementById("closeImageModal");


    // =================================
    // GET SAVED IMAGE
    // =================================

    const imageData =
        await loadClassifiedImage();

    const savedFileName =
        sessionStorage.getItem("classifiedFileName");


    if (imageData) {

        resultImage.src = imageData;

        fullResultImage.src = imageData;

    } else {

        window.location.href = "classify.html";
        return;

    }


    if (savedFileName) {

        resultFileName.textContent =
            savedFileName;

    }


    // =================================
    // CLASSIFY WITH THE TRAINED MODEL
    // =================================

    const predictedType =
        document.getElementById("predictedType");

    const confidence =
        document.getElementById("confidence");

    const classificationStatus =
        document.getElementById("classificationStatus");

    const classifierUrl = CLASSIFIER_BASE_URL + "/predict";

    const classifierTimeoutMs = 90000;

    const classificationSaved =
    sessionStorage.getItem("classificationSaved") === "true";

    function showDetail(element, text, pending) {
        element.textContent = text;
        element.classList.toggle("is-pending", pending);
    }

    function classificationError(kind, message) {
        const error = new Error(message);
        error.kind = kind;
        return error;
    }

    showDetail(predictedType, "Classifying...", true);
    showDetail(confidence, "Classifying...", true);
    showDetail(classificationStatus, "Running the trained model", true);

    const abortController =
        typeof AbortController !== "undefined" ? new AbortController() : null;

    const timeoutId = setTimeout(function () {
        if (abortController) {
            abortController.abort();
        }
    }, classifierTimeoutMs);

    fetch(classifierUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            image: imageData
        }),
        signal: abortController ? abortController.signal : undefined
    })
        .catch(function (error) {
            if (error && error.name === "AbortError") {
                throw classificationError(
                    "timeout",
                    "The classification server took too long to respond. " +
                    "Check that the laptop is awake and try again."
                );
            }

            throw classificationError("offline", classifierOfflineMessage());
        })
        .then(function (response) {
            return response.json()
                .catch(function () {
                    return {};
                })
                .then(function (payload) {
                    return {
                        ok: response.ok,
                        status: response.status,
                        payload: payload
                    };
                });
        })
        .then(async function (result) {
            if (!result.ok) {
                const serverMessage = result.payload && result.payload.error;

                if (result.status === 415) {
                    throw classificationError(
                        "format",
                        serverMessage || "Unsupported image format. Use a JPG or PNG photo."
                    );
                }

                if (result.status === 400 || result.status === 413) {
                    throw classificationError(
                        "image",
                        serverMessage || "Could not read that image. Try another photo."
                    );
                }

                throw classificationError(
                    "prediction",
                    serverMessage || "The classifier could not process this image. Please try again."
                );
            }

            const percent = Math.round(result.payload.confidence * 1000) / 10;

            showDetail(predictedType, result.payload.display_name, false);
            showDetail(confidence, percent.toFixed(1) + "%", false);
            showDetail(classificationStatus, "Classified", false);

            if (
                typeof supabaseClient !== "undefined" &&
                !classificationSaved
            ) {
                try {
                    const { data: sessionData } =
                        await supabaseClient.auth.getSession();
                    const user = sessionData.session && sessionData.session.user;

                    if (user) {
                        const { error: saveError } = await supabaseClient
                            .from("classifications")
                            .insert({
                                user_id: user.id,
                                file_name: savedFileName || null,
                                predicted_label: result.payload.label,
                                display_name: result.payload.display_name,
                                confidence: result.payload.confidence
                            });

                        if (saveError) {
                            console.error("Classification save error:", saveError);
                        }  else {
                            sessionStorage.setItem(
                                "classificationSaved",
                                "true"
                            );
                        }
                    }
                } catch (saveError) {
                    console.error("Classification save error:", saveError);
                }
            }
        })
        .catch(function (error) {
            const kind = error && error.kind;

            const headline = {
                offline: "Classifier unavailable",
                timeout: "Server timeout",
                format: "Unsupported image",
                image: "Invalid image",
                prediction: "Prediction failed"
            }[kind] || "Classification failed";

            showDetail(predictedType, headline, true);
            showDetail(confidence, "Not available", true);
            showDetail(
                classificationStatus,
                (error && error.kind && error.message) ||
                    "Something went wrong. Please try again.",
                true
            );
        })
        .finally(function () {
            clearTimeout(timeoutId);
        });


    // =================================
    // VIEW IMAGE MODAL
    // =================================

    function openImageModal() {

        imageModal.hidden = false;

        document.body.classList.add("modal-open");

    }

    function closeImageModalFunction() {

        imageModal.hidden = true;

        document.body.classList.remove("modal-open");

    }

    viewImageButton.addEventListener("click", function () {

        openImageModal();

    });

    closeImageModal.addEventListener("click", function () {

        closeImageModalFunction();

    });


    // Close when clicking outside the image

    imageModal.addEventListener("click", function (event) {

        if (event.target === imageModal) {

            closeImageModalFunction();

        }

    });


    // Close with Escape key

    document.addEventListener("keydown", function (event) {

        if (
            event.key === "Escape" &&
            !imageModal.hidden
        ) {

            closeImageModalFunction();

        }

    });

});