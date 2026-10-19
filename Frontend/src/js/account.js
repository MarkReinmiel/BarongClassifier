document.addEventListener("DOMContentLoaded", function () {
    const summary = document.getElementById("accountSummary");
    const form = document.getElementById("passwordForm");
    const status = document.getElementById("accountStatus");

    supabaseClient.auth.getSession().then(function (result) {
        const session = result.data && result.data.session;
        if (!session) {
            return;
        }
        fetch(AUTH_API_BASE + "/api/auth/me", {
            headers: { Authorization: "Bearer " + session.access_token }
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (profile) {
                if (!profile || profile.error) {
                    return;
                }
                summary.textContent =
                    (profile.full_name || "Account") +
                    " · " +
                    profile.email +
                    " · " +
                    profile.role;
                if (profile.must_change_password) {
                    show("Change the temporary password before using the rest of the app.", "error");
                }
            })
            .catch(function () {
                show("Account details could not be loaded.", "error");
            });
    });

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        const sessionResult = await supabaseClient.auth.getSession();
        const session = sessionResult.data && sessionResult.data.session;
        if (!session) {
            window.location.href = "auth.html";
            return;
        }
        const button = form.querySelector("button");
        button.disabled = true;
        try {
            const response = await fetch(AUTH_API_BASE + "/api/auth/change-password", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: "Bearer " + session.access_token
                },
                body: JSON.stringify({
                    new_password: document.getElementById("newPassword").value
                })
            });
            const payload = await response.json().catch(function () {
                return {};
            });
            if (!response.ok) {
                show(payload.error || "The password was not changed.", "error");
                return;
            }
            show("Password updated.", "success");
            window.setTimeout(function () {
                window.location.href = "dashboard.html";
            }, 600);
        } catch (error) {
            show("The authentication server could not be reached.", "error");
        } finally {
            button.disabled = false;
        }
    });

    function show(message, type) {
        status.hidden = false;
        status.textContent = message;
        status.className = "auth-message " + type;
    }
});
