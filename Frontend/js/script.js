const getStartedBtn = document.getElementById("getStartedBtn");
const navGetStarted = document.getElementById("navGetStarted");

if (getStartedBtn) {
    getStartedBtn.addEventListener("click", function () {
        window.location.href = "auth.html";
    });
}

if (navGetStarted) {
    navGetStarted.addEventListener("click", function () {
        window.location.href = "auth.html";
    });
}