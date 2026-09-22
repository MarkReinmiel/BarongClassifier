
document.addEventListener("DOMContentLoaded", function () {

    const navbarContainer = document.getElementById("navbar");

    if (!navbarContainer) {
        return;
    }

    fetch("../components/navbar.html")
        .then(function (response) {

            if (!response.ok) {
                throw new Error("Navbar could not be loaded.");
            }

            return response.text();

        })
        .then(async function (data) {

            navbarContainer.innerHTML = data;

            const currentPage = window.location.pathname
                .split("/")
                .pop()
                .replace(".html", "");

            const activeLink = navbarContainer.querySelector(
                '[data-nav="' + currentPage + '"]'
            );

            if (activeLink) {
                activeLink.classList.add("active");
            }


            // ==============================
            // ACCOUNT DROPDOWN
            // ==============================

            const accountButton =
                document.getElementById("accountButton");

            const accountDropdown =
                document.getElementById("accountDropdown");

            const accountName =
                document.getElementById("accountName");

            const accountEmail =
                document.getElementById("accountEmail");


            if (
                typeof supabaseClient !== "undefined" &&
                accountName &&
                accountEmail
            ) {

                const { data: sessionData, error } =
                    await supabaseClient.auth.getSession();

                if (error) {
                    console.error(
                        "Unable to retrieve account:",
                        error
                    );
                }

                const user = sessionData.session?.user;

                if (user) {

                    const fullName =
                        user.user_metadata?.full_name;

                    accountName.textContent =
                        fullName || user.email || "Account";

                    accountEmail.textContent =
                        user.email || "No email available";

                } else {

                    accountName.textContent = "Account";
                    accountEmail.textContent = "Not signed in";

                }

            }


            // ==============================
            // OPEN/CLOSE DROPDOWN
            // ==============================

            if (accountButton && accountDropdown) {

                accountButton.addEventListener("click", function (event) {

                    event.stopPropagation();

                    accountDropdown.hidden =
                        !accountDropdown.hidden;

                });

                document.addEventListener("click", function (event) {

                    if (
                        !accountDropdown.contains(event.target) &&
                        !accountButton.contains(event.target)
                    ) {

                        accountDropdown.hidden = true;

                    }

                });

            }


            // ==============================
            // LOGOUT
            // ==============================

            const logoutButton =
                document.getElementById("logoutButton");

            if (logoutButton) {

                logoutButton.addEventListener("click", async function () {

                    logoutButton.disabled = true;
                    logoutButton.textContent = "Signing out...";

                    try {

                        if (typeof supabaseClient !== "undefined") {
                            await supabaseClient.auth.signOut();
                        }

                    } catch (error) {

                        console.error("Logout error:", error);

                    }

                    window.location.href = "auth.html";

                });

            }

        })
        .catch(function (error) {

            console.error("Navbar error:", error);

        });

});