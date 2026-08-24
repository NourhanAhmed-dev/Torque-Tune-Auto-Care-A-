/* Admin console: passcode gate + dashboard nav + theme + all live tables. */
function onUnauthorized() { location.reload(); }

function showPre(id, obj) {
  const p = el(id);
  p.style.display = "";
  p.textContent = JSON.stringify(obj, null, 2);
}

/* ---------- theme ---------- */
function toggleTheme() {
  const root = document.documentElement;
  const dark = root.getAttribute("data-theme") === "dark";
  if (dark) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", "dark");
  localStorage.setItem("tt_theme", dark ? "" : "dark");
  const b = el("theme_btn");
  if (b) b.textContent = dark ? "🌙" : "☀️";
}

/* ---------- auth ---------- */
async function login() {
  const r = await post("/api/admin/auth", { passcode: el("pass").value });
  if (r.token) { sessionStorage.setItem("admin_token", r.token); enter(); }
  else showPre("login_out", r);
}
function logout() { sessionStorage.removeItem("admin_token"); location.reload(); }
function enter() {
  el("login").style.display = "none";
  el("console").style.display = "";
  loadAll();
}
window.addEventListener("load", () => {
  const b = el("theme_btn");
  if (b) b.textContent =
    document.documentElement.getAttribute("data-theme") === "dark" ? "☀️" : "🌙";
  if (sessionStorage.getItem("admin_token")) enter();
});

function loadAll() { loadStats(); loadHitl(); loadTickets(); loadRuns(); loadTools(); loadDocs(); }

/* ---------- live stats strip ---------- */
async function loadStats() {
  try {
    const [h, t, r] = await Promise.all([
      get("/api/admin/hitl?status=pending"),
      get("/api/admin/tickets?status=open"),
      get("/api/admin/runs"),
    ]);
    el("stat_hitl").textContent = (h || []).length;
    el("stat_tickets").textContent = (t || []).length;
    el("stat_active").textContent = (r || []).filter(x =>
      ["running", "waiting_external", "waiting_hitl", "ticketed"].includes(x.status)).length;
    el("stat_done").textContent = (r || []).filter(x => x.status === "completed").length;
  } catch (e) { /* stats are decorative */ }
}

/* ---------- HITL ---------- */
async function loadHitl() {
  const rows = await get("/api/admin/hitl?status=pending");
  el("hitl_tbl").innerHTML = "<tr><th>ID</th><th>Run</th><th>Reason</th><th>Decision</th></tr>" +
    ((rows || []).map(q => `
      <tr><td><b>#${q.request_id}</b></td><td>${q.run_id}</td><td>${q.reason}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-success btn-sm" onclick="decide(${q.request_id},true)">Approve</button>
        <button class="btn btn-danger btn-sm" onclick="decide(${q.request_id},false)">Reject</button>
      </td></tr>`).join("")
    || `<tr><td class="empty" colspan="4">Queue is clear 🎉</td></tr>`);
}
async function decide(id, approved) {
  try {
    showPre("h_out", await post(`/api/admin/hitl/${id}/decide`, { approved, comment: "via-ui" }));
  } catch (e) {
    showPre("h_out", { ui_error: String(e) });
  }
  loadHitl(); loadRuns();
}

/* ---------- tickets ---------- */
async function loadTickets() {
  const rows = await get("/api/admin/tickets?status=open");
  el("tickets_tbl").innerHTML = "<tr><th>ID</th><th>Run</th><th>Error</th><th>Resolve</th></tr>" +
    ((rows || []).map(t => `
      <tr><td><b>#${t.ticket_id}</b></td><td>${t.run_id}</td><td>${t.error_message || ""}</td>
      <td style="white-space:nowrap">
        <input id="res_${t.ticket_id}" placeholder="resolution" style="width:110px;display:inline-block">
        <button class="btn btn-success btn-sm" onclick="resolve(${t.ticket_id})">Resolve</button>
      </td></tr>`).join("")
    || `<tr><td class="empty" colspan="4">No open tickets 🎉</td></tr>`);
}
async function resolve(id) {
  showPre("t_out", await post(`/api/admin/tickets/${id}/resolve`,
    { resolution: el("res_" + id).value || "fixed" }));
  loadStats(); loadTickets(); loadRuns();
}

/* ---------- runs ---------- */
async function loadRuns() {
  const rows = await get("/api/admin/runs");
  el("runs_tbl").innerHTML =
    "<tr><th>Run</th><th>Status</th><th>Providers</th><th>Current node</th><th>Provider</th><th></th></tr>" +
    (rows.map(r => {
      const rej = (r.rejected_providers || []).join(", ");
      const prov = (r.selected_provider ? `🚛 ${r.selected_provider}` : "—") +
                   (rej ? ` · ❌ rejected: ${rej}` : "");
      const isSourcing = String(r.run_id).startsWith("build_") || String(r.run_id).startsWith("src_");
      const isWarranty = String(r.run_id).startsWith("war_");
      const actions =
        (isSourcing && r.status === "waiting_external")
        ? `<button class="btn btn-primary btn-sm" onclick="autoStep('${r.run_id}')">Supplier step ▶</button>`
        : (isWarranty && r.status === "waiting_external")
        ? `<span class="hint">use the Warranty page ⬅</span>`
        : (!isSourcing && !isWarranty && r.status === "waiting_external")
        ? `<button class="btn btn-success btn-sm" onclick="sendEventFor('${r.run_id}','accepted')">Accept</button>
           <button class="btn btn-danger btn-sm" onclick="sendEventFor('${r.run_id}','rejected')">Reject</button>`
        : (r.status === "waiting_hitl" ? `<span class="hint">decide in HITL queue</span>` : "");
      return `<tr>
        <td><b>${r.run_id}</b></td><td>${badge(r.status)}</td><td>${prov}</td>
        <td>${r.current_state || ""}</td>
        <td style="white-space:nowrap">${actions}</td>
        <td><button class="btn btn-ghost btn-sm" onclick="showStory('${r.run_id}')">Story</button></td>
      </tr>`;
    }).join("") || `<tr><td class="empty" colspan="6">No runs yet</tr>`);
}
async function sendEventFor(run, response) {
  const r = await post(`/api/graphs/fleet_rescue/runs/${run}/event`, { response });
  showPre("ev_out", r); loadStats(); loadRuns();
}
async function showStory(run) {
  const t = await get(`/api/admin/runs/${run}/timeline`);
  el("ev_out").style.display = "";
  el("ev_out").textContent =
    t.steps.map(s => `${s.icon} ${s.title} — ${s.detail}`).join("\n") + "\n\n" + t.banner;
}

/* ---------- MCP tools ---------- */
async function loadTools() {
  const d = await get("/api/admin/tools");
  el("tools_tbl").innerHTML = "<tr><th>Tool</th><th>Status</th><th></th></tr>" +
    d.live_catalog.map(t => `<tr><td>${t}</td><td>${badge("enabled")}</td>
      <td><button class="btn btn-danger btn-sm" onclick="setTool('${t}',false)">Disable</button></td></tr>`).join("") +
    d.disabled.map(t => `<tr><td>${t}</td><td>${badge("disabled")}</td>
      <td><button class="btn btn-success btn-sm" onclick="setTool('${t}',true)">Enable</button></td></tr>`).join("");
}
async function setTool(name, enabled) { await post(`/api/admin/tools/${name}/set`, { enabled }); loadTools(); }

/* ---------- RAG documents ---------- */
async function loadDocs() {
  const docs = await get("/api/admin/resources/documents");
  el("docs_tbl").innerHTML = "<tr><th>Document</th><th></th></tr>" +
    (docs.map(f => `<tr><td>${f}</td>
      <td><button class="btn btn-danger btn-sm" onclick="rmDoc('${f}')">Remove</button></td></tr>`).join("")
    || `<tr><td class="empty" colspan="2">No documents</td></tr>`);
}
async function addDoc() {
  showPre("doc_out", await post("/api/admin/resources/documents",
    { filename: el("doc_name").value, content: el("doc_body").value }));
  loadDocs();
}
async function rmDoc(f) {
  showPre("doc_out", await del("/api/admin/resources/documents?filename=" + encodeURIComponent(f)));
  loadDocs();
}

/* ---------- Graph 1: sourcing ---------- */
async function startSourcing() {
  const r = await post("/api/admin/sourcing/runs",
    { preset: el("src_preset").value || "stage2_turbo_stock_power" });
  showPre("src_out", r); loadStats(); loadRuns();
}
async function sendSourcingEvent() {
  const type = el("ev2_type").value;
  const event = { event_type: type };
  if (el("ev2_order").value) event.order_id = +el("ev2_order").value;
  if (el("ev2_part").value) event.part_id = +el("ev2_part").value;
  if (type === "price_changed") event.final_price = +el("ev2_price").value;
  if (type === "substitute_offered") event.substitute = {
    substitute_part: el("ev2_sub").value || "ALT-PART",
    warranty_impact: el("ev2_warranty").value || null };
  const r = await post(`/api/admin/sourcing/runs/${el("ev2_run").value}/event`, { event });
  showPre("src_out", r); loadStats(); loadRuns(); loadHitl(); loadTickets();
}
async function autoStep(run) {
  const r = await post(`/api/admin/sourcing/runs/${run}/auto_event`, {});
  showPre("src_out", r); loadStats(); loadRuns(); loadHitl(); loadTickets();
}

/* ---------- Graph 2: warranty ---------- */
async function startWarranty() {
  const r = await post("/api/admin/warranty/runs", {
    vehicle_id: +el("war_vehicle").value,
    client_id: +el("war_client").value || null,
    description: el("war_desc").value });
  showPre("war_out", r); loadStats(); loadRuns();
}
async function sendInspection() {
  const s = el("war_ins").value; if (!s) return;
  const r = await post(
    `/api/admin/warranty/runs/${el("war_run").value.trim()}/inspection`,
    { status: s, notes: "workshop findings" });
  showPre("war_out", r); loadAll();
}
async function sendDecision() {
  const d = el("war_dec").value; if (!d) return;
  const r = await post(
    `/api/admin/warranty/runs/${el("war_run").value.trim()}/decision`,
    { decision: d });
  showPre("war_out", r); loadAll();
}

/* ---------- sidebar navigation ---------- */
function showPage(name) {
  document.querySelectorAll(".sidebar a").forEach(a =>
    a.classList.toggle("on", a.dataset.page === name));
  document.querySelectorAll("main [data-page]").forEach(s => {
    s.style.display = (s.dataset.page === name) ? "" : "none";
  });
}
document.querySelectorAll(".sidebar a").forEach(a =>
  a.addEventListener("click", e => { e.preventDefault(); showPage(a.dataset.page); }));
showPage("hits");
