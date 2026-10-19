document.addEventListener("DOMContentLoaded", function () {
    const token = sessionStorage.getItem("barongVerificationToken");
    const hint = sessionStorage.getItem("barongVerificationHint") || "your email";
    const form = document.getElementById("verifyForm");
    const input = document.getElementById("codeInput");
    const status = document.getElementById("verifyStatus");
    const resendButton = document.getElementById("resendButton");
    const verifyButton = document.getElementById("verifyButton");
    const hintNode = document.getElementById("verifyHint");
    let submitting = false;
    let remaining = 60;
    let timerId = null;

    if (hintNode) {
        hintNode.textContent = "Code sent to " + hint + ".";
    }

    if (!token) {
        show("Sign in again to request a verification code.", "error");
        resendButton.disabled = true;
        verifyButton.disabled = true;
        return;
    }

    input.addEventListener("input", function () {
        input.value = input.value.replace(/\D/g, "").slice(0, 6);
    });

    input.addEventListener("paste", function (event) {
        const text = (event.clipboardData || window.clipboardData).getData("text");
        const digits = String(text || "").replace(/\D/g, "").slice(0, 6);
        if (!digits) {
            return;
        }
        event.preventDefault();
        input.value = digits;
    });

    function show(message, type) {
        status.hidden = false;
        status.textContent = message;
        status.className = "auth-message " + type;
    }

    function tick() {
        remaining -= 1;
        if (remaining <= 0) {
            clearInterval(timerId);
            resendButton.disabled = false;
            resendButton.textContent = "Resend Verification Email";
            return;
        }
        resendButton.disabled = true;
        resendButton.textContent = "Resend available in " + remaining + " seconds";
    }

    function startCountdown(seconds) {
        clearInterval(timerId);
        remaining = Math.max(0, Number(seconds) || 0);
        if (remaining <= 0) {
            resendButton.disabled = false;
            resendButton.textContent = "Resend Verification Email";
            return;
        }
        resendButton.disabled = true;
        resendButton.textContent = "Resend available in " + remaining + " seconds";
        timerId = setInterval(tick, 1000);
    }

    fetch(
        AUTH_API_BASE + "/api/auth/verification-status?verification_token=" + encodeURIComponent(token)
    )
        .then(function (response) {
            return response.json().then(function (payload) {
                return { ok: response.ok, payload: payload };
            });
        })
        .then(function (result) {
            if (!result.ok) {
                show(result.payload.error || "Sign in again to request a verification code.", "error");
                startCountdown(0);
                return;
            }
            startCountdown(result.payload.resend_after_seconds || 0);
        })
        .catch(function () {
            startCountdown(60);
        });

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        if (submitting) {
            return;
        }
        const code = input.value;
        if (!/^\d{6}$/.test(code)) {
            show("Enter the six-digit code from your email.", "error");
            return;
        }
        submitting = true;
        verifyButton.disabled = true;
        show("Checking the code...", "");
        try {
            const response = await fetch(AUTH_API_BASE + "/api/auth/verify-code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    verification_token: token,
                    code: code
                })
            });
            const payload = await response.json().catch(function () {
                return {};
            });
            if (!response.ok) {
                show(payload.error || "That code could not be verified.", "error");
                return;
            }

            if (!payload.session) {
                sessionStorage.removeItem("barongVerificationToken");
                sessionStorage.removeItem("barongVerificationHint");
                sessionStorage.setItem(
                    "barongAuthNotice",
                    "Email verified. Sign in to continue."
                );
                window.location.href = "auth.html";
                return;
            }
            const { error } = await supabaseClient.auth.setSession({
                access_token: payload.session.access_token,
                refresh_token: payload.session.refresh_token
            });
            if (error) {
                show("The code was accepted, but the session could not be saved. Sign in again.", "error");
                return;
            }
            sessionStorage.removeItem("barongVerificationToken");
            sessionStorage.removeItem("barongVerificationHint");
            window.location.href = payload.must_change_password
                ? "account.html"
                : "dashboard.html";
        } catch (error) {
            show("The server could not be reached. Nothing was verified.", "error");
        } finally {
            submitting = false;
            verifyButton.disabled = false;
        }
    });

    resendButton.addEventListener("click", async function () {
        if (resendButton.disabled || submitting) {
            return;
        }
        resendButton.disabled = true;
        show("Sending a new code...", "");
        try {
            const response = await fetch(AUTH_API_BASE + "/api/auth/resend-code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ verification_token: token })
            });
            const payload = await response.json().catch(function () {
                return {};
            });
            if (!response.ok) {
                show(payload.error || "A new code was not sent.", "error");
                if (payload.retry_after_seconds) {
                    startCountdown(payload.retry_after_seconds);
                } else if (response.status === 429) {
                    startCountdown(60);
                } else {
                    resendButton.disabled = false;
                    resendButton.textContent = "Resend Verification Email";
                }
                return;
            }
            input.value = "";
            show("A new code was sent. It expires in one hour.", "success");
            startCountdown(payload.resend_after_seconds || 60);
        } catch (error) {
            show("The server could not be reached. A new code was not sent.", "error");
            resendButton.disabled = false;
            resendButton.textContent = "Resend Verification Email";
        }
    });
});
