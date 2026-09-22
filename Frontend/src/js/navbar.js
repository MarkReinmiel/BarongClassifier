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

        })
        .catch(function (error) {

            console.error("Navbar error:", error);

        });

});
