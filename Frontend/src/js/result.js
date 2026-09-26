document.addEventListener("DOMContentLoaded", function () {

    const resultImage =
        document.getElementById("resultImage");

    const fullResultImage =
        document.getElementById("fullResultImage");

    const resultFileName =
        document.getElementById("resultFileName");

    const backButton =
        document.getElementById("backButton");

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
        sessionStorage.getItem("classifiedImage");

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

    const classifierUrl = "http://127.0.0.1:5501/predict";

    function showDetail(element, text, pending) {
        element.textContent = text;
        element.classList.toggle("is-pending", pending);
    }

    showDetail(predictedType, "Classifying...", true);
    showDetail(confidence, "Classifying...", true);
    showDetail(classificationStatus, "Running the trained model", true);

    fetch(classifierUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            image: imageData
        })
    })
        .then(function (response) {
            return response.json().then(function (payload) {
                return {
                    ok: response.ok,
                    payload: payload
                };
            });
        })
        .then(async function (result) {
            if (!result.ok) {
                throw new Error(
                    (result.payload && result.payload.error) ||
                    "Classification failed."
                );
            }

            const percent = Math.round(result.payload.confidence * 1000) / 10;

            showDetail(predictedType, result.payload.display_name, false);
            showDetail(confidence, percent.toFixed(1) + "%", false);
            showDetail(classificationStatus, "Classified", false);

            if (typeof supabaseClient !== "undefined") {
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
                        }
                    }
                } catch (saveError) {
                    console.error("Classification save error:", saveError);
                }
            }
        })
        .catch(function () {
            showDetail(predictedType, "Classifier unavailable", true);
            showDetail(confidence, "Not available", true);
            showDetail(
                classificationStatus,
                "Start: python \"Backend/machine learning/classify_server.py\"",
                true
            );
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


    // =================================
    // BACK TO CLASSIFY PAGE
    // =================================

    backButton.addEventListener("click", function () {

        window.location.href = "classify.html";

    });

});