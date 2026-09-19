document.addEventListener("DOMContentLoaded", function () {

    // Login form
    const loginForm = document.getElementById("login");

    if (loginForm) {

        loginForm.addEventListener("submit", function (event) {

            event.preventDefault();

            const usernameInput =
                document.getElementById("loginUsername");

            const passwordInput =
                document.getElementById("loginPassword");

            const username = usernameInput.value.trim();
            const password = passwordInput.value;

            if (username === "user" && password === "user") {

                alert("Login successful!");

                window.location.href = "dashboard.html";

            } else {

                alert("Invalid username or password.");

            }

        });

    }


    // Login / Sign Up switching

    const loginSection =
        document.getElementById("loginForm");

    const signupSection =
        document.getElementById("signupForm");

    const showSignup =
        document.getElementById("showSignup");

    const showLogin =
        document.getElementById("showLogin");


    if (
        showSignup &&
        loginSection &&
        signupSection
    ) {

        showSignup.addEventListener("click", function () {

            loginSection.classList.remove("active");

            signupSection.classList.add("active");

        });

    }


    if (
        showLogin &&
        loginSection &&
        signupSection
    ) {

        showLogin.addEventListener("click", function () {

            signupSection.classList.remove("active");

            loginSection.classList.add("active");

        });

    }


    // Sign Up form

    const signupForm =
        document.getElementById("signup");

    if (signupForm) {

        signupForm.addEventListener("submit", function (event) {

            event.preventDefault();

            alert("Account creation will be connected later.");

        });

    }

});