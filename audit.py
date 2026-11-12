import sqlite3
import hashlib
import json
from datetime import datetime

DB_PATH = "helioshr_audit.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                event_hash TEXT PRIMARY KEY,
                employee_id TEXT,
                processed_at TEXT,
                result_json TEXT,
                event_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT,
                employee_name TEXT,
                system TEXT,
                action TEXT,
                success INTEGER,
                attempts INTEGER,
                message TEXT,
                resource_id TEXT,
                logged_at TEXT
            )
        """)


def event_hash(employee_id: str, email: str, start_date: str) -> str:
    raw = f"{employee_id}:{email}:{start_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def already_processed(h: str):
    with _conn() as conn:
        row = conn.execute(
            "SELECT result_json FROM processed_events WHERE event_hash = ?", (h,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def mark_processed(h: str, employee_id: str, result: dict, event: dict = None):
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_events VALUES (?, ?, ?, ?, ?)",
            (h, employee_id, datetime.utcnow().isoformat(),
             json.dumps(result), json.dumps(event) if event else None)
        )


def get_held_event(employee_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT event_json FROM processed_events WHERE employee_id = ? AND event_json IS NOT NULL",
            (employee_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def log_result(employee_id: str, employee_name: str, system: str,
               action: str, success: bool, attempts: int,
               message: str, resource_id: str = None):
    with _conn() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (employee_id, employee_name, system, action, success, attempts, message, resource_id, logged_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (employee_id, employee_name, system, action,
             1 if success else 0, attempts, message,
             resource_id, datetime.utcnow().isoformat())
        )


def get_audit(employee_id: str) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE employee_id = ? ORDER BY logged_at",
            (employee_id,)
        ).fetchall()
    cols = ["id", "employee_id", "employee_name", "system", "action",
            "success", "attempts", "message", "resource_id", "logged_at"]
    return [dict(zip(cols, r)) for r in rows]
