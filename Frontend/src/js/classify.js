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


    // =================================
    // SELECT IMAGE
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

        const imageURL =
            URL.createObjectURL(file);

        imagePreview.src = imageURL;

        fileName.textContent =
            "Selected file: " + file.name;

        previewSection.hidden = false;

        classifyButton.disabled = false;

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

        uploadArea.querySelector("h3").textContent =
            "Choose an image";

        uploadArea.querySelector("span").textContent =
            "JPG or PNG files";

    });


    // =================================
    // CLASSIFY AND OPEN RESULT PAGE
    // =================================

    classifyButton.addEventListener("click", function () {

        const file = textileImage.files[0];

        if (!file) {

            alert("Please select an image first.");

            return;
        }

        const reader = new FileReader();

        reader.onload = function (event) {

            const imageData =
                event.target.result;

            // Save the selected image temporarily

            sessionStorage.setItem(
                "classifiedImage",
                imageData
            );

            sessionStorage.setItem(
                "classifiedFileName",
                file.name
            );

            // Open the classification result page

            window.location.href = "result.html";

        };

        reader.readAsDataURL(file);

    });

});