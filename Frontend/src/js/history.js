document.addEventListener("DOMContentLoaded", async function () {

    const historyLoading =
        document.getElementById("historyLoading");

    const historyEmpty =
        document.getElementById("historyEmpty");

    const historyError =
        document.getElementById("historyError");

    const historyList =
        document.getElementById("historyList");


    const historyFrom =
        document.getElementById("historyFrom");

    const historyTo =
        document.getElementById("historyTo");

    const fabricFilter =
        document.getElementById("fabricFilter");

    const historySearchDate =
        document.getElementById("historySearchDate");


    const todayHistoryButton =
        document.getElementById("todayHistoryButton");

    const filterHistoryButton =
        document.getElementById("filterHistoryButton");

    const clearHistoryButton =
        document.getElementById("clearHistoryButton");


    let currentUser = null;


    // =================================
    // INITIALIZE
    // =================================

    try {

        if (typeof supabaseClient === "undefined") {
            throw new Error(
                "Supabase client is not loaded."
            );
        }


        const {
            data: sessionData,
            error: sessionError
        } = await supabaseClient.auth.getSession();


        if (sessionError) {
            throw sessionError;
        }


        currentUser =
            sessionData.session?.user;


        if (!currentUser) {
            window.location.href = "auth.html";
            return;
        }


        // Load fabric types
        await loadFabricTypes();


        // Load all history
        await loadHistory();


    } catch (error) {

        console.error(
            "History initialization error:",
            error
        );

        historyLoading.hidden = true;
        historyError.hidden = false;

    }


    // =================================
    // LOAD FABRIC TYPES
    // =================================

    async function loadFabricTypes() {

        const {
            data,
            error
        } = await supabaseClient
            .from("textile_types")
            .select("slug, display_name")
            .order("display_name", {
                ascending: true
            });


        if (error) {
            throw error;
        }


        data.forEach(function (fabric) {

            const option =
                document.createElement("option");

            option.value =
                fabric.display_name;

            option.textContent =
                fabric.display_name;

            fabricFilter.appendChild(option);

        });

    }


    // =================================
    // TODAY BUTTON
    // =================================

    if (todayHistoryButton) {

        todayHistoryButton.addEventListener(
            "click",
            async function () {

                const today =
                    getLocalDateString();


                historyFrom.value =
                    today;

                historyTo.value =
                    today;


                await loadHistory(
                    today,
                    today
                );

            }
        );

    }


    // =================================
    // FILTER BUTTON
    // =================================

    if (filterHistoryButton) {

        filterHistoryButton.addEventListener(
            "click",
            async function () {

                const fromDate =
                    historyFrom.value;

                const toDate =
                    historyTo.value;


                if (fromDate && toDate) {

                    if (fromDate > toDate) {

                        alert(
                            "The From date cannot be later than the To date."
                        );

                        return;

                    }

                }

        


                await loadHistory(
                    fromDate,
                    toDate
                );

            }
        );

    }


    // =================================
    // SEARCH
    // =================================

    if (historySearchDate) {

        historySearchDate.addEventListener(
            "change",
            async function () {

                await loadHistory(
                    historyFrom.value,
                    historyTo.value
                );

            }
        );

    }


    // =================================
    // FABRIC TYPE FILTER
    // =================================

    if (fabricFilter) {

        fabricFilter.addEventListener(
            "change",
            async function () {

                await loadHistory(
                    historyFrom.value,
                    historyTo.value
                );

            }
        );

    }


    // =================================
    // CLEAR
    // =================================

    if (clearHistoryButton) {

        clearHistoryButton.addEventListener(
            "click",
            async function () {

                historyFrom.value = "";
                historyTo.value = "";

                historySearchDate.value = "";

                fabricFilter.value = "";


                await loadHistory();

            }
        );

    }


    // =================================
    // LOAD HISTORY
    // =================================

    async function loadHistory(
        fromDate = "",
        toDate = ""
    ) {

        historyLoading.hidden = false;
        historyEmpty.hidden = true;
        historyError.hidden = true;
        historyList.hidden = true;


        try {

            let query =
                supabaseClient
                    .from("classifications")
                    .select(
                        "file_name, predicted_label, display_name, confidence, created_at, image_path"
                    )
                    .eq(
                        "user_id",
                        currentUser.id
                    )
                    .order(
                        "created_at",
                        {
                            ascending: false
                        }
                    );


            // =================================
            // FROM DATE
            // =================================

            if (fromDate) {

                const start =
                    new Date(
                        fromDate + "T00:00:00"
                    );


                query = query.gte(
                    "created_at",
                    start.toISOString()
                );

            }


            // =================================
            // TO DATE
            // =================================

            if (toDate) {

                const end =
                    new Date(
                        toDate + "T00:00:00"
                    );


                end.setDate(
                    end.getDate() + 1
                );


                query = query.lt(
                    "created_at",
                    end.toISOString()
                );

            }

            // =================================
            // SEARCH DATE
            // =================================

            const searchDate =
                historySearchDate.value;

            if (searchDate) {

                const start =
                    new Date(
                        searchDate + "T00:00:00"
                    );

                const end =
                    new Date(
                        searchDate + "T00:00:00"
                    );

                end.setDate(
                    end.getDate() + 1
                );

                query = query
                    .gte(
                        "created_at",
                        start.toISOString()
                    )
                    .lt(
                        "created_at",
                        end.toISOString()
                    );
            }

            const {
                data,
                error
            } = await query;


            if (error) {
                throw error;
            }


            historyLoading.hidden = true;


            if (!data || data.length === 0) {

                showEmptyState(
                    fromDate ||
                    toDate ||
                    historySearchDate.value ||
                    fabricFilter.value
                );

                return;

            }


            // =================================
            // DISPLAY RESULTS
            // =================================

            historyList.innerHTML = "";

            const signedByPath = {};
            const imagePaths = data
                .map(function (item) {
                    return item.image_path;
                })
                .filter(Boolean);

            if (imagePaths.length) {
                const { data: signedFiles, error: signedError } =
                    await supabaseClient.storage
                        .from("classification-images")
                        .createSignedUrls(imagePaths, 3600);

                if (signedError) {
                    console.error("History image URL error:", signedError);
                } else if (signedFiles) {
                    signedFiles.forEach(function (file) {
                        if (file.path && file.signedUrl) {
                            signedByPath[file.path] = file.signedUrl;
                        }
                    });
                }
            }


            data.forEach(function (item) {

                const card =
                    document.createElement("article");


                card.className =
                    "history-card";


                card.dataset.fabric =
                    item.display_name || "";


                card.dataset.filename =
                    item.file_name || "";


                const confidence =
                    Number(item.confidence) * 100;


                const formattedConfidence =
                    confidence.toFixed(1) + "%";


                const date =
                    new Date(
                        item.created_at
                    );


                const formattedDate =
                    date.toLocaleDateString(
                        undefined,
                        {
                            year: "numeric",
                            month: "long",
                            day: "numeric"
                        }
                    );


                const formattedTime =
                    date.toLocaleTimeString(
                        undefined,
                        {
                            hour: "numeric",
                            minute: "2-digit"
                        }
                    );


                const imageUrl =
                    signedByPath[item.image_path] || "";


                card.innerHTML = `

                    ${imageUrl
                        ? `<img class="history-photo" src="${escapeHtml(imageUrl)}" alt="">`
                        : ""}

                    <div class="history-card-main">

                        <span class="history-label">
                            TEXTILE CLASSIFICATION
                        </span>

                        <h2>
                            ${escapeHtml(
                                item.display_name
                            )}
                        </h2>

                        <p class="history-file-name">
                            ${escapeHtml(
                                item.file_name ||
                                "Unnamed image"
                            )}
                        </p>

                    </div>


                    <div class="history-card-details">

                        <div class="history-detail">

                            <span>
                                Confidence
                            </span>

                            <strong>
                                ${formattedConfidence}
                            </strong>

                        </div>


                        <div class="history-detail">

                            <span>
                                Date
                            </span>

                            <strong>
                                ${formattedDate}
                            </strong>

                        </div>


                        <div class="history-detail">

                            <span>
                                Time
                            </span>

                            <strong>
                                ${formattedTime}
                            </strong>

                        </div>

                    </div>

                `;


                historyList.appendChild(card);

            });


            historyList.hidden = false;


            // Apply fabric/search filters
            filterDisplayedHistory();


        } catch (error) {

            console.error(
                "History loading error:",
                error
            );

            historyLoading.hidden = true;
            historyError.hidden = false;

        }

    }


    // =================================
    // SEARCH + FABRIC FILTER
    // =================================

    function filterDisplayedHistory() {

        const selectedFabric =
            fabricFilter.value
                .trim()
                .toLowerCase();

        const cards =
            historyList.querySelectorAll(
                ".history-card"
            );

        let visibleCount = 0;

        cards.forEach(function (card) {

            const fabric =
                card.dataset.fabric
                    .toLowerCase();

            const matchesFabric =
                !selectedFabric ||
                fabric === selectedFabric;

            if (matchesFabric) {

                card.style.display = "";
                visibleCount++;

            } else {

                card.style.display = "none";

            }

        });


        if (visibleCount === 0) {

            historyList.hidden = true;

            historyEmpty.hidden = false;

            historyEmpty.querySelector("h2").textContent =
                "No Classifications Found";

            historyEmpty.querySelector("p").textContent =
                "No classifications match your selected filters.";

        } else {

            historyList.hidden = false;
            historyEmpty.hidden = true;

        }

    }


    // =================================
    // EMPTY STATE
    // =================================

    function showEmptyState(hasFilter) {

        historyList.innerHTML = "";
        historyList.hidden = true;

        historyEmpty.hidden = false;


        historyEmpty.querySelector("h2").textContent =
            hasFilter
                ? "No Classifications Found"
                : "No Classifications Yet";


        historyEmpty.querySelector("p").textContent =
            hasFilter
                ? "There are no classifications matching the selected date range."
                : "Upload a textile image from the Classify Textile page to start building your classification history.";

    }


    // =================================
    // LOCAL DATE
    // =================================

    function getLocalDateString() {

        const now =
            new Date();


        const year =
            now.getFullYear();


        const month =
            String(
                now.getMonth() + 1
            ).padStart(2, "0");


        const day =
            String(
                now.getDate()
            ).padStart(2, "0");


        return `${year}-${month}-${day}`;

    }

});


function escapeHtml(value) {

    const div =
        document.createElement("div");

    div.textContent =
        value;

    return div.innerHTML;

}