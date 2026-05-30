import sqlite3
import threading
from pathlib import Path

from config import WORKSPACE_DIR


class DataBorderConsent:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(WORKSPACE_DIR / "data" / "consent.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS consent (
            user_id TEXT,
            operation_type TEXT,
            consented INTEGER DEFAULT 0,
            asked_at TEXT,
            PRIMARY KEY (user_id, operation_type)
        )""")

    def has_consented(self, user_id: str, operation_type: str) -> bool:
        row = self.conn.execute(
            "SELECT consented FROM consent WHERE user_id=? AND operation_type=?",
            (user_id, operation_type),
        ).fetchone()
        return row is not None and row[0] == 1

    def record_consent(self, user_id: str, operation_type: str, consented: bool):
        self.conn.execute(
            "INSERT OR REPLACE INTO consent VALUES (?, ?, ?, datetime('now'))",
            (user_id, operation_type, 1 if consented else 0),
        )
        self.conn.commit()

    def needs_prompt(self, user_id: str, operation_type: str) -> bool:
        row = self.conn.execute(
            "SELECT consented FROM consent WHERE user_id=? AND operation_type=?",
            (user_id, operation_type),
        ).fetchone()
        return row is None

_instance: "DataBorderConsent | None" = None
_instance_lock = threading.Lock()


def get_consent_db() -> "DataBorderConsent":
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DataBorderConsent()
    return _instance
