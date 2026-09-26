const getStartedBtn = document.getElementById("getStartedBtn");
const navGetStarted = document.getElementById("navGetStarted");

function goToAppEntry() {
    window.location.href = "auth.html";
}

if (getStartedBtn) {
    getStartedBtn.addEventListener("click", goToAppEntry);
}

if (navGetStarted) {
    navGetStarted.addEventListener("click", goToAppEntry);
}

const landingMenu = document.getElementById("landingMenu");
const landingNav = document.getElementById("landingNav");
const landingBar = document.querySelector(".navbar");

function setLandingMenu(isOpen) {
    if (!landingMenu || !landingBar) {
        return;
    }

    landingBar.classList.toggle("is-open", isOpen);
    landingMenu.setAttribute("aria-expanded", isOpen ? "true" : "false");
    landingMenu.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
}

if (landingMenu) {
    landingMenu.addEventListener("click", function () {
        setLandingMenu(!landingBar.classList.contains("is-open"));
    });
}

if (landingNav) {
    landingNav.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
            setLandingMenu(false);
        });
    });
}
