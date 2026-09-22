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
    // TEMPORARY DEMO DETAILS
    // =================================

    const predictedType =
        document.getElementById("predictedType");

    const confidence =
        document.getElementById("confidence");

    const classificationStatus =
        document.getElementById("classificationStatus");


    predictedType.textContent =
        "Pending AI Model";
    predictedType.classList.add("is-pending");

    confidence.textContent =
        "Not available";
    confidence.classList.add("is-pending");

    classificationStatus.textContent =
        "Waiting for AI Model";
    classificationStatus.classList.add("is-pending");


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