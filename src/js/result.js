
document.addEventListener("DOMContentLoaded", function () {

    const imageData =
        sessionStorage.getItem("classifiedImage");

    const savedFileName =
        sessionStorage.getItem("fileName");


    // Get result elements

    const backButton =
    document.getElementById("backButton");

    backButton.addEventListener("click", function () {

        window.location.href = "classify.html";

    });
    
    const resultImage =
        document.getElementById("resultImage");

    const fullResultImage =
        document.getElementById("fullResultImage");

    const resultFileName =
        document.getElementById("resultFileName");

    const viewImageButton =
        document.getElementById("viewImageButton");

    const resultPreview =
        document.getElementById("resultPreview");


    // Check if an image was submitted

    if (!imageData) {

        resultFileName.textContent =
            "No image submitted";

        viewImageButton.disabled = true;

        return;

    }


    // Display submitted image

    resultImage.src = imageData;

    fullResultImage.src = imageData;


    // Display file name

    resultFileName.textContent =
        savedFileName || "Unknown file";



    // View Image button

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

});