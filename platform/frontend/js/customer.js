/* Customer console: four conversational agents + proactive updates. */

let agent = "tech";
let rescueRun   = localStorage.getItem("rescue_run")   || null;
let buildRun    = localStorage.getItem("build_run")    || null;
let warrantyRun = localStorage.getItem("warranty_run") || null;
let lastNews         = localStorage.getItem("rescue_news")   || "";
let lastBuildNews    = localStorage.getItem("build_news")    || "";
let lastWarrantyNews = localStorage.getItem("warranty_news") || "";

function showAgent(which) {
  agent = which;
  document.querySelectorAll(".agent-card").forEach(c =>
    c.classList.toggle("sel", c.dataset.agent === which));
  const titles = {
    tech:     "Chat with the technician",
    rescue:   "Fleet Rescue concierge",
    build:    "Performance Build concierge",
    warranty: "Warranty & Comebacks concierge"
  };
  const hints = {
    tech:     "Example: ”list available vehicles”",
    rescue:   "Example: ”Hi, I'm customer 2, vehicle 3 — engine failure on the desert road.”",
    build:    "Example: ”I'm customer 2, vehicle 3 — I want the stage2_turbo_stock_power build.”",
    warranty: "Example: ”I'm customer 1, vehicle 1 — the car lost power since last week's tune.”"
  };
  el("chat_title").textContent = titles[which];
  el("chat_hint").textContent  = hints[which];
  el("chat").innerHTML = "";
}

function addMsg(text, cls) {
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.textContent = text;
  el("chat").appendChild(d);
  el("chat").scrollTop = 1e9;
}

async function sendChat() {
  const msg = el("chat_in").value.trim();
  if (!msg) return;
  el("chat_in").value = "";
  addMsg(msg, "user");
  addMsg("…", "bot");
  let reply;
  try {
    if (agent === "rescue") {
      const r = await post("/api/agents/rescue_chat", { message: msg, run_id: rescueRun });
      if (r.run_id) { rescueRun = r.run_id; localStorage.setItem("rescue_run", r.run_id); }
      else        { rescueRun = null;      localStorage.removeItem("rescue_run"); }
      reply = typeof r.reply === "string" ? r.reply : JSON.stringify(r.reply, null, 2);
      lastNews = reply; localStorage.setItem("rescue_news", lastNews);

    } else if (agent === "build") {
      const r = await post("/api/agents/build_chat", { message: msg, run_id: buildRun });
      if (r.run_id) { buildRun = r.run_id; localStorage.setItem("build_run", r.run_id); }
      else        { buildRun = null;    localStorage.removeItem("build_run"); }
      reply = typeof r.reply === "string" ? r.reply : JSON.stringify(r.reply, null, 2);
      lastBuildNews = reply; localStorage.setItem("build_news", lastBuildNews);

    } else if (agent === "warranty") {
      const r = await post("/api/agents/warranty_chat", { message: msg, run_id: warrantyRun });
      if (r.run_id) { warrantyRun = r.run_id; localStorage.setItem("warranty_run", r.run_id); }
      else        { warrantyRun = null;    localStorage.removeItem("warranty_run"); }
      reply = typeof r.reply === "string" ? r.reply : JSON.stringify(r.reply, null, 2);
      lastWarrantyNews = reply; localStorage.setItem("warranty_news", lastWarrantyNews);

    } else {
      const r = await post("/api/agents/chat", { message: msg, agent: "tuning-technician" });
      reply = typeof r.reply === "string" ? r.reply : JSON.stringify(r.reply, null, 2);
    }
  } catch (e) {
    reply = "⚠️ Something went wrong on our side — please try again in a moment.";
  }
  el("chat").lastChild.remove();
  addMsg(reply, "bot");
}

/* Proactive updates for the three tracked runs. */
setInterval(async () => {
  try {
    if (rescueRun) {
      const n = await get(`/api/agents/rescue_status?run_id=${rescueRun}`);
      if (n.message && n.message !== lastNews) {
        lastNews = n.message; localStorage.setItem("rescue_news", lastNews);
        if (agent === "rescue") addMsg(n.message, "bot");
      }
      if (["completed", "cancelled", "rejected", "failed"].includes(n.status)) {
        rescueRun = null; localStorage.removeItem("rescue_run");
      }
    }
    if (buildRun) {
      const n = await get(`/api/agents/build_status?run_id=${buildRun}`);
      if (n.message && n.message !== lastBuildNews) {
        lastBuildNews = n.message; localStorage.setItem("build_news", lastBuildNews);
        if (agent === "build") addMsg(n.message, "bot");
      }
      if (["failed", "cancelled"].includes(n.status)) {
        buildRun = null; localStorage.removeItem("build_run");
      }
    }
    if (warrantyRun) {
      const n = await get(`/api/agents/warranty_status?run_id=${warrantyRun}`);
      if (n.message && n.message !== lastWarrantyNews) {
        lastWarrantyNews = n.message; localStorage.setItem("warranty_news", lastWarrantyNews);
        if (agent === "warranty") addMsg(n.message, "bot");
      }
      if (["completed", "cancelled", "failed"].includes(n.status)) {
        warrantyRun = null; localStorage.removeItem("warranty_run");
      }
    }
  } catch (e) { /* ignore */ }
}, 5000);