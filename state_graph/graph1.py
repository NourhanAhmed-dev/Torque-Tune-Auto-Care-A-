"""
Graph 1: Post-Tune Comeback / Warranty Dispute Investigation.

Graph structure:

    START
      |
    INTAKE_COMPLAINT
      |
    LINK_TO_ORIGINAL_LOG
      |
    SCHEDULE_INSPECTION
      |
    WAITING_INSPECTION
      |
    INSPECTION
      |
    DETERMINE_RESPONSIBILITY
      |
    WAITING_HITL
      |
    AWAIT_CLIENT_DECISION
      |
    COMPLETE

Inconclusive inspection:

    INSPECTION -> TICKET_OPEN
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, START as LG_START, END

from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.schema import RunState, RunStatus


class Graph1:
    """Post-Tune Comeback / Warranty Dispute Investigation Graph."""

    START = "START"
    INTAKE_COMPLAINT = "INTAKE_COMPLAINT"
    LINK_TO_ORIGINAL_LOG = "LINK_TO_ORIGINAL_LOG"
    SCHEDULE_INSPECTION = "SCHEDULE_INSPECTION"
    WAITING_INSPECTION = "WAITING_INSPECTION"
    INSPECTION = "INSPECTION"
    DETERMINE_RESPONSIBILITY = "DETERMINE_RESPONSIBILITY"
    WAITING_HITL = "WAITING_HITL"
    AWAIT_CLIENT_DECISION = "AWAIT_CLIENT_DECISION"
    TICKET_OPEN = "TICKET_OPEN"
    COMPLETE = "COMPLETE"

    WAITING_NODES = {
        WAITING_INSPECTION,
        WAITING_HITL,
        TICKET_OPEN,
        COMPLETE,
    }

    def __init__(self, checkpoint_manager=None):
        """
        Create Graph 1.

        A default CheckpointManager is created for graph type "graph1".
        """

        self.checkpoints = (
            checkpoint_manager
            if checkpoint_manager is not None
            else CheckpointManager(graph_type="graph1")
        )

        # Explicit one-step transition map.
        #
        # Waiting states intentionally do not have automatic transitions.
        self.transitions = {
            self.START: self.INTAKE_COMPLAINT,
            self.INTAKE_COMPLAINT: self.LINK_TO_ORIGINAL_LOG,
            self.LINK_TO_ORIGINAL_LOG: self.SCHEDULE_INSPECTION,
            self.SCHEDULE_INSPECTION: self.WAITING_INSPECTION,
            self.INSPECTION: self.DETERMINE_RESPONSIBILITY,
            self.DETERMINE_RESPONSIBILITY: self.WAITING_HITL,
            self.AWAIT_CLIENT_DECISION: self.COMPLETE,
        }

        self.graph = self.get_graph()

    # ================================================================
    # Utility helpers
    # ================================================================

    @staticmethod
    def _copy_state(state: RunState | dict[str, Any]) -> RunState:
        """Always return a real RunState object."""

        if isinstance(state, RunState):
            return state

        if hasattr(RunState, "model_validate"):
            return RunState.model_validate(state)

        return RunState.parse_obj(state)

    @staticmethod
    def _state_dict(state: RunState) -> dict[str, Any]:
        """
        Convert RunState to a JSON-safe dictionary.

        Pydantic v2:
            model_dump(mode="json")

        Pydantic v1:
            dict()
        """

        if hasattr(state, "model_dump"):
            return state.model_dump(mode="json")

        return state.dict()

    def _save_state(
        self,
        state: RunState,
        *,
        reason: str,
    ) -> RunState:
        """
        Persist the current state using the actual CheckpointManager API.
        """

        state = self._copy_state(state)

        state_data = self._state_dict(state)

        self.checkpoints.save(
            run_id=state.run_id,
            node_name=state.current_node,
            state=state_data,
            reason=reason,
            metadata={
                "graph": "graph1",
                "status": (
                    state.status.value
                    if hasattr(state.status, "value")
                    else str(state.status)
                ),
            },
        )

        return state

    # ================================================================
    # LangGraph node functions
    # ================================================================

    def _intake_complaint(self, state: RunState) -> dict[str, Any]:
        state = self._copy_state(state)

        state.current_node = self.INTAKE_COMPLAINT
        state.status = RunStatus.RUNNING

        self._save_state(
            state,
            reason="Complaint intake completed",
        )

        return self._state_dict(state)

    def _link_to_original_log(self, state: RunState) -> dict[str, Any]:
        state = self._copy_state(state)

        state.current_node = self.LINK_TO_ORIGINAL_LOG
        state.status = RunStatus.RUNNING

        self._save_state(
            state,
            reason="Original tuning log linked",
        )

        return self._state_dict(state)

    def _schedule_inspection(self, state: RunState) -> dict[str, Any]:
        """Schedule the physical vehicle inspection."""

        state = self._copy_state(state)

        state.current_node = self.SCHEDULE_INSPECTION
        state.status = RunStatus.RUNNING

        self._save_state(
            state,
            reason="Inspection scheduled",
        )

        return self._state_dict(state)

    def _waiting_inspection(self, state: RunState) -> dict[str, Any]:
        """
        Pause at the external inspection stage.

        The graph must stop here until an external inspection result
        is submitted.
        """

        state = self._copy_state(state)

        state.current_node = self.WAITING_INSPECTION
        state.status = RunStatus.WAITING_EXTERNAL

        self._save_state(
            state,
            reason="Waiting for physical vehicle inspection",
        )

        return self._state_dict(state)

    def _inspection(self, state: RunState) -> dict[str, Any]:
        """Process a submitted inspection result."""

        state = self._copy_state(state)

        state.current_node = self.INSPECTION
        state.status = RunStatus.RUNNING

        self._save_state(
            state,
            reason="Inspection processed",
        )

        return self._state_dict(state)

    def _determine_responsibility(
        self,
        state: RunState,
    ) -> dict[str, Any]:
        """Determine responsibility after a conclusive inspection."""

        state = self._copy_state(state)

        state.current_node = self.DETERMINE_RESPONSIBILITY
        state.status = RunStatus.RUNNING

        self._save_state(
            state,
            reason="Responsibility determined",
        )

        return self._state_dict(state)

    def _waiting_hitl(self, state: RunState) -> dict[str, Any]:
        """Pause for human-in-the-loop decision."""

        state = self._copy_state(state)

        state.current_node = self.WAITING_HITL
        state.status = RunStatus.WAITING_HITL

        self._save_state(
            state,
            reason="Waiting for human decision",
        )

        return self._state_dict(state)

    def _await_client_decision(
        self,
        state: RunState,
    ) -> dict[str, Any]:
        """Move into the client decision stage."""

        state = self._copy_state(state)

        state.current_node = self.AWAIT_CLIENT_DECISION
        state.status = RunStatus.RUNNING

        self._save_state(
            state,
            reason="Awaiting client decision",
        )

        return self._state_dict(state)

    def _ticket_open(self, state: RunState) -> dict[str, Any]:
        """Open a ticket for an inconclusive inspection."""

        state = self._copy_state(state)

        state.current_node = self.TICKET_OPEN
        state.status = RunStatus.TICKET_OPEN

        self._save_state(
            state,
            reason="Inspection inconclusive; ticket opened",
        )

        return self._state_dict(state)

    def _complete(self, state: RunState) -> dict[str, Any]:
        """Complete the warranty investigation."""

        state = self._copy_state(state)

        state.current_node = self.COMPLETE
        state.status = RunStatus.COMPLETED

        self._save_state(
            state,
            reason="Graph 1 investigation completed",
        )

        return self._state_dict(state)

    # ================================================================
    # Routing
    # ================================================================

    def _inspection_route(self, state: RunState) -> str:
        """Route inspection result."""

        state = self._copy_state(state)

        result = state.payload.get("inspection_result")

        if result == "inconclusive":
            return "inconclusive"

        return "normal"

    # ================================================================
    # LangGraph construction
    # ================================================================

    def get_graph(self):
        """
        Build the LangGraph StateGraph.

        LangGraph defines the official topology.

        Public step() executes one logical transition at a time because
        external waiting states must not be skipped.
        """

        workflow = StateGraph(dict)

        workflow.add_node(
            self.INTAKE_COMPLAINT,
            self._intake_complaint,
        )

        workflow.add_node(
            self.LINK_TO_ORIGINAL_LOG,
            self._link_to_original_log,
        )

        workflow.add_node(
            self.SCHEDULE_INSPECTION,
            self._schedule_inspection,
        )

        workflow.add_node(
            self.WAITING_INSPECTION,
            self._waiting_inspection,
        )

        workflow.add_node(
            self.INSPECTION,
            self._inspection,
        )

        workflow.add_node(
            self.DETERMINE_RESPONSIBILITY,
            self._determine_responsibility,
        )

        workflow.add_node(
            self.WAITING_HITL,
            self._waiting_hitl,
        )

        workflow.add_node(
            self.AWAIT_CLIENT_DECISION,
            self._await_client_decision,
        )

        workflow.add_node(
            self.TICKET_OPEN,
            self._ticket_open,
        )

        workflow.add_node(
            self.COMPLETE,
            self._complete,
        )

        # START -> INTAKE
        workflow.add_edge(
            LG_START,
            self.INTAKE_COMPLAINT,
        )

        # INTAKE -> LINK
        workflow.add_edge(
            self.INTAKE_COMPLAINT,
            self.LINK_TO_ORIGINAL_LOG,
        )

        # LINK -> SCHEDULE
        workflow.add_edge(
            self.LINK_TO_ORIGINAL_LOG,
            self.SCHEDULE_INSPECTION,
        )

        # SCHEDULE -> WAITING_INSPECTION
        workflow.add_edge(
            self.SCHEDULE_INSPECTION,
            self.WAITING_INSPECTION,
        )

        # IMPORTANT:
        # LangGraph topology includes this edge, but public step()
        # deliberately stops at WAITING_INSPECTION.
        workflow.add_edge(
            self.WAITING_INSPECTION,
            self.INSPECTION,
        )

        # INSPECTION branching
        workflow.add_conditional_edges(
            self.INSPECTION,
            self._inspection_route,
            {
                "normal": self.DETERMINE_RESPONSIBILITY,
                "inconclusive": self.TICKET_OPEN,
            },
        )

        # Responsibility -> HITL
        workflow.add_edge(
            self.DETERMINE_RESPONSIBILITY,
            self.WAITING_HITL,
        )

        # HITL -> client decision
        workflow.add_edge(
            self.WAITING_HITL,
            self.AWAIT_CLIENT_DECISION,
        )

        # Client decision -> complete
        workflow.add_edge(
            self.AWAIT_CLIENT_DECISION,
            self.COMPLETE,
        )

        # Inconclusive -> ticket
        workflow.add_edge(
            self.TICKET_OPEN,
            END,
        )

        # Complete -> END
        workflow.add_edge(
            self.COMPLETE,
            END,
        )

        return workflow.compile()

    # ================================================================
    # Public API
    # ================================================================

    def step(self, state: RunState) -> RunState:
        """
        Execute exactly ONE logical transition.

        External waiting states stop immediately.
        """

        state = self._copy_state(state)

        current = state.current_node

        # ------------------------------------------------------------
        # WAITING_INSPECTION
        # ------------------------------------------------------------

        if current == self.WAITING_INSPECTION:
            state.status = RunStatus.WAITING_EXTERNAL

            return self._save_state(
                state,
                reason="Waiting for physical vehicle inspection",
            )

        # ------------------------------------------------------------
        # WAITING_HITL
        # ------------------------------------------------------------

        if current == self.WAITING_HITL:
            state.status = RunStatus.WAITING_HITL

            return self._save_state(
                state,
                reason="Waiting for human decision",
            )

        # ------------------------------------------------------------
        # TICKET_OPEN
        # ------------------------------------------------------------

        if current == self.TICKET_OPEN:
            state.status = RunStatus.TICKET_OPEN

            return self._save_state(
                state,
                reason="Ticket remains open",
            )

        # ------------------------------------------------------------
        # COMPLETE
        # ------------------------------------------------------------

        if current == self.COMPLETE:
            state.status = RunStatus.COMPLETED

            return self._save_state(
                state,
                reason="Graph 1 already completed",
            )

        # ------------------------------------------------------------
        # Normal transitions
        # ------------------------------------------------------------

        if current == self.START:
            self._intake_complaint(state)

        elif current == self.INTAKE_COMPLAINT:
            self._link_to_original_log(state)

        elif current == self.LINK_TO_ORIGINAL_LOG:
            self._schedule_inspection(state)

        elif current == self.SCHEDULE_INSPECTION:
            self._waiting_inspection(state)

        elif current == self.INSPECTION:
            result = self._inspection_route(state)

            if result == "inconclusive":
                self._ticket_open(state)
            else:
                self._determine_responsibility(state)

        elif current == self.DETERMINE_RESPONSIBILITY:
            self._waiting_hitl(state)

        elif current == self.AWAIT_CLIENT_DECISION:
            self._complete(state)

        else:
            raise ValueError(
                f"Invalid transition from node: {current}"
            )

        return self._copy_state(state)

    # ================================================================
    # Start
    # ================================================================

    def start(
        self,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> RunState:
        """
        Create and persist a new Graph 1 run.

        The initial state MUST remain at START.
        """

        state = RunState(
            run_id=run_id,
            graph_name="graph1",
            current_node=self.START,
            payload=dict(payload or {}),
        )

        # Explicitly register the run before inserting the checkpoint.
        self.checkpoints.start_run(run_id)

        self._save_state(
            state,
            reason="Graph 1 run started",
        )

        return state

    # ================================================================
    # Inspection result
    # ================================================================

    def submit_inspection_result(
        self,
        state: RunState,
        result: str,
    ) -> RunState:
        """
        Submit the physical inspection result.

        A conclusive result moves to INSPECTION.

        An inconclusive result opens TICKET_OPEN immediately.
        """

        state = self._copy_state(state)

        if state.current_node != self.WAITING_INSPECTION:
            raise ValueError(
                "Inspection result can only be submitted while "
                "the graph is at WAITING_INSPECTION."
            )

        if not result:
            raise ValueError("Inspection result cannot be empty.")

        state.payload["inspection_result"] = result

        # ------------------------------------------------------------
        # Inconclusive -> ticket
        # ------------------------------------------------------------

        if result == "inconclusive":
            state.current_node = self.TICKET_OPEN
            state.status = RunStatus.TICKET_OPEN

            self._save_state(
                state,
                reason="Inconclusive inspection; ticket opened",
            )

            return state

        # ------------------------------------------------------------
        # Conclusive -> inspection
        # ------------------------------------------------------------

        state.current_node = self.INSPECTION
        state.status = RunStatus.RUNNING

        self._save_state(
            state,
            reason="Inspection result submitted",
        )

        return state

    # ================================================================
    # Client decision
    # ================================================================

    def submit_client_decision(
        self,
        state: RunState,
        decision: str,
    ) -> RunState:
        """
        Record the client's decision.

        The decision can only be submitted from WAITING_HITL or
        AWAIT_CLIENT_DECISION.
        """

        state = self._copy_state(state)

        if state.current_node not in (
            self.WAITING_HITL,
            self.AWAIT_CLIENT_DECISION,
        ):
            raise ValueError(
                "Client decision can only be submitted while "
                "waiting for a client/HITL decision."
            )

        if not decision:
            raise ValueError("Client decision cannot be empty.")

        state.payload["client_decision"] = decision

        state.current_node = self.COMPLETE
        state.status = RunStatus.COMPLETED

        self._save_state(
            state,
            reason="Client decision submitted; investigation completed",
        )

        # Mark the underlying run as completed as well.
        try:
            self.checkpoints.mark_run_finished(
                state.run_id,
                status="completed",
            )
        except Exception:
            # The checkpoint itself is already persisted. Do not hide
            # the successful state transition if run-status bookkeeping
            # fails.
            pass

        return state

    # ================================================================
    # State retrieval
    # ================================================================

    def get_state(self, run_id: str) -> RunState:
        """
        Return the latest persisted checkpoint as RunState.
        """

        checkpoint = self.checkpoints.get_latest(run_id)

        if checkpoint is None:
            raise ValueError(
                f"No checkpoint found for run_id={run_id}"
            )

        if hasattr(checkpoint, "state"):
            return self._copy_state(checkpoint.state)

        return self._copy_state(checkpoint)

    # ================================================================
    # Resume
    # ================================================================

    def resume(self, run_id: str) -> RunState:
        """
        Recover the latest checkpoint.

        IMPORTANT:
        Waiting states are returned immediately and NEVER skipped.
        """

        state = self.get_state(run_id)

        # ------------------------------------------------------------
        # Never skip external waiting states.
        # ------------------------------------------------------------

        if state.current_node in (
            self.WAITING_INSPECTION,
            self.WAITING_HITL,
            self.TICKET_OPEN,
            self.COMPLETE,
        ):
            return state

        # ------------------------------------------------------------
        # Continue only until the next waiting state.
        # ------------------------------------------------------------

        while state.current_node not in (
            self.WAITING_INSPECTION,
            self.WAITING_HITL,
            self.TICKET_OPEN,
            self.COMPLETE,
        ):
            state = self.step(state)

        return state