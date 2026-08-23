"""
Graph 3 — B2B Fleet Rescue & Authorization (simple core workflow).

REQUESTED
    ↓
VALIDATING
    ↓
SERVICE_ASSESSMENT
    ↓
AUTHORIZATION_CHECK
    ├── Approval required
    │       ↓
    │   WAITING_FOR_APPROVAL [HITL]
    │       ├── Approved ──────────┐
    │       └── Rejected → CANCELLED
    │                              ↓
    └── Auto-approved ─────────→ PROVIDER_SEARCH
                                    ↓
                         [Constrained ReAct over
                           real MCP tools only]
                                    ↓
                           Provider found?
                           ├── Yes
                           │    ↓
                           │ WAITING_FOR_PROVIDER
                           │    [External Wait]
                           │    ↓
                           │ RESCUE_IN_PROGRESS
                           │    ↓
                           │ COMPLETED
                           │
                           └── No / Provider rejected
                                    ↓
                              PROVIDER_SEARCH
                                   ↺ cycle

Side paths:
    VALIDATING → Invalid → CANCELLED

LLM additions:
    * RAG               → AUTHORIZATION_CHECK
                          Retrieves the client's contract and determines
                          whether the estimated service cost requires HITL.

    * Constrained ReAct → PROVIDER_SEARCH
                          Selects or interacts with providers using
                          whitelisted real MCP tools only.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from state_graph import runs
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.checkpoint.recovery import get_resume_info
from state_graph.hitl.hitl_manager import HitlPaused
from state_graph.tickets.ticket_manager import FailurePaused
from state_graph.graph3_fleet_rescue.nodes import (
    ExternalWaitPaused,
    FleetRescueNodes,
    FleetRescueState,
    MAX_PROVIDER_RETRIES,
)

_WAIT_VALUES = {"provider_response": {"accepted", "rejected"}}


class FleetRescueWorkflow:
    def __init__(
        self,
        *,
        nodes: FleetRescueNodes,
        checkpoints: CheckpointManager,
        hitl_manager,
        ticket_manager,
    ):
        self.nodes = nodes
        self.checkpoints = checkpoints
        self.hitl_manager = hitl_manager
        self.ticket_manager = ticket_manager
        self.graph = self._build_graph()

    def _wrap(self, name, fn):
        def node_fn(state: FleetRescueState) -> dict[str, Any]:
            if name in state.get("completed_nodes", []):
                return {}
            try:
                updates = fn(state) or {}
            except ExternalWaitPaused as wait:
                paused = {**state, "current_state": name, "awaiting": wait.wait_for}
                self.checkpoints.save(
                    run_id=state["run_id"],
                    node_name=name,
                    state=paused,
                    reason="external_wait",
                    metadata={"wait_for": wait.wait_for},
                )
                runs.touch_run(
                    state["run_id"], status="waiting_external", current_state=name
                )
                raise
            if "completed_nodes" not in updates:
                updates = {
                    **updates,
                    "completed_nodes": state.get("completed_nodes", []) + [name],
                }
            updates = {**updates, "current_state": updates.get("current_state", name)}
            self.checkpoints.save(
                run_id=state["run_id"],
                node_name=name,
                state={**state, **updates},
                reason="node_completed",
                metadata={},
            )
            return updates

        return node_fn

    # ---------- routers ----------
    @staticmethod
    def _route_validating(s):
        return "cancelled" if s.get("rescue_status") == "cancelled" else "ok"

    @staticmethod
    def _route_auth(s):
        return "needs_approval" if s.get("authorization_required") else "auto"

    @staticmethod
    def _route_approval(s):
        st = s.get("authorization_status")
        if st == "approved":
            return "approved"
        if st == "rejected":
            return "rejected"
        raise RuntimeError(f"approval router reached with status={st!r}")

    @staticmethod
    def _route_provider(s):
        if s.get("provider_response") == "accepted":
            return "accepted"
        return (
            "escalate"
            if int(s.get("retry_count", 0)) >= MAX_PROVIDER_RETRIES
            else "retry"
        )

    def _build_graph(self):
        g = StateGraph(FleetRescueState)
        n = self.nodes
        for name, fn in [
            ("validating", n.validating),
            ("service_assessment", n.service_assessment),
            ("authorization_check", n.authorization_check),
            ("waiting_for_approval", n.waiting_for_approval),
            ("provider_search", n.provider_search),
            ("waiting_for_provider", n.waiting_for_provider),
            ("escalate_provider_failure", n.escalate_provider_failure),
            ("rescue_in_progress", n.rescue_in_progress),
            ("cancelled", n.cancelled),
        ]:
            g.add_node(name, self._wrap(name, fn))

        g.add_edge(START, "validating")
        g.add_conditional_edges(
            "validating",
            self._route_validating,
            {"ok": "service_assessment", "cancelled": "cancelled"},
        )
        g.add_edge("service_assessment", "authorization_check")
        g.add_conditional_edges(
            "authorization_check",
            self._route_auth,
            {"needs_approval": "waiting_for_approval", "auto": "provider_search"},
        )
        g.add_conditional_edges(
            "waiting_for_approval",
            self._route_approval,
            {"approved": "provider_search", "rejected": "cancelled"},
        )
        g.add_edge("provider_search", "waiting_for_provider")
        g.add_conditional_edges(
            "waiting_for_provider",
            self._route_provider,
            {
                "accepted": "rescue_in_progress",
                "retry": "provider_search",  # cyclic
                "escalate": "escalate_provider_failure",
            },
        )
        g.add_edge("rescue_in_progress", END)
        g.add_edge("cancelled", END)
        g.add_edge("escalate_provider_failure", END)
        return g.compile()

    # ---------- execution / recovery ----------
    def execute(self, run_id, initial_state, *, state_override=None):
        if state_override is not None:
            state = state_override
        else:
            resume = get_resume_info(run_id, self.checkpoints)
            state = resume.state if resume.can_resume else dict(initial_state)
        state.setdefault("run_id", run_id)
        state.setdefault("completed_nodes", [])
        try:
            self.checkpoints.start_run(
                run_id,
                vehicle_id=state.get("vehicle_id"),
                client_id=state.get("customer_id"),
            )
            if not state.get("completed_nodes"):
                self.checkpoints.save(
                    run_id=run_id,
                    node_name="requested",
                    state=state,
                    reason="run_started",
                    metadata={},
                )
            runs.touch_run(
                run_id,
                status="running",
                current_state=state.get("current_state") or "REQUESTED",
            )
            final = self.graph.invoke(state)
        except HitlPaused as p:
            runs.touch_run(
                run_id, status="waiting_hitl", current_state="WAITING_FOR_APPROVAL"
            )
            return {
                "status": "paused_hitl",
                "request_id": p.request_id,
                "checkpoint_id": p.checkpoint_id,
            }
        except FailurePaused as p:
            runs.touch_run(
                run_id, status="ticketed", current_state=state.get("current_state")
            )
            return {
                "status": "failed_ticket",
                "ticket_id": p.ticket_id,
                "checkpoint_id": p.checkpoint_id,
            }
        except ExternalWaitPaused as p:
            return {
                "status": "waiting_external",
                "wait_for": p.wait_for,
                "node": p.node_name,
            }
        except Exception as e:
            runs.touch_run(
                run_id, status="failed", current_state=state.get("current_state")
            )
            return {"status": "failed", "error": str(e)}
        final_status = final.get("rescue_status", "completed")
        self.checkpoints.mark_run_finished(run_id, status=final_status)
        return {"status": final_status, "state": final}

    def resume_from_hitl(self, request_id: int):
        request = self.hitl_manager.approvals.get_request(request_id)
        data = self.hitl_manager.resume_data(request_id)
        state = dict(data["state"])
        state["authorization_status"] = "approved" if data["approved"] else "rejected"
        state["admin_decision"] = data["admin_decision"]
        return self.execute(request["run_id"], {}, state_override=state)

    def resume_from_ticket(self, ticket_id: int):
        ticket = self.ticket_manager.tickets.get(ticket_id)
        state = dict(self.ticket_manager.resume_data(ticket_id)["state"])
        return self.execute(ticket["run_id"], {}, state_override=state)

    def resume_from_external(self, run_id: str, *, provider_response: str):
        latest = self.checkpoints.get_latest(run_id)
        if latest is None:
            raise ValueError(f"no checkpoint for run {run_id}")
        if (
            latest.metadata.get("wait_for") or latest.state.get("awaiting")
        ) != "provider_response":
            raise ValueError(f"run {run_id} is not waiting for a provider response")
        if provider_response not in _WAIT_VALUES["provider_response"]:
            raise ValueError(f"invalid provider_response: {provider_response!r}")
        state = dict(latest.state)
        state["provider_response"] = provider_response
        return self.execute(run_id, {}, state_override=state)

    def get_status(self, run_id):
        latest = self.checkpoints.get_latest(run_id)
        run = runs.get_run(run_id)
        return {
            "run": dict(run) if run else None,
            "checkpoint_node": latest.node_name if latest else None,
            "reason": latest.reason if latest else None,
        }
