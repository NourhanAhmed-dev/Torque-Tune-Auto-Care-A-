from __future__ import annotations

import json
from state_graph import db

def insert(
    *,
    run_id: str,
    graph_name: str,
    node_name: str,
    state: dict,
    reason: str,
    metadata: dict,
) -> str:
    """
    Persist one checkpoint using the current state_checkpoints schema.
    """

    with db.connect() as conn:

        # Determine the next step for this run.
        row = conn.execute(
            """
            SELECT COALESCE(MAX(step_index), -1) + 1 AS next_step
            FROM state_checkpoints
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

        step_index = row["next_step"]

        checkpoint_id = f"{run_id}:{step_index}"

        conn.execute(
            """
            INSERT INTO state_checkpoints (
                checkpoint_id,
                run_id,
                graph_name,
                node_name,
                step_index,
                state_json,
                reason,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                checkpoint_id,
                run_id,
                graph_name,
                node_name,
                step_index,
                json.dumps(state, ensure_ascii=False),
                reason,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )

        conn.commit()

        return checkpoint_id


def get_by_id(checkpoint_id: str):
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM state_checkpoints
            WHERE checkpoint_id = ?
            """,
            (checkpoint_id,),
        ).fetchone()


def get_latest_for_run(run_id: str):
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM state_checkpoints
            WHERE run_id = ?
            ORDER BY step_index DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

def list_for_run(run_id: str) -> list:
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM state_checkpoints
            WHERE run_id = ?
            ORDER BY step_index ASC
            """,
            (run_id,),
        ).fetchall()