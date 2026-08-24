"""Customer-friendly story of a run, reconstructed from its checkpoints.
Used by the ADMIN console only (operators view); customers see the
concierge chat instead."""
from state_graph import runs as runs_db
from ..deps import get_stack

STEPS = {
    
    # Graph 1 — multi-supplier sourcing
    "build_configuration":       ("🧩", "Reading build configuration"),
    "place_orders":              ("📦", "Placing supplier orders"),
    "apply_event_effects":       ("📡", "Applying supplier event"),
    "price_check":               ("💰", "Price deviation check"),
    "substitute_check":          ("🔁", "Substitute warranty check"),
    "apply_hitl_decision":       ("🧑‍⚖️", "Applying manager decision"),
    "task_decomposition":        ("🛠️", "Planning installation sequence (LLM)"),
    # Graph 2 - 
    "intake_complaint":         ("📨", "Complaint received"),
    "link_to_original_log":     ("📚", "Pulling original tuning history (RAG)"),
    "schedule_inspection":      ("🔧", "Inspection scheduled"),
    "evaluate_inspection":      ("🔍", "Evaluating inspection"),
    "determine_responsibility": ("🤖", "Responsibility analysis (constrained agent)"),
    "senior_review_hitl":       ("🧑‍️", "Senior review"),
    "await_client_decision":    ("📞", "Waiting on client decision"),
    "complete":                 ("✅", "Investigation complete"),
    # Graph 3 — fleet rescue
    "validating":                ("🔎", "Checking your account & fleet"),
    "service_assessment":        ("🤖", "AI assessment of the problem"),
    "authorization_check":       ("📚", "Reading your contract (RAG)"),
    "waiting_for_approval":      ("🙋", "Approval from your fleet manager"),
    "provider_search":           ("🧭", "Finding an available provider"),
    "waiting_for_provider":      ("📡", "Provider response"),
    "escalate_provider_failure": ("🚫", "No provider available right now"),
    "rescue_in_progress":        ("🔧", "Rescue in progress"),
    # Terminal
    "completed":                 ("✅", "Done"),
    "cancelled":                 ("⛔", "Request cancelled"),
}


def _detail(node, s):
    # ---- Graph 3 ----
    if node == "validating":
        if s.get("rescue_status") == "cancelled":
            return s.get("cancel_reason", "not registered"), "error"
        return "Account and vehicle are registered correctly.", "ok"
    if node == "service_assessment":
        return (f"Gemini estimate: {s.get('service_type')} — "
                f"~${s.get('estimated_cost')}"), "ok"
    if node == "authorization_check":
        need = ("manager approval required" if s.get("authorization_required")
                else "auto-approved by your contract")
        return (f"Contract says: auto-approval up to "
                f"${s.get('authorization_threshold')} → {need}."), "ok"
    if node == "waiting_for_approval":
        st = s.get("authorization_status")
        if st == "approved":  return "Your manager approved the cost.", "ok"
        if st == "rejected":  return "Your manager declined the rescue.", "error"
        return "Waiting for your manager's decision…", "wait"
    if node == "provider_search":
        if s.get("selected_provider"):
            return (f"Agent dispatched {s['selected_provider']} "
                    f"(dispatch #{s.get('dispatch_id')})."), "ok"
        return "Searching providers…", "wait"
    if node == "waiting_for_provider":
        pr = s.get("provider_response")
        if pr == "accepted":
            return f"{s.get('selected_provider')} accepted — truck on the way 🚛", "ok"
        if pr == "rejected":
            last = (s.get("rejected_providers") or ["the provider"])[-1]
            return (f"{last} declined — looking for another one "
                    f"(attempt {s.get('retry_count', 1)})."), "warn"
        return "Request sent — waiting for the provider's answer…", "wait"
    if node == "escalate_provider_failure":
        return ("Nobody is available right now — a support ticket was opened; "
                "we resume automatically once it's fixed."), "error"
    if node == "rescue_in_progress":
        return "A technician is handling your vehicle.", "ok"
    # ---- Graph 1 ----
    if node == "build_configuration":
        return f"{len(s.get('parts_required') or [])} part(s) required for this build.", "ok"
    if node == "place_orders":
        orders = s.get("orders") or {}
        summary = ", ".join(f"#{o['order_id']}→{o['supplier']}" for o in orders.values())
        return f"Orders placed: {summary or 'none'}.", "ok"
    if node == "apply_event_effects":
        ev = s.get("last_event") or {}
        return f"Event applied: {ev.get('event_type', '?')}.", "ok"
    if node == "price_check":
        return "Final price recorded; deviation within threshold — no approval needed.", "ok"
    if node == "substitute_check":
        return "Substitute evaluated.", "ok"
    if node == "apply_hitl_decision":
        return "Manager decision applied to the orders.", "ok"
    if node == "task_decomposition":
        seq = [x["part_id"] for x in (s.get("installation_sequence") or [])]
        return f"Installation sequence: {seq or '[]'}.", "ok"
    if node == "completed":
        return "All done ✅", "ok"
    if node == "cancelled":
        return s.get("cancel_reason") or "Authorization rejected.", "error"
    return "", "ok"


def _banner(status, s):
    if status == "waiting_external":
        return "📡 Your request was sent to a provider — waiting for their yes/no."
    if status in ("waiting_hitl", "paused_hitl"):
        return "🙋 Waiting for a manager decision — I'll update you once decided."
    if status == "ticketed":
        return ("🛠️ Technical issue — a support ticket is open; the run resumes "
                "automatically once resolved.")
    if status == "running":
        return "🔄 Working on your request…"
    if status == "completed":
        return "✅ Completed."
    if status in ("cancelled", "rejected"):
        return f"⛔ {s.get('cancel_reason') or 'The request was cancelled.'}"
    if status == "failed":
        return "⚠️ Something failed — support has been notified."
    return "…"


def timeline(run_id: str):
    hist = get_stack().checkpoints.history(run_id)
    steps = []
    for ck in hist:
        s = ck.state or {}
        if ck.reason == "run_started":
            steps.append({"icon": "📨", "title": "Run started",
                          "detail": s.get("rescue_request", ""), "kind": "ok"})
            continue
        if ck.reason == "node_failure":
            steps.append({"icon": "🎫",
                          "title": "Something went wrong — support ticket opened",
                          "detail": s.get("error_message") or "unexpected failure",
                          "kind": "error"})
            continue
        if ck.node_name not in STEPS:
            continue
        icon, title = STEPS[ck.node_name]
        detail, kind = _detail(ck.node_name, s)
        if ck.reason == "hitl_pause":
            detail, kind = "Waiting for the manager's decision…", "wait"
        if ck.reason == "external_wait":
            detail, kind = "Waiting for the external answer…", "wait"
        steps.append({"icon": icon, "title": title, "detail": detail, "kind": kind})
    run = runs_db.get_run(run_id)
    status = run["status"] if run else "unknown"
    latest = hist[-1].state if hist else {}
    return {"status": status, "banner": _banner(status, latest), "steps": steps}