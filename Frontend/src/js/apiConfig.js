// The CNN runs on the laptop. When the site is opened from a phone as
// http://<laptop-ip>:5500, the classifier is reached on that same laptop IP.
const CLASSIFIER_PORT = 5501;

const CLASSIFIER_HOST = (function () {
    const host = window.location.hostname;

    if (
        !host ||
        host === "localhost" ||
        host === "127.0.0.1" ||
        host === "[::1]" ||
        host === "::1"
    ) {
        return "127.0.0.1";
    }

    return host;
})();

const CLASSIFIER_BASE_URL =
    "http://" + CLASSIFIER_HOST + ":" + CLASSIFIER_PORT;

const CLASSIFIER_IS_REMOTE = CLASSIFIER_HOST !== "127.0.0.1";

function classifierOfflineMessage() {
    if (CLASSIFIER_IS_REMOTE) {
        return (
            "Cannot connect to the classification server. Make sure your " +
            "laptop and phone are connected to the same Wi-Fi, the classifier " +
            "was started with --host 0.0.0.0, and Windows Firewall allows " +
            "port " + CLASSIFIER_PORT + "."
        );
    }

    return (
        "Cannot connect to the classification server. Start it with: " +
        "python \"Backend/machine learning/classify_server.py\""
    );
}
