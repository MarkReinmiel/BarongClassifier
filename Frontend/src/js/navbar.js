
document.addEventListener("DOMContentLoaded", function () {

    const navbarContainer = document.getElementById("navbar");

    if (!navbarContainer) {
        return;
    }

    fetch("../components/navbar.html?v=3", { cache: "no-cache" })
        .then(function (response) {

            if (!response.ok) {
                throw new Error("Navbar could not be loaded.");
            }

            return response.text();

        })
        .then(async function (data) {

            navbarContainer.innerHTML = data;

            const currentPage = window.location.pathname
                .split("/")
                .pop()
                .replace(".html", "");

            const navKey = currentPage === "result"
                ? "classify"
                : currentPage;

            navbarContainer.querySelectorAll(
                '[data-nav="' + navKey + '"]'
            ).forEach(function (activeLink) {
                activeLink.classList.add("active");
            });


            // ==============================
            // MOBILE MENU
            // ==============================

            const navbar =
                navbarContainer.querySelector(".navbar");

            const menuToggle =
                document.getElementById("menuToggle");

            function setMenuOpen(isOpen) {

                if (!navbar || !menuToggle) {
                    return;
                }

                navbar.classList.toggle("is-open", isOpen);
                menuToggle.setAttribute(
                    "aria-expanded",
                    isOpen ? "true" : "false"
                );
                menuToggle.setAttribute(
                    "aria-label",
                    isOpen ? "Close menu" : "Open menu"
                );
                document.body.classList.toggle("nav-open", isOpen);

            }

            if (menuToggle && navbar) {

                menuToggle.addEventListener("click", function (event) {

                    event.stopPropagation();

                    const accountDropdown =
                        document.getElementById("accountDropdown");

                    if (accountDropdown) {
                        accountDropdown.hidden = true;
                    }

                    setMenuOpen(!navbar.classList.contains("is-open"));

                });

                navbar.querySelectorAll(".navbar-links a")
                    .forEach(function (link) {

                        link.addEventListener("click", function () {
                            setMenuOpen(false);
                        });

                    });

                document.addEventListener("keydown", function (event) {

                    if (event.key === "Escape") {
                        setMenuOpen(false);
                    }

                });

            }


            // ==============================
            // ACCOUNT DROPDOWN
            // ==============================

            const accountButton =
                document.getElementById("accountButton");

            const accountDropdown =
                document.getElementById("accountDropdown");

            const accountName =
                document.getElementById("accountName");

            const accountEmail =
                document.getElementById("accountEmail");


            function showAccount(name, email) {
                if (accountName) {
                    accountName.textContent = name;
                }
                if (accountEmail) {
                    accountEmail.textContent = email;
                }
            }

            // The session listener fires as soon as Supabase knows the
            // session (and again after a token refresh), so the name can
            // never stay stuck on "Loading...". Nothing is awaited inside
            // the callback, which keeps it safe with the Supabase lock.
            function loadNameFromProfiles(user) {
                var email = user.email || "";

                setTimeout(function () {
                    supabaseClient
                        .from("profiles")
                        .select("full_name")
                        .eq("id", user.id)
                        .maybeSingle()
                        .then(function (result) {
                            var name =
                                result && result.data
                                    ? String(result.data.full_name || "").trim()
                                    : "";

                            if (name) {
                                showAccount(name, email);

                                try {
                                    localStorage.setItem("barongDisplayName", name);
                                } catch (ignore) {
                                    // Storage can be blocked; the page still works.
                                }
                            }
                        })
                        .catch(function () {
                            // No profiles table or no row — keep what we have.
                        });
                }, 0);
            }

            function renderUser(user) {

                if (!user) {
                    showAccount("Not signed in", "");
                    return;
                }

                var email = user.email || "";
                var fullName = "";

                try {
                    fullName = String(
                        (user.user_metadata && user.user_metadata.full_name) ||
                        localStorage.getItem("barongDisplayName") ||
                        ""
                    ).trim();
                } catch (ignore) {
                    fullName = "";
                }

                showAccount(
                    fullName || email || "Account",
                    fullName ? email : ""
                );

                if (!fullName) {
                    loadNameFromProfiles(user);
                }

            }

            if (typeof supabaseClient === "undefined") {

                showAccount("Account", "");

            } else if (accountName || accountEmail) {

                try {

                    supabaseClient.auth.onAuthStateChange(
                        function (event, session) {
                            renderUser(session && session.user);
                        }
                    );

                } catch (error) {

                    console.error("Unable to retrieve account:", error);
                    showAccount("Account", "");

                }

            }


            // ==============================
            // OPEN/CLOSE DROPDOWN
            // ==============================

            if (accountButton && accountDropdown) {

                accountButton.addEventListener("click", function (event) {

                    event.stopPropagation();

                    const willOpen = accountDropdown.hidden;

                    accountDropdown.hidden = !willOpen;
                    accountButton.setAttribute(
                        "aria-expanded",
                        willOpen ? "true" : "false"
                    );

                    if (willOpen) {
                        setMenuOpen(false);
                    }

                });

                document.addEventListener("click", function (event) {

                    if (
                        !accountDropdown.contains(event.target) &&
                        !accountButton.contains(event.target)
                    ) {

                        accountDropdown.hidden = true;

                    }

                });

            }


            // ==============================
            // LOGOUT
            // ==============================

            const logoutButton =
                document.getElementById("logoutButton");

            if (logoutButton) {

                logoutButton.addEventListener("click", async function () {

                    logoutButton.disabled = true;
                    logoutButton.textContent = "Signing out...";

                    try {

                        if (typeof supabaseClient !== "undefined") {
                            await supabaseClient.auth.signOut();
                        }

                    } catch (error) {

                        console.error("Logout error:", error);

                    }

                    window.location.href = "auth.html";

                });

            }

        })
        .catch(function (error) {

            console.error("Navbar error:", error);

        });

});