from __future__ import annotations
 
from typing import Any
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.tickets.ticket_service import TicketService
 
 
class FailurePaused(Exception):
    """Unexpected failure. Distinct from HitlPaused — different
    exception type, different table, different status vocabulary
    (open/investigating/resolved vs pending/approved/rejected)."""
 
    def __init__(self, *, ticket_id: int, checkpoint_id: str | None, error_message: str = ""):
        self.ticket_id = ticket_id
        self.checkpoint_id = checkpoint_id
        super().__init__(
            f"Ticketed failure (ticket {ticket_id}, checkpoint {checkpoint_id}): {error_message}"
        )
 
 
class TicketManager:
    def __init__(self, *, checkpoints: CheckpointManager, tickets: TicketService):
        self.checkpoints = checkpoints
        self.tickets = tickets
 
    def capture_failure(
        self,
        *,
        run_id: str,
        node_name: str,
        state: dict[str, Any],
        error: Exception,
    ) -> None:
        checkpoint = self.checkpoints.save(
            run_id=run_id,
            node_name=node_name,
            state=state,
            reason="node_failure",
            metadata={"error_type": type(error).__name__, "error_message": str(error)},
        )
        ticket = self.tickets.create(
            run_id=run_id,
            checkpoint_id=checkpoint.checkpoint_id,
            node_name=node_name,
            error=error,
        )
        raise FailurePaused(
            ticket_id=ticket["ticket_id"],
            checkpoint_id=checkpoint.checkpoint_id,
            error_message=str(error),
        )
 
    def resume_data(self, ticket_id: int) -> dict[str, Any]:
        ticket = self.tickets.get(ticket_id)
        if ticket["status"] != "resolved":
            raise ValueError(f"Ticket {ticket_id} must be resolved before resume (status={ticket['status']}).")
 
        checkpoint = self.checkpoints.load(ticket["checkpoint_id"])
 
        return {
            "checkpoint_id": ticket["checkpoint_id"],
            "state": checkpoint.state,
            "ticket_id": ticket_id,
            "resolution": ticket["resolution"],
        }
 