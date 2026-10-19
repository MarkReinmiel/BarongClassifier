document.addEventListener("DOMContentLoaded", async function () {
    const list = document.getElementById("adminUsers");
    const status = document.getElementById("adminStatus");
    const sessionResult = await supabaseClient.auth.getSession();
    const session = sessionResult.data && sessionResult.data.session;
    if (!session) {
        return;
    }

    const headers = {
        Authorization: "Bearer " + session.access_token,
        "Content-Type": "application/json"
    };

    function show(message) {
        status.hidden = false;
        status.textContent = message;
    }

    async function loadUsers() {
        const response = await fetch(AUTH_API_BASE + "/api/admin/users", { headers: headers });
        const payload = await response.json().catch(function () {
            return {};
        });
        if (!response.ok) {
            show(payload.error || "Users could not be loaded.");
            return;
        }
        list.innerHTML = "";
        (payload.users || []).forEach(function (user) {
            const card = document.createElement("article");
            card.className = "overview-card";
            card.style.marginBottom = "12px";
            const title = document.createElement("h3");
            title.textContent = (user.full_name || "User") + " · " + user.email;
            const meta = document.createElement("p");
            meta.textContent =
                user.role +
                (user.is_active ? " · active" : " · inactive") +
                (user.email_verified ? " · verified" : " · unverified");
            const roleSelect = document.createElement("select");
            ["customer", "owner"].forEach(function (role) {
                const option = document.createElement("option");
                option.value = role;
                option.textContent = role;
                option.selected = user.role === role;
                roleSelect.appendChild(option);
            });
            if (user.role === "admin") {
                roleSelect.disabled = true;
            }
            const saveRole = document.createElement("button");
            saveRole.type = "button";
            saveRole.textContent = "Save role";
            saveRole.addEventListener("click", function () {
                updateUser(user.id, "role", { role: roleSelect.value });
            });
            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.textContent = user.is_active ? "Deactivate" : "Activate";
            toggle.addEventListener("click", function () {
                updateUser(user.id, "status", { is_active: !user.is_active });
            });
            card.appendChild(title);
            card.appendChild(meta);
            card.appendChild(roleSelect);
            card.appendChild(saveRole);
            card.appendChild(toggle);
            list.appendChild(card);
        });
    }

    async function updateUser(userId, kind, body) {
        const response = await fetch(
            AUTH_API_BASE + "/api/admin/users/" + userId + "/" + kind,
            {
                method: "PATCH",
                headers: headers,
                body: JSON.stringify(body)
            }
        );
        const payload = await response.json().catch(function () {
            return {};
        });
        if (!response.ok) {
            show(payload.error || "That change was not saved.");
            return;
        }
        show("Saved.");
        loadUsers();
    }

    try {
        await loadUsers();
    } catch (error) {
        show("The authentication server could not be reached.");
    }
});
