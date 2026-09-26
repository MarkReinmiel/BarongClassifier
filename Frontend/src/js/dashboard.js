document.addEventListener("DOMContentLoaded", async function () {
    const textileTypesEl = document.getElementById("overviewTextileTypes");
    const modelAccuracyEl = document.getElementById("overviewModelAccuracy");
    const imagesClassifiedEl = document.getElementById("overviewImagesClassified");

    // Project defaults from the trained MobileNetV2 model.
    const fallback = {
        textile_types: 3,
        model_accuracy: 100,
        images_classified: 0
    };

    function renderOverview(data) {
        if (textileTypesEl) {
            textileTypesEl.textContent = String(data.textile_types ?? fallback.textile_types);
        }
        if (modelAccuracyEl) {
            modelAccuracyEl.textContent =
                String(data.model_accuracy ?? fallback.model_accuracy) + "%";
        }
        if (imagesClassifiedEl) {
            imagesClassifiedEl.textContent = String(
                data.images_classified ?? fallback.images_classified
            );
        }
    }

    renderOverview(fallback);

    if (typeof supabaseClient === "undefined") {
        return;
    }

    try {
        const { data, error } = await supabaseClient.rpc("get_dashboard_overview");

        if (error) {
            console.error("Dashboard overview error:", error);
            return;
        }

        if (data) {
            renderOverview(data);
        }
    } catch (error) {
        console.error("Dashboard overview error:", error);
    }
});
