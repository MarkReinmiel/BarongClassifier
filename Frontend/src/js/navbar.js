document.addEventListener("DOMContentLoaded", function () {

    const navbarContainer = document.getElementById("navbar");

    if (!navbarContainer) {
        return;
    }

    fetch("../components/navbar.html")
        .then(response => {

            if (!response.ok) {
                throw new Error("Navbar could not be loaded.");
            }

            return response.text();

        })
        .then(data => {

            navbarContainer.innerHTML = data;

        })
        .catch(error => {

            console.error("Navbar error:", error);

        });

});