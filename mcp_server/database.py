from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent.parent / "db" / "redline.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn