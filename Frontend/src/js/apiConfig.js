// The CNN runs on the laptop. When the site is opened from a phone as
// http(s)://<laptop-ip>:..., the classifier is reached on that same laptop IP.
// HTTPS pages (needed for the phone camera) cannot call an http:// server, so
// they use the classifier's HTTPS port instead.
const CLASSIFIER_USES_HTTPS = window.location.protocol === "https:";

const CLASSIFIER_PORT = CLASSIFIER_USES_HTTPS ? 5502 : 5501;

const CLASSIFIER_HOST = (function () {
    const host = window.location.hostname;

    if (
        !host ||
        host === "localhost" ||
        host === "127.0.0.1" ||
        host === "[::1]" ||
        host === "::1"
    ) {
        return CLASSIFIER_USES_HTTPS ? "localhost" : "127.0.0.1";
    }

    return host;
})();

const CLASSIFIER_BASE_URL =
    (CLASSIFIER_USES_HTTPS ? "https://" : "http://") +
    CLASSIFIER_HOST + ":" + CLASSIFIER_PORT;

const CLASSIFIER_IS_REMOTE =
    CLASSIFIER_HOST !== "127.0.0.1" && CLASSIFIER_HOST !== "localhost";

function classifierOfflineMessage() {
    if (CLASSIFIER_USES_HTTPS) {
        return (
            "Cannot connect to the classification server. Make sure the " +
            "classifier was started with --host 0.0.0.0 --https, then open " +
            CLASSIFIER_BASE_URL + "/health once in this browser and tap " +
            "Advanced > Proceed to accept the local certificate."
        );
    }

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
