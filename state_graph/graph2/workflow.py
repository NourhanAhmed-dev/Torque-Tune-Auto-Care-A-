"""
Graph 2: Post-Tune Comeback / Warranty Dispute Investigation.

Scenario
--------
A client comes back ~2 weeks after a tuning/remap and reports a problem
(loss of power, strange noise, engine light...). The question the graph
exists to answer is: is this caused by our tuning, or something else?

Flow
----

    START
      |
    INTAKE_COMPLAINT
      |
    LINK_TO_ORIGINAL_LOG        <-- AgenticRAG pulls tuning_logs +
      |                             episodic_memories for this vehicle_id
    SCHEDULE_INSPECTION
      |
    (WAIT for a real, physical inspection -- this cannot be answered
     by the agent talking; someone has to look at the car)
      |
    EVALUATE_INSPECTION
      |
      +--- inspection_result == "inconclusive"
      |        -> raise InconclusiveInspection
      |        -> caught by FailureNode -> TicketManager.capture_failure()
      |        -> TICKET (paused; a human resolves it, e.g. goodwill comp.)
      |
      +--- inspection_result usable -> DETERMINE_RESPONSIBILITY
                |
                |   DETERMINE_RESPONSIBILITY is internally a
                |   *Constrained ReAct* loop (bounded steps, fixed
                |   action set, schema-validated JSON actions) -- see
                |   graph2_nodes.Graph2Nodes for the implementation.
                |
                +--- ambiguous evidence -> SENIOR_REVIEW_HITL (HitlNode)
                |         |
                |         v
                +--- clear responsibility --> AWAIT_CLIENT_DECISION
                                                    |
                                                    v
                                                COMPLETE

Why LangGraph + a custom checkpoint layer instead of LangGraph's own
checkpointer:
    This run spans days/sessions, waits on physical-world events and on
    human decisions, and must resume the *same* run afterwards. The
    compiled graph below is invoked from START every time. Nodes that
    already ran are no-ops (via `should_skip`), and nodes that are
    waiting on something external simply route to END until that input
    shows up in the persisted state.

Module layout
-------------
This file owns graph *assembly* (StateGraph, nodes wiring, edges) and
the public API (start / submit_* / resume_after_* / get_state). The
node/routing/ReAct *logic* itself lives in `graph2_nodes.py` as
`Graph2Nodes` -- this class just instantiates it and points
`g.add_node(...)` at its methods. Nothing about behavior, checkpointing,
or control flow changed by splitting the file this way.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.failure_node import FailureNode
from state_graph.hitl_node import HitlNode
from state_graph.tickets.ticket_manager import TicketManager, FailurePaused
from state_graph.tickets.ticket_service import TicketService
from state_graph.hitl.hitl_manager import HitlManager, HitlPaused
from state_graph.hitl.approval_service import ApprovalService
from rag.agentic_rag import AgenticRAG

from nodes import (
    INTAKE_COMPLAINT,
    LINK_TO_ORIGINAL_LOG,
    SCHEDULE_INSPECTION,
    EVALUATE_INSPECTION,
    DETERMINE_RESPONSIBILITY,
    SENIOR_REVIEW_HITL,
    AWAIT_CLIENT_DECISION,
    TICKET,
    COMPLETE,
    Graph2State,
    Graph2Nodes,
    InconclusiveInspection,
    HitlRejected,
)

__all__ = [
    "Graph2Warranty",
    "Graph2State",
    "InconclusiveInspection",
    "HitlRejected",
]


class Graph2Warranty:
    """Post-Tune Comeback / Warranty Dispute Investigation, on LangGraph."""

    def __init__(
        self,
        checkpoint_manager: CheckpointManager | None = None,
        ticket_manager: TicketManager | None = None,
        hitl_manager: HitlManager | None = None,
        rag: AgenticRAG | None = None,
    ) -> None:
        self.checkpoints = checkpoint_manager or CheckpointManager(graph_type="warranty_dispute")

        self.ticket_manager = ticket_manager or TicketManager(
            checkpoints=self.checkpoints, tickets=TicketService()
        )
        self.hitl_manager = hitl_manager or HitlManager(
            checkpoints=self.checkpoints, approvals=ApprovalService()
        )

        self.failure_node = FailureNode(self.ticket_manager)
        self.hitl_node = HitlNode(self.hitl_manager)
        self.rag = rag or AgenticRAG()

        # All node/routing/ReAct logic lives here; the graph below just
        # wires StateGraph nodes/edges onto its methods.
        self.nodes = Graph2Nodes(
            checkpoints=self.checkpoints,
            ticket_manager=self.ticket_manager,
            hitl_manager=self.hitl_manager,
            failure_node=self.failure_node,
            hitl_node=self.hitl_node,
            rag=self.rag,
        )

        self._graph = self._build()

    # ---- graph assembly ---------------------------------------------

    def _build(self):
        g = StateGraph(Graph2State)

        g.add_node(INTAKE_COMPLAINT, self.nodes._n_intake_complaint)
        g.add_node(LINK_TO_ORIGINAL_LOG, self.nodes._n_link_to_original_log)
        g.add_node(SCHEDULE_INSPECTION, self.nodes._n_schedule_inspection)
        g.add_node(EVALUATE_INSPECTION, self.nodes._n_evaluate_inspection)
        g.add_node(DETERMINE_RESPONSIBILITY, self.nodes._n_determine_responsibility)
        g.add_node(SENIOR_REVIEW_HITL, self.nodes._n_senior_review_hitl)
        g.add_node(AWAIT_CLIENT_DECISION, self.nodes._n_await_client_decision)
        g.add_node(COMPLETE, self.nodes._n_complete)

        g.set_entry_point(INTAKE_COMPLAINT)

        g.add_edge(INTAKE_COMPLAINT, LINK_TO_ORIGINAL_LOG)
        g.add_edge(LINK_TO_ORIGINAL_LOG, SCHEDULE_INSPECTION)

        g.add_conditional_edges(
            SCHEDULE_INSPECTION,
            self.nodes._route_after_schedule,
            {END: END, EVALUATE_INSPECTION: EVALUATE_INSPECTION},
        )

        # On a first pass, EVALUATE_INSPECTION either returns normally
        # (usable result) or raises FailurePaused before returning at
        # all (inconclusive -> ticket), so this conditional edge is
        # only ever evaluated in two cases: the normal path, or a
        # resumed invoke where should_skip() let the node no-op with
        # inspection_result.status == "resolved_via_ticket" already set
        # by resume_after_ticket_resolution().
        g.add_conditional_edges(
            EVALUATE_INSPECTION,
            self.nodes._route_after_evaluate_inspection,
            {DETERMINE_RESPONSIBILITY: DETERMINE_RESPONSIBILITY, AWAIT_CLIENT_DECISION: AWAIT_CLIENT_DECISION},
        )

        g.add_conditional_edges(
            DETERMINE_RESPONSIBILITY,
            self.nodes._route_after_responsibility,
            {SENIOR_REVIEW_HITL: SENIOR_REVIEW_HITL, AWAIT_CLIENT_DECISION: AWAIT_CLIENT_DECISION},
        )

        # SENIOR_REVIEW_HITL: on a first pass it always raises HitlPaused
        # before returning (see Graph2Nodes._n_senior_review_hitl), so
        # this edge is only ever reached on a resumed invoke, where the
        # decision has already been merged into the state.
        g.add_edge(SENIOR_REVIEW_HITL, AWAIT_CLIENT_DECISION)

        g.add_conditional_edges(
            AWAIT_CLIENT_DECISION,
            self.nodes._route_after_client,
            {END: END, COMPLETE: COMPLETE},
        )

        g.add_edge(COMPLETE, END)

        return g.compile()

    # ---- public API ---------------------------------------------------
    #
    # Every entrypoint below can raise:
    #   - HitlPaused    (from state_graph.hitl.hitl_manager) when the
    #     graph stopped at SENIOR_REVIEW_HITL. Catch it, keep
    #     .request_id, and resume later with resume_after_hitl_approval().
    #   - FailurePaused (from state_graph.tickets.ticket_manager) when
    #     EVALUATE_INSPECTION found the result inconclusive and opened a
    #     ticket. Catch it, keep .ticket_id, and resume later with
    #     resume_after_ticket_resolution().
    # Neither is a bug -- both are the graph correctly stopping to wait
    # on a human. Only nodes with no such infrastructure behind them
    # (SCHEDULE_INSPECTION, AWAIT_CLIENT_DECISION) pause "softly" by
    # just returning normally with status="waiting_*" and letting the
    # conditional edge route to END.

    def start(self, run_id: str, vehicle_id: int, complaint: dict[str, Any], client_id: int | None = None) -> Graph2State:
        """Create a new run and drive it as far as it can go before
        hitting the first wait (the physical inspection)."""
        self.checkpoints.start_run(run_id, vehicle_id=vehicle_id, client_id=client_id)

        initial_state: Graph2State = {
            "run_id": run_id,
            "vehicle_id": vehicle_id,
            "client_id": client_id,
            "complaint": complaint,
            "completed_nodes": [],
            "status": "running",
        }
        return self._invoke(initial_state)

    def submit_inspection_result(self, run_id: str, result: dict[str, Any]) -> Graph2State:
        """result = {"status": "tuning_fault" | "unrelated" | "inconclusive", "notes": str}

        Called once the physical inspection actually happened. May raise
        FailurePaused if `result["status"] == "inconclusive"`.
        """
        state = self._load_state(run_id)
        state["inspection_result"] = result
        return self._invoke(state)

    def submit_client_decision(self, run_id: str, decision: str) -> Graph2State:
        """decision = "accept" | "reject" | "escalate" """
        state = self._load_state(run_id)
        state["client_decision"] = decision
        return self._invoke(state)

    def resume_after_hitl_approval(self, request_id: int) -> Graph2State:
        """Call once an admin has approved/rejected the senior-review
        request. Pulls the *exact* checkpointed state SENIOR_REVIEW_HITL
        paused on (not just the latest checkpoint for the run -- those
        could differ if something else touched the run meanwhile).

        - approved -> the candidate responsibility already sitting in
          `state["responsibility"]` (set by the constrained ReAct loop
          in DETERMINE_RESPONSIBILITY before the pause) is confirmed.
          We just clear the ambiguity flag and resume.
        - rejected -> ApprovalService only carries approve/reject + a
          free-text comment, no corrected value, so there is nothing to
          apply automatically. This escalates to a ticket the same way
          an inconclusive inspection does, and raises FailurePaused
          (caller must catch it, same as elsewhere).
        """
        data = self.hitl_manager.resume_data(request_id)  # raises ValueError if still pending

        state: Graph2State = dict(data["state"])  # type: ignore[assignment]
        admin_decision = data["admin_decision"]  # {"approved": bool, "comment": str, "admin_id": str}
        state["hitl_decision"] = admin_decision

        if data["approved"]:
            state["responsibility_ambiguous"] = False
            state["status"] = "running"
            return self._invoke(state)

        error = HitlRejected(
            f"Senior reviewer rejected candidate responsibility "
            f"'{state.get('responsibility')}' for run {state['run_id']}: "
            f"{admin_decision.get('comment', '')}"
        )
        # TicketManager.capture_failure() always raises FailurePaused
        # after checkpointing this state and opening a ticket -- it
        # never returns. Propagates straight to the caller.
        self.ticket_manager.capture_failure(
            run_id=state["run_id"],
            node_name=SENIOR_REVIEW_HITL,
            state=state,
            error=error,
        )
        raise AssertionError("unreachable: TicketManager.capture_failure() always raises FailurePaused")

    def resume_after_ticket_resolution(self, ticket_id: int) -> Graph2State:
        """Call once a ticket has been resolved. Two different nodes can
        open a ticket for this graph, so the resolution is applied
        differently depending on which one it was:

          - EVALUATE_INSPECTION (inconclusive result) -> management
            decided the outcome directly (e.g. goodwill compensation).
            Mark that node handled and route straight to
            AWAIT_CLIENT_DECISION with the resolution as the offer.

          - SENIOR_REVIEW_HITL (rejected candidate responsibility) ->
            the ticket resolution IS the corrected responsibility.
            Mark that node handled, adopt the resolution as the final
            responsibility, and continue to AWAIT_CLIENT_DECISION.

        We know which one it was directly from failure_tickets.state
        (TicketService.get()'s `node_name` alias) -- no need to guess
        from the shape of the checkpointed state."""
        origin_node = self.ticket_manager.tickets.get(ticket_id)["node_name"]
        data = self.ticket_manager.resume_data(ticket_id)  # raises ValueError if not resolved

        state: Graph2State = dict(data["state"])  # type: ignore[assignment]
        resolution = data["resolution"]

        completed = list(state.get("completed_nodes", []))

        if origin_node == EVALUATE_INSPECTION:
            if EVALUATE_INSPECTION not in completed:
                completed.append(EVALUATE_INSPECTION)
            state["completed_nodes"] = completed
            state["inspection_result"] = {"status": "resolved_via_ticket", "notes": resolution}
            state["proposed_resolution"] = resolution

        elif origin_node == SENIOR_REVIEW_HITL:
            if SENIOR_REVIEW_HITL not in completed:
                completed.append(SENIOR_REVIEW_HITL)
            state["completed_nodes"] = completed
            state["responsibility"] = resolution
            state["responsibility_ambiguous"] = False

        else:
            raise ValueError(
                f"Ticket {ticket_id} was opened by unexpected node "
                f"'{origin_node}' -- resume_after_ticket_resolution() only "
                f"knows how to apply resolutions for {EVALUATE_INSPECTION!r} "
                f"and {SENIOR_REVIEW_HITL!r}."
            )

        state["status"] = "running"
        return self._invoke(state)

    def get_state(self, run_id: str) -> Graph2State:
        return self._load_state(run_id)

    # ---- internals ------------------------------------------------

    def _load_state(self, run_id: str) -> Graph2State:
        latest = self.checkpoints.get_latest(run_id)
        if latest is None:
            raise KeyError(f"no checkpoints found for run: {run_id}")
        return dict(latest.state)  # type: ignore[return-value]

    def _invoke(self, state: Graph2State) -> Graph2State:
        """Re-run the whole compiled graph from START. Already-completed
        nodes are no-ops via `should_skip`; nodes waiting on a plain
        external input (inspection scheduling, client reply) route
        straight to END. HitlPaused / FailurePaused are intentionally
        NOT caught here -- they must surface to the caller so it can
        track the request_id / ticket_id needed to resume this exact
        run later."""
        return self._graph.invoke(state)