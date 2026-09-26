const SUPABASE_URL = "https://sguodujpbonvlaarzutf.supabase.co";
const SUPABASE_ANON_KEY =
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNndW9kdWpwYm9udmxhYXJ6dXRmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTAwODYyMDIsImV4cCI6MjEwNTY2MjIwMn0.56kNohdvp_sx8xvOuLQn2WS_0XoYeFQ53wehqAZKPIU";

const supabaseClient = window.supabase.createClient(
    SUPABASE_URL,
    SUPABASE_ANON_KEY
);
