/* Shared fetch helpers — the frontend is served by FastAPI itself (same origin). */
async function api(path, method = "GET", body) {
  const headers = body ? { "Content-Type": "application/json" } : {};
  const token = sessionStorage.getItem("admin_token");
  if (token && path.startsWith("/api/admin")) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 401 && path.startsWith("/api/admin")) {
    sessionStorage.removeItem("admin_token");
    if (typeof onUnauthorized === "function") onUnauthorized();
  }
  return res.json();
}
const get  = (p) => api(p);
const post = (p, b) => api(p, "POST", b);
const del  = (p) => api(p, "DELETE");
const el   = (id) => document.getElementById(id);
const badge = (s) => `<span class="pill pill-${(s || "").replace(/\W/g, "_")}">${s || "?"}</span>`;