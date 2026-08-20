from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from state_graph import db
from state_graph.contracts import PlatformTaskGateway
 
 
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
 
 
class ApprovalService:
    """Talks to hitl_tasks (state_graph/db.py schema) — and, later, to a
    real platform. platform_tasks is optional on purpose: connecting to
    the actual admin platform is the next step after checkpointing;
    until then this runs with no external side channel at all."""
 
    def __init__(self, *, platform_tasks: PlatformTaskGateway | None = None):
        self.platform_tasks = platform_tasks
 
    def create_request(
        self,
        *,
        run_id: str,
        checkpoint_id: str | None,
        node_name: str,
        action: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Create a HITL task in hitl_tasks. `node_name` is stored in the
        `state` column — same convention as state_checkpoints.state_name,
        just named `state` in this table per the adopted schema."""
 
        db.init_db()
        created_at = _now()
 
        platform_task_id = None
        if self.platform_tasks is not None:
            platform_task_id = self.platform_tasks.create_task(
                task_type="hitl_approval",
                resource_id=run_id,
                title=f"Approval required: {node_name}",
                payload={
                    "run_id": run_id, "node_name": node_name,
                    "checkpoint_id": checkpoint_id, "action": action, "reason": reason,
                },
            )
 
        payload = {"action": action}
        if platform_task_id is not None:
            payload["platform_task_id"] = platform_task_id
 
        with db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO hitl_tasks
                   (run_id, checkpoint_id, state, reason, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (run_id, checkpoint_id, node_name, reason, json.dumps(payload), created_at),
            )
            conn.commit()
            task_id = cursor.lastrowid
 
        return self.get_request(task_id)
 
    def decide(self, *, request_id: int, admin_id: str, approved: bool, comment: str) -> dict[str, Any]:
        request = self.get_request(request_id)
        if request["status"] != "pending":
            raise ValueError(f"HITL request {request_id} already has a decision ({request['status']}).")
 
        decision = {"approved": approved, "comment": comment, "admin_id": admin_id}
        status = "approved" if approved else "rejected"
        resolved_at = _now()
 
        with db.connect() as conn:
            conn.execute(
                """UPDATE hitl_tasks
                   SET status = ?, admin_id = ?, decision = ?, resolved_at = ?
                   WHERE task_id = ?""",
                (status, admin_id, json.dumps(decision), resolved_at, request_id),
            )
            conn.commit()
 
        platform_task_id = request["payload"].get("platform_task_id")
        if platform_task_id and self.platform_tasks is not None:
            self.platform_tasks.close_task(platform_task_id=platform_task_id)
 
        return self.get_request(request_id)
 
    def get_request(self, request_id: int) -> dict[str, Any]:
        db.init_db()
        with db.connect() as conn:
            row = conn.execute(
                """SELECT task_id, run_id, checkpoint_id, state, reason, payload,
                          status, admin_id, decision, created_at, resolved_at
                   FROM hitl_tasks WHERE task_id = ?""",
                (request_id,),
            ).fetchone()
 
        if row is None:
            raise KeyError(f"Unknown HITL request: {request_id}")
 
        result = dict(row)
        result["payload"] = json.loads(result["payload"]) if result["payload"] else {}
        result["decision"] = json.loads(result["decision"]) if result["decision"] else None
        result["request_id"] = result["task_id"]
        result["node_name"] = result["state"]  # readable alias, same convention as elsewhere
        return result
 
    def list_requests(self, *, run_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        db.init_db()
        clauses, params = [], []
        if run_id:
            clauses.append("run_id = ?"); params.append(run_id)
        if status:
            clauses.append("status = ?"); params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT task_id FROM hitl_tasks {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self.get_request(r["task_id"]) for r in rows]
 