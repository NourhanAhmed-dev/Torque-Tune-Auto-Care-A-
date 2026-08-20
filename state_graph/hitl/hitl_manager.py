from __future__ import annotations
 
from typing import Any 
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.hitl.approval_service import ApprovalService
 
 
class HitlPaused(Exception):
    """Expected graph pause. This is not an error ticket.
 
    Not a @dataclass on purpose: a dataclass Exception doesn't call
    Exception.__init__(*args), so str(exception) comes back empty —
    that's a real bug in the earlier version. This still exposes
    .request_id / .checkpoint_id as attributes, but str()/repr() also
    say something useful.
    """
 
    def __init__(self, *, request_id: int, checkpoint_id: str, reason: str = ""):
        self.request_id = request_id
        self.checkpoint_id = checkpoint_id
        self.reason = reason
        super().__init__(
            f"HITL pause (request {request_id}, checkpoint {checkpoint_id}): {reason}"
        )
 
 
class HitlManager:
    def __init__(self, *, checkpoints: CheckpointManager, approvals: ApprovalService):
        self.checkpoints = checkpoints
        self.approvals = approvals
 
    def require_decision(
        self,
        *,
        run_id: str,
        node_name: str,
        state: dict[str, Any],
        action: dict[str, Any],
        reason: str,
    ) -> None:
        """Pause the graph when the caller has already determined that
        human approval is required. The HITL manager does not evaluate
        business policies — that decision was already made by the node
        that called this."""
 
        checkpoint = self.checkpoints.save(
            run_id=run_id,
            node_name=node_name,
            state=state,
            reason="hitl_pause",
            metadata={"action": action, "reason": reason},
        )
 
        request = self.approvals.create_request(
            run_id=run_id,
            checkpoint_id=checkpoint.checkpoint_id,
            node_name=node_name,
            action=action,
            reason=reason,
        )
 
        raise HitlPaused(
            request_id=request["request_id"],
            checkpoint_id=checkpoint.checkpoint_id,
            reason=reason,
        )
 
    def resume_data(self, request_id: int) -> dict[str, Any]:
        """Retrieve the admin decision AND the exact checkpointed state
        to resume from — before resuming the graph."""
 
        request = self.approvals.get_request(request_id)
        if request["status"] == "pending":
            raise ValueError(f"Admin has not decided on request {request_id} yet.")
 
        checkpoint = self.checkpoints.load(request["checkpoint_id"])
 
        return {
            "checkpoint_id": request["checkpoint_id"],
            "state": checkpoint.state,
            "admin_decision": request["decision"],
            "approved": request["status"] == "approved",
            "status": request["status"],
        }