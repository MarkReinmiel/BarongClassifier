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
        .then(function (data) {

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
