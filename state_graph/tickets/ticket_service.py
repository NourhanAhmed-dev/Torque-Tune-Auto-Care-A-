from __future__ import annotations
# يستلم الفشل من المانيجر ويعمل تذكرة في الداتا بيز
 
from datetime import datetime, timezone
from typing import Any
 
from state_graph import db
from state_graph.contracts import PlatformTaskGateway
 
 
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
 
 
class TicketService:
    """Talks to failure_tickets (state_graph/db.py schema). Columns:
    ticket_id, run_id, state, error_type, error_message, checkpoint_id,
    status, assigned_to, resolution, created_at, resolved_at — no
    details_json / platform_task_id columns in the adopted schema, so
    those aren't stored here (platform_tasks stays optional, same as
    ApprovalService, for the same reason)."""
 
    VALID_STATUSES = {"open", "investigating", "resolved"}
 
    def __init__(self, *, platform_tasks: PlatformTaskGateway | None = None):
        self.platform_tasks = platform_tasks
 
    def create(
        self,
        *,
        run_id: str,
        checkpoint_id: str | None,
        node_name: str,
        error: Exception,
    ) -> dict[str, Any]:
        db.init_db()
        now = _now()
 
        if self.platform_tasks is not None:
            self.platform_tasks.create_task(
                task_type="failure_ticket",
                resource_id=run_id,
                title=f"Graph failure in {node_name}",
                payload={
                    "run_id": run_id, "node_name": node_name,
                    "checkpoint_id": checkpoint_id,
                    "error_type": type(error).__name__, "error_message": str(error),
                },
            )
 
        with db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO failure_tickets
                   (run_id, state, error_type, error_message, checkpoint_id,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'open', ?)""",
                (run_id, node_name, type(error).__name__, str(error),
                 checkpoint_id, now),
            )
            conn.commit()
            ticket_id = cursor.lastrowid
 
        return self.get(ticket_id)
 
    def set_status(self, ticket_id: int, status: str, *, assigned_to: str | None = None) -> dict[str, Any]:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid ticket status: {status}")
        with db.connect() as conn:
            if assigned_to is not None:
                conn.execute(
                    "UPDATE failure_tickets SET status = ?, assigned_to = ? WHERE ticket_id = ?",
                    (status, assigned_to, ticket_id),
                )
            else:
                conn.execute(
                    "UPDATE failure_tickets SET status = ? WHERE ticket_id = ?",
                    (status, ticket_id),
                )
            conn.commit()
        return self.get(ticket_id)
 
    def resolve(self, *, ticket_id: int, resolution: str) -> dict[str, Any]:
        ticket = self.get(ticket_id)
        if ticket["status"] == "resolved":
            raise ValueError(f"Ticket {ticket_id} is already resolved.")
 
        now = _now()
        with db.connect() as conn:
            conn.execute(
                """UPDATE failure_tickets
                   SET status = 'resolved', resolution = ?, resolved_at = ?
                   WHERE ticket_id = ?""",
                (resolution, now, ticket_id),
            )
            conn.commit()
        return self.get(ticket_id)
 
    def get(self, ticket_id: int) -> dict[str, Any]:
        db.init_db()
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM failure_tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown ticket: {ticket_id}")
        result = dict(row)
        result["node_name"] = result["state"]  # readable alias
        return result
 
    def list_tickets(self, *, run_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        db.init_db()
        clauses, params = [], []
        if run_id:
            clauses.append("run_id = ?"); params.append(run_id)
        if status:
            clauses.append("status = ?"); params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT ticket_id FROM failure_tickets {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self.get(r["ticket_id"]) for r in rows]
 