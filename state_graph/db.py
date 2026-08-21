from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "db"
    / "redline.db"
)


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Redline database not found: {DB_PATH}"
        )

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    # Enable FK enforcement.
    conn.execute("PRAGMA foreign_keys = ON")

    return conn