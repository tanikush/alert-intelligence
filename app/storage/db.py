"""
Storage layer using SQLite for zero-setup local runs. Swap the connection
in `_conn()` for a Postgres driver (psycopg) in production - every function
below is a thin wrapper so that's a localized change.
"""

import sqlite3
import json
from datetime import datetime
from app.models.schemas import Incident
from app import config


def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                primary_service TEXT NOT NULL,
                alertnames TEXT NOT NULL,
                alert_count INTEGER NOT NULL,
                severity TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                context TEXT DEFAULT '{}',
                confidence_score INTEGER DEFAULT 0,
                suggested_action TEXT,
                auto_remediated INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                resolved_by TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alertname_weights (
                alertname TEXT PRIMARY KEY,
                weight INTEGER DEFAULT 50
            )
        """)


def _row_to_incident(row: sqlite3.Row) -> Incident:
    return Incident(
        id=row["id"],
        primary_service=row["primary_service"],
        alertnames=json.loads(row["alertnames"]),
        alert_count=row["alert_count"],
        severity=row["severity"],
        first_seen=datetime.fromisoformat(row["first_seen"]),
        last_seen=datetime.fromisoformat(row["last_seen"]),
        context=json.loads(row["context"]),
        confidence_score=row["confidence_score"],
        suggested_action=row["suggested_action"],
        auto_remediated=bool(row["auto_remediated"]),
        status=row["status"],
    )


def create_incident(incident: Incident) -> Incident:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO incidents
               (primary_service, alertnames, alert_count, severity,
                first_seen, last_seen, context, confidence_score,
                suggested_action, auto_remediated, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                incident.primary_service,
                json.dumps(incident.alertnames),
                incident.alert_count,
                incident.severity,
                incident.first_seen.isoformat(),
                incident.last_seen.isoformat(),
                json.dumps(incident.context),
                incident.confidence_score,
                incident.suggested_action,
                int(incident.auto_remediated),
                incident.status,
            ),
        )
        incident.id = cur.lastrowid
        return incident


def update_incident(incident: Incident) -> None:
    with _conn() as conn:
        conn.execute(
            """UPDATE incidents SET
               alertnames=?, alert_count=?, severity=?, last_seen=?,
               context=?, confidence_score=?, suggested_action=?,
               auto_remediated=?, status=?
               WHERE id=?""",
            (
                json.dumps(incident.alertnames),
                incident.alert_count,
                incident.severity,
                incident.last_seen.isoformat(),
                json.dumps(incident.context),
                incident.confidence_score,
                incident.suggested_action,
                int(incident.auto_remediated),
                incident.status,
                incident.id,
            ),
        )


def find_open_incident(service: str, window_start: datetime) -> Incident | None:
    with _conn() as conn:
        row = conn.execute(
            """SELECT * FROM incidents
               WHERE primary_service = ? AND status = 'open' AND last_seen >= ?
               ORDER BY last_seen DESC LIMIT 1""",
            (service, window_start.isoformat()),
        ).fetchone()
        return _row_to_incident(row) if row else None


def get_incident(incident_id: int) -> Incident | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return _row_to_incident(row) if row else None


def find_resolved_incidents(service: str, limit: int = 5) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM incidents
               WHERE primary_service = ? AND status != 'open'
               ORDER BY last_seen DESC LIMIT ?""",
            (service, limit),
        ).fetchall()
        return [
            {"resolved_by": r["resolved_by"], "last_seen": r["last_seen"]}
            for r in rows
        ]


def resolve_incident(incident_id: int, status: str, resolved_by: str | None) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE incidents SET status = ?, resolved_by = ? WHERE id = ?",
            (status, resolved_by, incident_id),
        )


def get_alertname_weight(alertname: str) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT weight FROM alertname_weights WHERE alertname = ?", (alertname,)
        ).fetchone()
        return row["weight"] if row else 50


def set_alertname_weight(alertname: str, weight: int) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO alertname_weights (alertname, weight) VALUES (?, ?)
               ON CONFLICT(alertname) DO UPDATE SET weight = excluded.weight""",
            (alertname, weight),
        )
