"""
Graph 1: Post-Tune Comeback / Warranty Dispute Investigation.

Flow:
    START
      ↓
    INTAKE_COMPLAINT
      ↓
    LINK_TO_ORIGINAL_LOG
      ↓
    SCHEDULE_INSPECTION
      ↓
    WAITING_INSPECTION
      ↓
    INSPECTION
      ↓
    DETERMINE_RESPONSIBILITY
      ↓
    WAITING_HITL
      ↓
    AWAIT_CLIENT_DECISION
      ↓
    COMPLETE

Inconclusive inspection:
    INSPECTION → TICKET_OPEN
"""

from state_graph.checkpoint import CheckpointManager
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

    def __init__(self, checkpoint_manager=None):
        self.checkpoints = checkpoint_manager or CheckpointManager()

        self.transitions = {
            self.START: self.INTAKE_COMPLAINT,
            self.INTAKE_COMPLAINT: self.LINK_TO_ORIGINAL_LOG,
            self.LINK_TO_ORIGINAL_LOG: self.SCHEDULE_INSPECTION,
            self.SCHEDULE_INSPECTION: self.WAITING_INSPECTION,
            self.INSPECTION: self.DETERMINE_RESPONSIBILITY,
            self.DETERMINE_RESPONSIBILITY: self.WAITING_HITL,
            self.AWAIT_CLIENT_DECISION: self.COMPLETE,
        }

    def start(self, run_id: str, payload=None) -> RunState:
        """Create and persist a new Graph 1 run."""

        state = RunState(
            run_id=run_id,
            graph_name="graph1",
            current_node=self.START,
            payload=payload or {},
        )

        self.checkpoints.save(state)
        return state

    def step(self, state: RunState) -> RunState:
        """Execute one graph transition and save a checkpoint."""

        current = state.current_node

        # Waiting for the real-world vehicle inspection.
        if current == self.WAITING_INSPECTION:
            state.status = RunStatus.WAITING_EXTERNAL
            self.checkpoints.save(state)
            return state

        # Waiting for Person 2's HITL component.
        if current == self.WAITING_HITL:
            state.status = RunStatus.WAITING_HITL
            self.checkpoints.save(state)
            return state

        # Ticket is handled by Person 2.
        if current == self.TICKET_OPEN:
            state.status = RunStatus.TICKET_OPEN
            self.checkpoints.save(state)
            return state

        if current == self.COMPLETE:
            state.status = RunStatus.COMPLETED
            self.checkpoints.save(state)
            return state

        if current not in self.transitions:
            raise ValueError(
                f"Invalid transition from node: {current}"
            )

        state.current_node = self.transitions[current]
        state.status = RunStatus.RUNNING

        self.checkpoints.save(state)
        return state

    def submit_inspection_result(
        self,
        state: RunState,
        result: str,
    ) -> RunState:
        """
        Submit the result of the physical vehicle inspection.

        A normal result continues the investigation.
        An inconclusive result opens a ticket.
        """

        state.payload["inspection_result"] = result

        if result == "inconclusive":
            state.current_node = self.TICKET_OPEN
        else:
            state.current_node = self.INSPECTION

        state.status = RunStatus.RUNNING
        self.checkpoints.save(state)

        return state

    def submit_client_decision(
        self,
        state: RunState,
        decision: str,
    ) -> RunState:
        """Record the client's decision and complete the investigation."""

        state.payload["client_decision"] = decision
        state.current_node = self.COMPLETE
        state.status = RunStatus.COMPLETED

        self.checkpoints.save(state)
        return state

    def resume(self, run_id: str) -> RunState:
        """Load the latest checkpoint and resume the graph."""

        state = self.checkpoints.load(run_id)

        # Do not automatically pass waiting states.
        if state.current_node in (
            self.WAITING_INSPECTION,
            self.WAITING_HITL,
            self.TICKET_OPEN,
        ):
            return state

        while state.current_node != self.COMPLETE:
            state = self.step(state)

        return state

    def get_state(self, run_id: str) -> RunState:
        """Return the latest checkpoint."""

        return self.checkpoints.load(run_id)