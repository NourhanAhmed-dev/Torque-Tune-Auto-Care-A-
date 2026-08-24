"""Gives Graph2Warranty the same contract the platform speaks.
Maps the graph's soft/hard pauses onto platform run statuses."""
from __future__ import annotations

from state_graph import runs as runs_db
from state_graph.hitl.hitl_manager import HitlPaused
from state_graph.tickets.ticket_manager import FailurePaused

_STATUS_MAP = {
    "running": "running",
    "waiting_inspection": "waiting_external",
    "waiting_client": "waiting_external",
    "waiting_hitl": "waiting_hitl",
    "ticket_open": "ticketed",
    "completed": "completed",
}


class WarrantyAdapter:
    def __init__(self, graph, checkpoints, hitl, tickets):
        self.graph = graph
        self.checkpoints = checkpoints
        self.hitl = hitl
        self.tickets = tickets

    def _wrap(self, run_id, fn):
        runs_db.ensure_run(run_id, graph_type="warranty_dispute")
        try:
            state = fn()
        except HitlPaused as p:
            runs_db.touch_run(run_id, status="waiting_hitl",
                              current_state="WAITING_FOR_SENIOR_REVIEW")
            return {"status": "paused_hitl", "request_id": p.request_id,
                    "checkpoint_id": p.checkpoint_id}
        except FailurePaused as p:
            runs_db.touch_run(run_id, status="ticketed", current_state="TICKET_OPEN")
            return {"status": "failed_ticket", "ticket_id": p.ticket_id,
                    "checkpoint_id": getattr(p, "checkpoint_id", None)}
        except Exception as e:
            runs_db.touch_run(run_id, status="failed", current_state="FAILED")
            return {"status": "failed", "error": str(e)}
        # The graph returns the full state dict on success — derive status from it.
        g_status = (state or {}).get("status", "running")
        mapped = _STATUS_MAP.get(g_status, "running")
        runs_db.touch_run(run_id, status=mapped, current_state=g_status.upper())
        return {"status": mapped, "state": state}

    # ---- platform contract ----
    def execute(self, run_id, initial_state, **_):
        return self._wrap(run_id, lambda: self.graph.start(
            run_id=run_id,
            vehicle_id=int(initial_state["vehicle_id"]),
            complaint=initial_state.get("complaint") or {},
            client_id=initial_state.get("client_id")))

    def resume_from_external(self, run_id, inspection=None, decision=None, **_):
        if inspection is not None:
            return self._wrap(run_id, lambda: self.graph.submit_inspection_result(
                run_id=run_id, result=inspection))
        if decision is not None:
            return self._wrap(run_id, lambda: self.graph.submit_client_decision(
                run_id=run_id, decision=decision))
        raise ValueError("warranty external event needs 'inspection' or 'decision'")

    def resume_from_hitl(self, request_id):
        run_id = self.hitl.approvals.get_request(request_id)["run_id"]
        return self._wrap(run_id,
                      lambda: self.graph.resume_after_hitl_approval(request_id))

    def resume_from_ticket(self, ticket_id):
        run_id = self.tickets.tickets.get(ticket_id)["run_id"]
        return self._wrap(run_id,
                          lambda: self.graph.resume_after_ticket_resolution(ticket_id))

    def get_status(self, run_id):
        run = runs_db.get_run(run_id)
        ck = self.checkpoints.get_latest(run_id)
        return {"run": dict(run) if run else None,
                "checkpoint_node": ck.node_name if ck else None,
                "state": ck.state if ck else {}}