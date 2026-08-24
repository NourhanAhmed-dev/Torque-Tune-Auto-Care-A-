"""Performance Build concierge — conversational facade over Graph 1.
No teammate code is modified: we only wrap the graph via graph_service."""
from __future__ import annotations

import json
import re
import time

from state_graph import runs as runs_db
from ..deps import get_stack
from . import customer_service, graph_service

_EXTRACT = """You are the intake assistant of a performance tuning shop.
From the user's message extract STRICT JSON only:
{{"customer_id": int|null, "vehicle_id": int|null, "preset": str|null, "missing": [str]}}
Available build presets: stage1_ecu_only, stage2_turbo_stock_power, stage2_turbo_high_power,
stage2_turbo_boost_controller, stage2_turbo_full_send, stage3_race_build,
intercooler_upgrade_only, exhaust_upgrade_only.
- preset: map phrases like "turbo kit" / "stage 2" / "race build" / "intercooler only"
  to the closest preset key; null if absent.
- missing: whichever of ["customer_id", "vehicle_id", "preset"] are unknown.
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


def _compose(status: str, st: dict, error=None) -> str:
    if status in ("paused_hitl", "waiting_hitl"):
        return "Waiting for manager approval. I'll update you soon."
    
    if status in ("ticketed", "failed_ticket"):
        return "We're working on an issue. Will resume automatically."
    
    if status == "failed":
        return "Something went wrong. Please try again later."
    
    if status == "cancelled":
        return "Request cancelled. You can start a new one anytime."
    
    delivered = st.get("delivered_part_ids") or []
    cancelled = st.get("cancelled_part_ids") or []
    
    if status == "completed":
        return "Your build is ready! We'll contact you for scheduling."
    
    if not delivered and not cancelled:
        return "Your build is being arranged. I'll keep you updated."
    
    return "Some parts arrived. More updates coming soon."

def _update_reply(status: str, st: dict) -> str:
    if status == "waiting_external" and not (st.get("delivered_part_ids") or []):
        return ("Nothing new yet — I'll message you the moment "
                "something changes ")
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

    # Tracked run + short/news-seeking message -> latest update only.
    # A COMPLETE new request always opens a brand-new run.
    if run_id:
        cur_status, cur_state = _latest(run_id)
        if cur_status != "unknown":
            info = _llm_json(stack, _EXTRACT.format(message=message))
            if info.get("missing"):
                return {"reply": _update_reply(cur_status, cur_state),
                        "run_id": run_id}

    if info is None:
        info = _llm_json(stack, _EXTRACT.format(message=message))
    if info.get("missing"):
        nice = {"customer_id": "your customer ID", "vehicle_id": "the vehicle ID",
                "preset": "which build preset you want"}
        need = ", ".join(nice.get(m, m) for m in info["missing"])
        return {"reply": f"Happy to set up your build! I just need: {need}.",
                "run_id": None}

    ok, why, detail = customer_service.verify(int(info["customer_id"]),
                                              int(info["vehicle_id"]))
    if not ok:
        c, v = info["customer_id"], info["vehicle_id"]
        if why == "unknown_customer":
            reply = (f"I couldn't find customer {c} in our records — builds are "
                     f"for registered clients only.")
        elif why == "unknown_vehicle":
            reply = (f"I couldn't find vehicle {v} in our registry — "
                     f"please double-check the ID.")
        else:
            reply = (f"I couldn't verify vehicle {v} under customer {c} — our records "
                     f"show it belongs to customer {detail}.")
        return {"reply": reply, "run_id": None}

    preset = info["preset"] or "stage2_turbo_stock_power"
    new_run = f"build_{int(time.time() % 1_000_000)}"
    r = graph_service.start("graph1_multi_supplier", new_run,
                            {"run_id": new_run, "preset": preset})
    _, st = _latest(new_run)
    return {"reply": _compose(r.get("status"), st, r.get("error")),
            "run_id": new_run}