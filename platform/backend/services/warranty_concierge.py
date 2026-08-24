"""Warranty & Comebacks concierge — conversational facade over Graph 2.
The CUSTOMER opens the complaint, follows updates, and gives the final
decision from the chat; the workshop side (inspection result, senior
HITL, tickets) stays in the admin console."""
from __future__ import annotations

import json
import re
import time

from state_graph import runs as runs_db
from ..deps import get_stack
from . import customer_service, graph_service

_EXTRACT = """You are the intake assistant of a performance tuning shop.
From the user's message extract STRICT JSON only:
{{"customer_id": int|null, "vehicle_id": int|null, "complaint": str|null, "missing": [str]}}
- complaint: one-line description of the problem the client reports after a recent tune.
- missing: whichever of ["customer_id", "vehicle_id", "complaint"] are unknown.
User message: {message}"""


def _llm_json(stack, prompt: str):
    text = stack.llm.complete(prompt).strip()
    text = re.sub(r"^```(json)?", "", text)
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _latest(run_id: str):
    stack = get_stack()
    ck = stack.checkpoints.get_latest(run_id)
    run = runs_db.get_run(run_id)
    return (run["status"] if run else "unknown"), (ck.state if ck else {})


def _decision_in(text: str):
    t = text.lower()
    if any(k in t for k in ("escalate", "manager")):
        return "escalate"
    if any(k in t for k in ("reject", "decline")):
        return "reject"
    if any(k in t for k in ("accept", "approve", "agree", "ok", "yes")):
        return "accept"
    return None


def _compose(status: str, st: dict, error=None) -> str:
    g = st.get("status") or ""
    
    if status in ("paused_hitl", "waiting_hitl"):
        return "A senior technician is reviewing your case. I'll update you soon."
    
    if status in ("ticketed", "failed_ticket"):
        return "We're working on an issue. Will resume automatically."
    
    if status == "failed":
        return "Something went wrong. Please try again or call the shop."
    
    if status == "cancelled":
        return "Case closed. You can open a new one anytime."
    
    if status == "completed":
        return "All done! The workshop will contact you for next steps."
    
    if g == "waiting_client":
        resp = st.get("responsibility")
        offer = st.get("proposed_resolution")
        
        if offer:
            body = f"Management's offer: {offer}."
        elif resp == "company":
            body = "Good news — this is covered under warranty."
        elif resp in ("client", "unrelated"):
            body = "This isn't covered under warranty, but we can fix it at standard rates."
        else:
            body = "Our investigation is complete."
        
        return f"{body} Please reply: accept / reject / escalate."
    
    return "Your complaint is registered. The workshop is inspecting your car. I'll update you soon."


def _update_reply(status: str, st: dict) -> str:
    g = st.get("status") or ""
    if g == "waiting_inspection":
        return ("The workshop is still inspecting — nothing new yet 🙂 "
                "I'll message you the moment we know.")
    return _compose(status, st)


def news(run_id: str | None):
    if not run_id:
        return {"status": None, "message": None}
    status, st = _latest(run_id)
    if status == "unknown":
        return {"status": None, "message": None}
    return {"status": status, "message": _compose(status, st)}


def chat(message: str, run_id: str | None):
    stack = get_stack()
    info = None

    if run_id:
        cur_status, cur_state = _latest(run_id)
        if cur_status != "unknown":
            # While waiting on the client, a decision word closes the case.
            if cur_state.get("status") == "waiting_client":
                decision = _decision_in(message)
                if decision:
                    r = graph_service.external_event(
                        "warranty_dispute", run_id, {"decision": decision})
                    _, st = _latest(run_id)
                    return {"reply": _compose(r.get("status"), st, r.get("error")),
                            "run_id": run_id}
            info = _llm_json(stack, _EXTRACT.format(message=message))
            if info.get("missing"):
                return {"reply": _update_reply(cur_status, cur_state),
                        "run_id": run_id}

    if info is None:
        info = _llm_json(stack, _EXTRACT.format(message=message))
    if info.get("missing"):
        nice = {"customer_id": "your customer ID", "vehicle_id": "the vehicle ID",
                "complaint": "what's wrong with the car"}
        need = ", ".join(nice.get(m, m) for m in info["missing"])
        return {"reply": f"Sorry to hear that! To open the complaint I just need: {need}.",
                "run_id": None}

    ok, why, detail = customer_service.verify(int(info["customer_id"]),
                                              int(info["vehicle_id"]))
    if not ok:
        c, v = info["customer_id"], info["vehicle_id"]
        if why == "unknown_customer":
            reply = (f"I couldn't find customer {c} in our records — "
                     f"warranty service is for registered clients only.")
        elif why == "unknown_vehicle":
            reply = (f"I couldn't find vehicle {v} in our registry — "
                     f"please double-check the ID.")
        else:
            reply = (f"I couldn't verify vehicle {v} under customer {c} — our records "
                     f"show it belongs to customer {detail}.")
        return {"reply": reply, "run_id": None}

    new_run = f"war_{int(time.time() % 1_000_000)}"
    r = graph_service.start("warranty_dispute", new_run, {
        "run_id": new_run, "vehicle_id": int(info["vehicle_id"]),
        "client_id": int(info["customer_id"]),
        "complaint": {"description": info["complaint"]}})
    _, st = _latest(new_run)
    return {"reply": _compose(r.get("status"), st, r.get("error")),
            "run_id": new_run}