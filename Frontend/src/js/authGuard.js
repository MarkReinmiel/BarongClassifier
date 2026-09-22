document.addEventListener("DOMContentLoaded", async function () {

    if (typeof supabaseClient === "undefined") {
        console.error("Supabase client is not loaded.");
        window.location.href = "auth.html";
        return;
    }

    const { data, error } = await supabaseClient.auth.getSession();

    if (error || !data.session) {
        window.location.href = "auth.html";
    }

});
