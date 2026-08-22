"""
SQLite persistence for state-graph checkpoints.

Uses the project's existing db/redline.db database.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from state_graph.schema import RunState


_DB_PATH = Path(__file__).parent / "redline.db"


def _get_connection() -> sqlite3.Connection:
    """Return a connection to the project's existing SQLite database."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    """Create the latest-checkpoint table if it does not already exist."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state_graph_checkpoints (
                run_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _ensure_history_table() -> None:
    """Create the immutable checkpoint history table if needed."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state_graph_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                current_node TEXT NOT NULL,
                status TEXT NOT NULL,
                checkpoint_ts TEXT NOT NULL
            )
            """
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Latest checkpoint state
# ---------------------------------------------------------------------------

def upsert_state(run_state: RunState) -> None:
    """Save or overwrite the latest checkpoint for a run."""
    _ensure_table()

    state_json = json.dumps(
        run_state.model_dump(mode="json")
    )

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO state_graph_checkpoints (run_id, state_json)
            VALUES (?, ?)
            ON CONFLICT(run_id)
            DO UPDATE SET state_json = excluded.state_json
            """,
            (run_state.run_id, state_json),
        )
        conn.commit()


def get_latest_state(run_id: str) -> RunState:
    """Load the latest saved checkpoint for a run."""
    _ensure_table()

    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT state_json
            FROM state_graph_checkpoints
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"No checkpoint found for run_id={run_id}")

    state_data: dict[str, Any] = json.loads(row["state_json"])
    return RunState.model_validate(state_data)


def checkpoint_exists(run_id: str) -> bool:
    """Return True if a checkpoint exists."""
    _ensure_table()

    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM state_graph_checkpoints
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    return row is not None


def delete_state(run_id: str) -> None:
    """Delete a saved checkpoint."""
    _ensure_table()

    with _get_connection() as conn:
        conn.execute(
            """
            DELETE FROM state_graph_checkpoints
            WHERE run_id = ?
            """,
            (run_id,),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Immutable checkpoint history
# ---------------------------------------------------------------------------

def append_history(run_state: RunState) -> None:
    """Append an immutable history record for a checkpoint."""
    _ensure_history_table()

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO state_graph_history
                (run_id, current_node, status, checkpoint_ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_state.run_id,
                run_state.current_node,
                run_state.status.value,
                run_state.checkpoint_ts.isoformat(),
            ),
        )
        conn.commit()


def get_history(run_id: str) -> list[dict[str, Any]]:
    """Return checkpoint history in chronological order."""
    _ensure_history_table()

    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT current_node, status, checkpoint_ts
            FROM state_graph_history
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()

    return [
        {
            "current_node": row["current_node"],
            "status": row["status"],
            "checkpoint_ts": row["checkpoint_ts"],
        }
        for row in rows
    ]