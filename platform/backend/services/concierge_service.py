"""Fleet Rescue concierge — conversational facade over Graph 3.
The customer chats in plain language; the LLM extracts the request,
the graph works silently behind the scenes, and the customer only
hears human-friendly outcomes — never the internals."""
import json
import re
import time

from state_graph import runs as runs_db
from ..deps import get_stack
from . import customer_service

_EXTRACT = """You are the intake assistant of a B2B fleet-rescue service.
From the user's message extract STRICT JSON only:
{{"customer_id": int|null, "vehicle_id": int|null, "problem": str|null, "missing": [str]}}
- customer_id / vehicle_id only when stated or clearly implied.
- problem: one-line breakdown description.
- missing: whichever of ["customer_id", "vehicle_id", "problem"] are unknown.
User message: {message}"""

_TERMINAL = ("completed", "cancelled", "rejected", "failed", "unknown")


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


def _compose(status: str, st: dict, error: str | None = None) -> str:
    if status == "waiting_external":
        prov = st.get("selected_provider") or "a provider"
        return f"Request sent to {prov}. They'll confirm shortly."
    
    if status in ("waiting_hitl", "paused_hitl"):
        return "Waiting for fleet manager approval. I'll update you soon."
    
    if status in ("ticketed", "failed_ticket"):
        return "Technical issue detected. Support notified. Will resume automatically."
    
    if status == "completed":
        return "Rescue complete! Your vehicle is back on the road. ✅"
    
    if status in ("cancelled", "rejected"):
        reason = st.get('cancel_reason') or 'declined by manager'
        return f"Request {reason}."
    
    if status == "failed":
        if error and ("registered" in error or "Unknown" in error or "FOREIGN KEY" in error):
            return "Couldn't verify vehicle. Please check customer and vehicle IDs."
        return "Something failed. Support notified."
    
    if status == "running":
        return "Working on your request..."
    
    return "I'll update you as soon as there's news."

def _update_message(status: str, st: dict) -> str:
    if status == "waiting_external":
        rej = st.get("rejected_providers") or []
        if rej:
            return f"{rej[-1]} couldn't make it. Contacting another provider..."
        return f"Waiting on {st.get('selected_provider') or 'the provider'}'s confirmation."
    
    if status in ("waiting_hitl", "paused_hitl"):
        return "Still waiting for fleet manager's decision."
    
    return _compose(status, st)




def news(run_id: str | None):
    """One customer-friendly line about the current situation (for polling)."""
    if not run_id:
        return {"status": None, "message": None}
    status, st = _latest(run_id)
    if status == "unknown":
        return {"status": None, "message": None}
    if status in _TERMINAL:
        return {"status": status, "message": _compose(status, st)}
    return {"status": status, "message": _update_message(status, st)}


def chat(message: str, run_id: str | None):
    stack = get_stack()
    info = None

    # 1) Active (non-terminal) run -> the user is asking for news.
    if run_id:
        status, st = _latest(run_id)
        if status not in _TERMINAL:
            return {"reply": _update_message(status, st), "run_id": run_id}
        # Terminal run: report the final outcome, unless the message is a
        # complete brand-new request.
        info = _llm_json(stack, _EXTRACT.format(message=message))
        if info.get("missing"):
            return {"reply": _compose(status, st), "run_id": run_id}

    # 2) Extract a new request (if we didn't already above).
    if info is None:
        info = _llm_json(stack, _EXTRACT.format(message=message))
    if info.get("missing"):
        nice = {"customer_id": "your customer ID", "vehicle_id": "the vehicle ID",
                "problem": "what happened to the vehicle"}
        need = ", ".join(nice.get(m, m) for m in info["missing"])
        return {"reply": f"Happy to help! To open the rescue request I just need: {need}.",
                "run_id": None}

    # 3) API-layer input validation (fail fast, friendly).
    ok, why, detail = customer_service.verify(int(info["customer_id"]),
                                              int(info["vehicle_id"]))
    if not ok:
        c, v = info["customer_id"], info["vehicle_id"]
        if why == "unknown_customer":
            reply = (f"I'm sorry, I couldn't find customer {c} in our records — "
                     f"this service is available for contracted fleets only. "
                     f"If you believe this is a mistake, please contact your "
                     f"account manager.")
        elif why == "unknown_vehicle":
            reply = (f"I couldn't find vehicle {v} in our registry — "
                     f"please double-check the ID.")
        else:
            reply = (f"I couldn't verify vehicle {v} under customer {c} — our records "
                     f"show it's registered to customer {detail}. "
                     f"Please double-check the IDs and try again.")
        return {"reply": reply, "run_id": None}

    # 4) Open the run and let the graph do the work behind the scenes.
    new_run = f"chat_{int(time.time() % 1_000_000)}"
    r = stack.rescue_wf.execute(new_run, {
        "run_id": new_run,
        "customer_id": int(info["customer_id"]),
        "vehicle_id": int(info["vehicle_id"]),
        "rescue_request": info["problem"],
    })
    _, st = _latest(new_run)
    return {"reply": _compose(r.get("status"), st, r.get("error")), "run_id": new_run}