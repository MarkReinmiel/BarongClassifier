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
                const { data, error } =
                    await supabaseClient.auth.signInWithPassword({
                        email: email,
                        password: password
                    });

                if (error) {
                    showMessage(error.message, "error");
                    return;
                }

                if (data.session) {
                    try {
                        const user = data.session.user;
                        await supabaseClient.from("profiles").upsert({
                            id: user.id,
                            email: user.email,
                            full_name:
                                (user.user_metadata &&
                                    user.user_metadata.full_name) ||
                                ""
                        });
                    } catch (profileError) {
                        console.error("Profile save error:", profileError);
                    }

                    window.location.href = "dashboard.html";
                }
            } catch (error) {
                showMessage(
                    error.message || "Unable to sign in. Please try again.",
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
                const { data, error } = await supabaseClient.auth.signUp({
                    email: email,
                    password: password,
                    options: {
                        data: {
                            full_name: fullName
                        },
                        emailRedirectTo:
                            window.location.origin +
                            window.location.pathname.replace(
                                /[^/]+$/,
                                "auth.html"
                            )
                    }
                });

                if (error) {
                    const message = error.message || "";
                    if (
                        /rate limit/i.test(message) ||
                        /over_email_send_rate_limit/i.test(message)
                    ) {
                        showMessage(
                            "Supabase email limit reached. No confirmation email can be sent right now. In the project dashboard turn Confirm email OFF, or wait and try again later.",
                            "error"
                        );
                        return;
                    }
                    showMessage(message, "error");
                    return;
                }

                const createdUser = data.user;
                const identityCount =
                    createdUser && createdUser.identities
                        ? createdUser.identities.length
                        : 0;

                if (!createdUser || identityCount === 0) {
                    showMessage(
                        "No account was created. This email may already be registered, confirm your email first, or check Authentication > Users in the new Supabase project.",
                        "error"
                    );
                    return;
                }

                // Keep a visible row in public.profiles (Table Editor).
                // Auth itself already stores the account in Authentication > Users.
                if (data.session) {
                    try {
                        await supabaseClient.from("profiles").upsert({
                            id: createdUser.id,
                            email: createdUser.email,
                            full_name: fullName
                        });
                    } catch (profileError) {
                        console.error("Profile save error:", profileError);
                    }

                    window.location.href = "dashboard.html";
                    return;
                }

                showMessage(
                    "Account created in Authentication. Confirm your email, then sign in. After confirmation it can also appear in the profiles table.",
                    "success"
                );

                signupSection.classList.remove("active");
                loginSection.classList.add("active");
            } catch (error) {
                showMessage(
                    error.message || "Unable to sign up. Please try again.",
                    "error"
                );
            } finally {
                setLoading(submitButton, false, "Create Account →");
            }
        });
    }

});
