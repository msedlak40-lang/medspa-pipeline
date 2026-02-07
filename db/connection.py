import sqlite3

from config import DB_FILE
from utils.file_utils import ensure_state_dir


def get_connection() -> sqlite3.Connection:
    ensure_state_dir()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn
