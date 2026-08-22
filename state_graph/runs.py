"""Lifecycle for state_graph_runs. Every checkpoint / hitl_task /
failure_ticket has a FOREIGN KEY on run_id -> state_graph_runs(run_id),
enforced (PRAGMA foreign_keys=ON in db.py) — so a run row must exist
before anything else can be inserted. ensure_run() makes that a
non-event for callers: create on first use, no-op after.
"""
from __future__ import annotations

from state_graph import db


def ensure_run(
    run_id: str,
    *,
    graph_type: str,
    vehicle_id: int | None = None,
    client_id: int | None = None,
) -> None:
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO state_graph_runs
               (run_id, graph_type, status, vehicle_id, client_id)
               VALUES (?, ?, 'running', ?, ?)
               ON CONFLICT(run_id) DO NOTHING""",
            (run_id, graph_type, vehicle_id, client_id),
        )


def touch_run(run_id: str, *, status: str | None = None, current_state: str | None = None) -> None:
    with db.connect() as conn:
        if status is not None and current_state is not None:
            conn.execute(
                """UPDATE state_graph_runs
                   SET status = ?, current_state = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE run_id = ?""",
                (status, current_state, run_id),
            )
        elif status is not None:
            conn.execute(
                "UPDATE state_graph_runs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (status, run_id),
            )
        elif current_state is not None:
            conn.execute(
                "UPDATE state_graph_runs SET current_state = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (current_state, run_id),
            )


def get_run(run_id: str):
    db.init_db()
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM state_graph_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
