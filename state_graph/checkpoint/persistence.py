"""Pure persistence against state_checkpoints — exactly the columns in
the adopted DDL (checkpoint_id, run_id, state_name, state_data,
created_at). No reason/metadata columns exist here on purpose; those are
folded into state_data as an envelope by checkpoint_manager.py so this
module never has to diverge from the schema you already committed to.
"""
from __future__ import annotations
 
import json
 
from state_graph import db
 
 
def insert(*, run_id: str, state_name: str, state_data: dict) -> int:
    """Returns the new checkpoint_id (AUTOINCREMENT)."""
    db.init_db()
    with db.connect() as conn:
        cursor = conn.execute(
            """INSERT INTO state_checkpoints (run_id, state_name, state_data)
               VALUES (?, ?, ?)""",
            (run_id, state_name, json.dumps(state_data, ensure_ascii=False)),
        )
        conn.commit()
        return cursor.lastrowid
 
 
def get_by_id(checkpoint_id: int):
    db.init_db()
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM state_checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
        ).fetchone()
 
 
def get_latest_for_run(run_id: str):
    db.init_db()
    with db.connect() as conn:
        return conn.execute(
            """SELECT * FROM state_checkpoints WHERE run_id = ?
               ORDER BY checkpoint_id DESC LIMIT 1""",
            (run_id,),
        ).fetchone()
 
 
def list_for_run(run_id: str) -> list:
    db.init_db()
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM state_checkpoints WHERE run_id = ? ORDER BY checkpoint_id ASC",
            (run_id,),
        ).fetchall()