document.addEventListener("DOMContentLoaded", async function () {

    if (typeof supabaseClient !== "undefined") {
        const { data } = await supabaseClient.auth.getSession();

        if (data.session) {
            window.location.href = "dashboard.html";
            return;
        }
    }

    const loginSection = document.getElementById("loginForm");
    const signupSection = document.getElementById("signupForm");
    const showSignup = document.getElementById("showSignup");
    const showLogin = document.getElementById("showLogin");
    const authMessage = document.getElementById("authMessage");

    function showMessage(text, type) {
        if (!authMessage) {
            return;
        }

        authMessage.textContent = text;
        authMessage.hidden = false;
        authMessage.className = "auth-message " + type;
    }

    const savedNotice = sessionStorage.getItem("barongAuthNotice");
    if (savedNotice) {
        sessionStorage.removeItem("barongAuthNotice");
        showMessage(savedNotice, "success");
    }

    function clearMessage() {
        if (!authMessage) {
            return;
        }

        authMessage.textContent = "";
        authMessage.hidden = true;
        authMessage.className = "auth-message";
    }

    function setLoading(button, isLoading, idleLabel) {
        if (!button) {
            return;
        }

        button.disabled = isLoading;
        button.textContent = isLoading ? "Please wait..." : idleLabel;
    }

    if (showSignup && loginSection && signupSection) {
        showSignup.addEventListener("click", function () {
            clearMessage();
            loginSection.classList.remove("active");
            signupSection.classList.add("active");
        });
    }

    if (showLogin && loginSection && signupSection) {
        showLogin.addEventListener("click", function () {
            clearMessage();
            signupSection.classList.remove("active");
            loginSection.classList.add("active");
        });
    }

    const loginForm = document.getElementById("login");

    if (loginForm) {
        loginForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            clearMessage();

            const email = document
                .getElementById("loginEmail")
                .value.trim();
            const password = document.getElementById("loginPassword").value;
            const submitButton = loginForm.querySelector(".auth-button");

            setLoading(submitButton, true, "Login →");

            try {
                const response = await fetch(AUTH_API_BASE + "/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        email: email,
                        password: password
                    })
                });
                const payload = await response.json().catch(function () {
                    return {};
                });

                if (!response.ok) {
                    showMessage(
                        payload.error || "Invalid email or password.",
                        "error"
                    );
                    return;
                }

                if (payload.verification_required) {
                    sessionStorage.setItem(
                        "barongVerificationToken",
                        payload.verification_token
                    );
                    sessionStorage.setItem(
                        "barongVerificationHint",
                        payload.email_hint || ""
                    );
                    window.location.href = "verify-email.html";
                    return;
                }

                const session = payload.session || {};
                let sessionError = null;

                if (session.access_token && session.refresh_token) {
                    const restored = await supabaseClient.auth.setSession({
                        access_token: session.access_token,
                        refresh_token: session.refresh_token
                    });
                    sessionError = restored.error;
                } else {
                    sessionError = { message: "missing session" };
                }

                if (sessionError) {
                    const direct = await supabaseClient.auth.signInWithPassword({
                        email: email,
                        password: password
                    });

                    if (direct.error) {
                        showMessage(
                            direct.error.message || "Unable to sign in. Please try again.",
                            "error"
                        );
                        return;
                    }
                }

                window.location.href = payload.must_change_password
                    ? "account.html"
                    : "dashboard.html";
            } catch (error) {
                showMessage(
                    "Unable to reach the authentication server. Start it with: python Backend/main.py",
                    "error"
                );
            } finally {
                setLoading(submitButton, false, "Login →");
            }
        });
    }

    const signupForm = document.getElementById("signup");

    document.querySelectorAll(".password-toggle").forEach(function (button) {
        button.addEventListener("click", function () {
            const input = document.getElementById(button.dataset.target);

            if (!input) {
                return;
            }

            const showing = input.type === "text";
            input.type = showing ? "password" : "text";
            button.textContent = showing ? "Show" : "Hide";
        });
    });

    if (signupForm) {
        signupForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            clearMessage();

            if (typeof supabaseClient === "undefined") {
                showMessage(
                    "Supabase is not loaded. Serve the site over HTTP and refresh.",
                    "error"
                );
                return;
            }

            const fullName = document
                .getElementById("signupName")
                .value.trim();
            const email = document
                .getElementById("signupEmail")
                .value.trim();
            const password = document.getElementById("signupPassword").value;
            const submitButton = signupForm.querySelector(".auth-button");

            setLoading(submitButton, true, "Create Account →");

            try {
                const response = await fetch(AUTH_API_BASE + "/api/auth/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        full_name: fullName,
                        email: email,
                        password: password
                    })
                });
                const payload = await response.json().catch(function () {
                    return {};
                });

                if (!response.ok) {
                    showMessage(
                        payload.error || "Unable to create an account. Please try again.",
                        "error"
                    );
                    return;
                }

                if (payload.verification_required && payload.verification_token) {
                    sessionStorage.setItem(
                        "barongVerificationToken",
                        payload.verification_token
                    );
                    sessionStorage.setItem(
                        "barongVerificationHint",
                        payload.email_hint || ""
                    );
                    window.location.href = "verify-email.html";
                    return;
                }

                showMessage(
                    payload.message || "Check your email for the next step.",
                    "success"
                );
                signupSection.classList.remove("active");
                loginSection.classList.add("active");
            } catch (error) {
                showMessage(
                    "Unable to reach the authentication server. Start it with: python Backend/main.py",
                    "error"
                );
            } finally {
                setLoading(submitButton, false, "Create Account →");
            }
        });
    }

});
