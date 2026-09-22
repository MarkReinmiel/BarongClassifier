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

        if (!allowedTypes.includes(file.type)) {
            setFeedback("Please select a JPG or PNG image.", "error");
            textileImage.value = "";
            return;
        }

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

        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        textileImage.files = dataTransfer.files;

        applySelectedFile(file);
    });

    removeImage.addEventListener("click", function () {
        textileImage.value = "";

        imagePreview.src = "";

        fileName.textContent = "";

        previewSection.hidden = true;

        classifyButton.disabled = true;

        uploadArea.classList.remove("has-file");

        resetUploadCopy();

        setFeedback("", "");
    });

    classifyButton.addEventListener("click", function () {
        const file = textileImage.files[0];

        if (!file) {
            setFeedback("Please select an image first.", "error");
            return;
        }

        classifyButton.disabled = true;
        classifyButton.textContent = "Preparing...";

        const reader = new FileReader();

        reader.onload = function (event) {
            sessionStorage.setItem(
                "classifiedImage",
                event.target.result
            );

            sessionStorage.setItem(
                "classifiedFileName",
                file.name
            );

            window.location.href = "result.html";
        };

        reader.onerror = function () {
            classifyButton.disabled = false;
            classifyButton.innerHTML =
                'Classify Textile <span>→</span>';
            setFeedback("Could not read that image. Try again.", "error");
        };

        reader.readAsDataURL(file);
    });

});
