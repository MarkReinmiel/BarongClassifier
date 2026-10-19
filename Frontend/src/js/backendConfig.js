// Auth API on this computer. The classifier stays on its own port.
const AUTH_API_BASE = (function () {
    const host = window.location.hostname;
    if (!host || host === "localhost" || host === "127.0.0.1" || host === "::1") {
        return "http://127.0.0.1:8000";
    }
    return window.location.protocol + "//" + host + ":8000";
})();
