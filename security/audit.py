import json
import sqlite3
from datetime import datetime
from pathlib import Path

from config import WORKSPACE_DIR


class AuditLogger:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(WORKSPACE_DIR / "data" / "audit.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, user_id TEXT, action TEXT,
            risk_level TEXT, details TEXT, result TEXT
        )""")

    def log(self, user_id: str, action: str, risk, details: dict, result: str):
        risk_str = risk.value if hasattr(risk, "value") else str(risk)
        self.conn.execute(
            "INSERT INTO audit_log VALUES (NULL,?,?,?,?,?,?)",
            (datetime.now().isoformat(), user_id, action,
             risk_str, json.dumps(details, ensure_ascii=False), result)
        )
        self.conn.commit()


audit_logger = AuditLogger()
