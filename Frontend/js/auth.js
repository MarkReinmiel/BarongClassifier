// =========================================
// LOGIN / SIGN UP SWITCHING
// =========================================

const loginForm = document.getElementById("loginForm");
const signupForm = document.getElementById("signupForm");

const showSignup = document.getElementById("showSignup");
const showLogin = document.getElementById("showLogin");


// Show Sign Up
showSignup.addEventListener("click", function () {

    loginForm.classList.remove("active");

    signupForm.classList.add("active");

});


// Show Login
showLogin.addEventListener("click", function () {

    signupForm.classList.remove("active");

    loginForm.classList.add("active");

});


// =========================================
// TEMPORARY LOGIN
// =========================================

document.getElementById("login").addEventListener("submit", function (event) {

    event.preventDefault();

    alert("Login will be connected to Supabase Auth.");

});


// =========================================
// TEMPORARY SIGN UP
// =========================================

document.getElementById("signup").addEventListener("submit", function (event) {

    event.preventDefault();

    alert("Registration will be connected to Supabase Auth.");

});