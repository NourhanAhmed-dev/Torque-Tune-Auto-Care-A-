from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "db"
    / "redline.db"
)


def init_db() -> None:
    
    if DB_PATH.exists():
        return
    schema = DB_PATH.parent / "schema.sql"
    seed = DB_PATH.parent / "seed.sql"
    conn = sqlite3.connect(DB_PATH)
    try:
        if schema.exists():
            conn.executescript(schema.read_text(encoding="utf-8"))
        if seed.exists():
            conn.executescript(seed.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Redline database not found: {DB_PATH}"
        )
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn