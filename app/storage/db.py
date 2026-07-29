"""
Storage layer using SQLAlchemy Core, so the exact same code works against
both SQLite (zero-setup local development) and Postgres (production,
multi-instance deployments) - only `config.DATABASE_URL` changes between
the two, nothing here does.

Why this matters: SQLite is a single file. Two app instances writing to it
at once is unsafe and doesn't scale. Postgres is a real client-server
database, so multiple replicas of this app can all point at the same
Postgres instance and safely share incident data.
"""

import json
from datetime import datetime
from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    Integer, String, Text, Boolean,
)
from app.models.schemas import Incident
from app import config

engine = create_engine(config.DATABASE_URL, future=True)
metadata = MetaData()

incidents_table = Table(
    "incidents", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("primary_service", String),
    Column("alertnames", Text),
    Column("alert_count", Integer),
    Column("severity", String),
    Column("first_seen", String),
    Column("last_seen", String),
    Column("context", Text, default="{}"),
    Column("confidence_score", Integer, default=0),
    Column("suggested_action", String, nullable=True),
    Column("auto_remediated", Boolean, default=False),
    Column("status", String, default="open"),
    Column("resolved_by", String, nullable=True),
)

alertname_weights_table = Table(
    "alertname_weights", metadata,
    Column("alertname", String, primary_key=True),
    Column("weight", Integer, default=50),
)


def init_db() -> None:
    metadata.create_all(engine)


def _row_to_incident(row) -> Incident:
    m = row._mapping
    return Incident(
        id=m["id"],
        primary_service=m["primary_service"],
        alertnames=json.loads(m["alertnames"]),
        alert_count=m["alert_count"],
        severity=m["severity"],
        first_seen=datetime.fromisoformat(m["first_seen"]),
        last_seen=datetime.fromisoformat(m["last_seen"]),
        context=json.loads(m["context"]),
        confidence_score=m["confidence_score"],
        suggested_action=m["suggested_action"],
        auto_remediated=bool(m["auto_remediated"]),
        status=m["status"],
    )


def create_incident(incident: Incident) -> Incident:
    with engine.begin() as conn:
        result = conn.execute(
            incidents_table.insert().values(
                primary_service=incident.primary_service,
                alertnames=json.dumps(incident.alertnames),
                alert_count=incident.alert_count,
                severity=incident.severity,
                first_seen=incident.first_seen.isoformat(),
                last_seen=incident.last_seen.isoformat(),
                context=json.dumps(incident.context),
                confidence_score=incident.confidence_score,
                suggested_action=incident.suggested_action,
                auto_remediated=incident.auto_remediated,
                status=incident.status,
            )
        )
        incident.id = result.inserted_primary_key[0]
        return incident


def update_incident(incident: Incident) -> None:
    with engine.begin() as conn:
        conn.execute(
            incidents_table.update()
            .where(incidents_table.c.id == incident.id)
            .values(
                alertnames=json.dumps(incident.alertnames),
                alert_count=incident.alert_count,
                severity=incident.severity,
                last_seen=incident.last_seen.isoformat(),
                context=json.dumps(incident.context),
                confidence_score=incident.confidence_score,
                suggested_action=incident.suggested_action,
                auto_remediated=incident.auto_remediated,
                status=incident.status,
            )
        )


def find_open_incident(service: str, window_start):
    with engine.connect() as conn:
        row = conn.execute(
            incidents_table.select()
            .where(incidents_table.c.primary_service == service)
            .where(incidents_table.c.status == "open")
            .where(incidents_table.c.last_seen >= window_start.isoformat())
            .order_by(incidents_table.c.last_seen.desc())
            .limit(1)
        ).fetchone()
        return _row_to_incident(row) if row else None


def get_incident(incident_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            incidents_table.select().where(incidents_table.c.id == incident_id)
        ).fetchone()
        return _row_to_incident(row) if row else None


def list_incidents(limit: int = 50) -> list:
    with engine.connect() as conn:
        rows = conn.execute(
            incidents_table.select()
            .order_by(incidents_table.c.id.desc())
            .limit(limit)
        ).fetchall()
        return [_row_to_incident(r) for r in rows]


def find_resolved_incidents(service: str, limit: int = 5) -> list:
    with engine.connect() as conn:
        rows = conn.execute(
            incidents_table.select()
            .where(incidents_table.c.primary_service == service)
            .where(incidents_table.c.status != "open")
            .order_by(incidents_table.c.last_seen.desc())
            .limit(limit)
        ).fetchall()
        return [
            {"resolved_by": r._mapping["resolved_by"], "last_seen": r._mapping["last_seen"]}
            for r in rows
        ]


def resolve_incident(incident_id: int, status: str, resolved_by) -> None:
    with engine.begin() as conn:
        conn.execute(
            incidents_table.update()
            .where(incidents_table.c.id == incident_id)
            .values(status=status, resolved_by=resolved_by)
        )


def get_alertname_weight(alertname: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            alertname_weights_table.select().where(
                alertname_weights_table.c.alertname == alertname
            )
        ).fetchone()
        return row._mapping["weight"] if row else 50


def set_alertname_weight(alertname: str, weight: int) -> None:
    # Portable "upsert" (works identically on SQLite and Postgres): try an
    # update first; if no row was affected, insert one. Avoids
    # dialect-specific ON CONFLICT syntax.
    with engine.begin() as conn:
        result = conn.execute(
            alertname_weights_table.update()
            .where(alertname_weights_table.c.alertname == alertname)
            .values(weight=weight)
        )
        if result.rowcount == 0:
            conn.execute(
                alertname_weights_table.insert().values(
                    alertname=alertname, weight=weight
                )
            )