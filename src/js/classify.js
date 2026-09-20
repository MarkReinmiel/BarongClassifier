
document.addEventListener("DOMContentLoaded", function () {

    // =================================
    // GET HTML ELEMENTS
    // =================================

    const textileImage =
        document.getElementById("textileImage");

    const uploadArea =
        document.getElementById("uploadArea");

    const previewSection =
        document.getElementById("previewSection");

    const imagePreview =
        document.getElementById("imagePreview");

    const fileName =
        document.getElementById("fileName");

    const removeImage =
        document.getElementById("removeImage");

    const classifyButton =
        document.getElementById("classifyButton");


    // =================================
    // IMAGE UPLOAD AND PREVIEW
    // =================================

    textileImage.addEventListener("change", function () {

        const file = textileImage.files[0];

        if (!file) {
            return;
        }

        const allowedTypes = [
            "image/jpeg",
            "image/png"
        ];

        if (!allowedTypes.includes(file.type)) {

            alert("Please select a JPG or PNG image.");

            textileImage.value = "";

            return;
        }

        // Create image preview

        const imageURL =
            URL.createObjectURL(file);

        imagePreview.src = imageURL;

        // Show file name

        fileName.textContent =
            "Selected file: " + file.name;

        // Show preview section

        previewSection.hidden = false;

        // Enable classify button

        classifyButton.disabled = false;

        // Update upload text

        uploadArea.querySelector("h3").textContent =
            "Image selected";

        uploadArea.querySelector("span").textContent =
            "You can review your image below";

    });


    // =================================
    // REMOVE IMAGE
    // =================================

    removeImage.addEventListener("click", function () {

        textileImage.value = "";

        imagePreview.src = "";

        fileName.textContent = "";

        previewSection.hidden = true;

        classifyButton.disabled = true;

        // Restore upload text

        uploadArea.querySelector("h3").textContent =
            "Choose an image";

        uploadArea.querySelector("span").textContent =
            "JPG or PNG files";

    });


    // =================================
    // CLASSIFY IMAGE
    // =================================

    classifyButton.addEventListener("click", function () {

        const file = textileImage.files[0];

        if (!file) {

            alert("Please select an image first.");

            return;
        }

        // Convert image to a format
        // that can be used on the next page

        const reader = new FileReader();

        reader.onload = function (event) {

            // Save the image

            sessionStorage.setItem(
                "classifiedImage",
                event.target.result
            );

            // Save the image file name

            sessionStorage.setItem(
                "fileName",
                file.name
            );

            // Go to the result page

            window.location.href = "result.html";

        };

        reader.readAsDataURL(file);

    });

});