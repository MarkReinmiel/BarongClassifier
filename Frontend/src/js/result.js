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

    const resultPreview =
        document.getElementById("resultPreview");


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

    confidence.textContent =
        "Not available";

    classificationStatus.textContent =
        "Waiting for AI Model";


    // =================================
    // VIEW FULL IMAGE
    // =================================

    viewImageButton.addEventListener("click", function () {

        resultPreview.hidden =
            !resultPreview.hidden;

        if (resultPreview.hidden) {

            viewImageButton.textContent =
                "View Image";

        } else {

            viewImageButton.textContent =
                "Hide Image";

        }

    });


    // =================================
    // BACK TO CLASSIFY PAGE
    // =================================

    backButton.addEventListener("click", function () {

        window.location.href = "classify.html";

    });

});