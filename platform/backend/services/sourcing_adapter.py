"""Gives SourcingInstallGraph the same 4-method contract the platform speaks."""
from __future__ import annotations
import json
import re
from state_graph import runs as runs_db
from state_graph.hitl.hitl_manager import HitlPaused
from state_graph.tickets.ticket_manager import FailurePaused


class SourcingAdapter:
    def __init__(self, graph, checkpoints, hitl, tickets):
        self.graph = graph
        self.checkpoints = checkpoints
        self.hitl = hitl
        self.tickets = tickets

    def _wrap(self, run_id, fn):
        runs_db.ensure_run(run_id, graph_type="graph1_multi_supplier")
        try:
            state = fn()
        except HitlPaused as p:
            runs_db.touch_run(run_id, status="waiting_hitl",
                              current_state="WAITING_FOR_APPROVAL")
            return {"status": "paused_hitl", "request_id": p.request_id,
                    "checkpoint_id": p.checkpoint_id}
        except FailurePaused as p:
            runs_db.touch_run(run_id, status="ticketed", current_state="FAILED")
            return {"status": "failed_ticket", "ticket_id": p.ticket_id,
                    "checkpoint_id": getattr(p, "checkpoint_id", None)}
        except Exception as e:
            runs_db.touch_run(run_id, status="failed", current_state="FAILED")
            return {"status": "failed", "error": str(e)}
        # Success: real lifecycle — waiting for suppliers until every part
        # is resolved (delivered or cancelled); only then completed.
        required = {p["part_id"] for p in state.get("parts_required") or []}
        resolved = (set(state.get("delivered_part_ids") or []) |
                    set(state.get("cancelled_part_ids") or []))
        done = bool(required) and required <= resolved
        runs_db.touch_run(run_id,
                          status="completed" if done else "waiting_external",
                          current_state="DONE" if done else "WAITING_FOR_SUPPLIERS")
        return {"status": "completed" if done else "waiting_external",
                "state": state}

    def get_status(self, run_id):
        run = runs_db.get_run(run_id)
        ck = self.checkpoints.get_latest(run_id)
        return {"run": dict(run) if run else None,
                "checkpoint_node": ck.node_name if ck else None,
                "state": ck.state if ck else {}}

    def execute(self, run_id, initial_state, **_):
        preset = initial_state.get("preset", "stage2_turbo_stock_power")
        return self._wrap(run_id, lambda: self.graph.start_from_preset(
            run_id=run_id, state=initial_state, preset=preset))

    def resume_from_external(self, run_id, event=None, **_):
        return self._wrap(run_id, lambda: self.graph.on_supplier_event(
            run_id=run_id, event=event, state={}))

    def resume_from_hitl(self, request_id):
        req = self.hitl.approvals.get_request(request_id)
        run_id = req["run_id"]
        ck = self.checkpoints.get_latest(run_id)
        saved_state = ck.state if ck else {}
        try:
            resume = self.hitl.resume_data(request_id) or {}
        except Exception:
            resume = {}
        approved = bool((resume or {}).get("approved"))

        def _find_action(v):
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    return None
            if isinstance(v, dict):
                if v.get("type") in ("price_deviation", "substitute_offered"):
                    return v
                for inner in v.values():
                    found = _find_action(inner)
                    if found:
                        return found
            return None

        action = None
        for src in (req, resume):
            if isinstance(src, dict):
                for key in ("payload", "action"):
                    action = _find_action(src.get(key))
                    if action:
                        break
            if action:
                break

        # Fallback: rebuild the action from the human-readable reason.
        if not action:
            reason = req.get("reason") or ""
            m = re.search(r"part (\d+) on order (\d+)", reason)
            if m:
                action = {"type": "substitute_offered",
                          "part_id": int(m.group(1)),
                          "order_id": int(m.group(2)),
                          "substitute_part": None,
                          "warranty_impact":
                              reason.split("warranty:", 1)[-1].strip() or None}
            else:
                m = re.search(r"Order (\d+)", reason)
                m2 = re.search(r"final price ([\d.]+).*?quote ([\d.]+)", reason)
                if m:
                    oid = int(m.group(1))
                    orders = (resume.get("state") or {}).get("orders") or {}
                    order = orders.get(oid) or orders.get(str(oid)) or {}
                    action = {"type": "price_deviation", "order_id": oid,
                              "quoted_price": order.get("quoted_price") or
                                  (float(m2.group(2)) if m2 else None),
                              "final_price": order.get("final_price") or
                                  (float(m2.group(1)) if m2 else None)}

        decision = {"action": action or {}, "approved": approved}
        res = self._wrap(run_id, lambda: self.graph.on_hitl_decision(
                    run_id=run_id, decision=decision, state=saved_state))
        # Admin answered -> close the loop: ship (approved) or cancel
        # (rejected) whatever is left, so the run ends without extra clicks.
        if res.get("status") == "waiting_external":
            st = res.get("state") or {}
            left = [p["part_id"] for p in (st.get("parts_required") or [])
                    if p["part_id"] not in (st.get("delivered_part_ids") or [])
                    and p["part_id"] not in (st.get("cancelled_part_ids") or [])]
            settle = "delivery_confirmed" if approved else "cancelled"
            last = res
            for pid in left:
                last = self._wrap(run_id, lambda pid=pid: self.graph.on_supplier_event(
                    run_id=run_id, event={"event_type": settle, "part_id": pid},
                    state={}))
            return last
        return res

    def resume_from_ticket(self, ticket_id):
        t = self.tickets.tickets.get(ticket_id)
        run_id = t["run_id"]
        ck = self.checkpoints.get_latest(run_id)
        st = ck.state if ck else {}

        def _orders():
            grouped = {}
            for part in st.get("parts_required") or []:
                grouped.setdefault(part["preferred_suppliers"][0], []).append(part["part_id"])
            return [{"supplier": s, "part_ids": p} for s, p in grouped.items()]

        return self._wrap(run_id, lambda: self.graph.start(
            run_id=run_id, state={}, orders_to_place=_orders()))

  