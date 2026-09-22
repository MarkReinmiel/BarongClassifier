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
