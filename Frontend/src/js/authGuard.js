document.addEventListener("DOMContentLoaded", async function () {

    if (typeof supabaseClient === "undefined") {
        console.error("Supabase client is not loaded.");
        window.location.href = "auth.html";
        return;
    }

    const { data, error } = await supabaseClient.auth.getSession();
    const session = data && data.session;

    if (error || !session) {
        window.location.href = "auth.html";
        return;
    }

    const { data: profile, error: profileError } = await supabaseClient
        .from("users")
        .select("is_active, email_verified, must_change_password, role, full_name")
        .eq("id", session.user.id)
        .maybeSingle();

    if (profileError || !profile || !profile.is_active || !profile.email_verified) {
        await supabaseClient.auth.signOut();
        window.location.href = "auth.html";
        return;
    }

    const page = window.location.pathname.split("/").pop();

    if (profile.must_change_password && page !== "account.html") {
        window.location.href = "account.html";
        return;
    }

    if (page === "admin.html" && profile.role !== "admin") {
        window.location.href = "dashboard.html";
    }

    document.body.dataset.role = profile.role || "customer";

});
