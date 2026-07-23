"""
Correlator: the heart of "stop paging me 40 times for one outage".

Strategy (kept simple and auditable on purpose - no black box):
1. Alerts on the SAME service within CORRELATION_WINDOW_SECONDS are merged.
2. Alerts on a DIFFERENT but TOPOLOGICALLY RELATED service (e.g. a downstream
   dependency) within the same window are merged into the same incident,
   with the upstream/root service marked as primary_service.
3. Everything else opens a new incident.

The service topology map is intentionally simple (a dict of
service -> [services that depend on it]). In a real deployment this would
be pulled from a service catalog / Kubernetes labels / Backstage, but the
correlator doesn't care where it comes from - just that it's a dict.
"""

from datetime import datetime, timedelta
from app.models.schemas import Alert, Incident
from app.storage import db
from app import config

# service -> list of downstream services that commonly alert as a side effect
SERVICE_TOPOLOGY = {
    "checkout-api": ["payments-service", "inventory-service"],
    "payments-service": ["fraud-detector"],
}


def _find_root_service(service: str) -> str:
    """If `service` is a known downstream of something else, return the
    upstream root so alerts get grouped under the actual cause, not the
    symptom."""
    for root, downstream in SERVICE_TOPOLOGY.items():
        if service in downstream:
            return root
    return service


def correlate(alert: Alert) -> Incident:
    root_service = _find_root_service(alert.service)
    window_start = alert.received_at - timedelta(seconds=config.CORRELATION_WINDOW_SECONDS)

    existing = db.find_open_incident(root_service, window_start)

    if existing:
        existing.alertnames = list(set(existing.alertnames + [alert.alertname]))
        existing.alert_count += 1
        existing.last_seen = alert.received_at
        # escalate severity if this alert is worse than what we've recorded
        if _severity_rank(alert.severity) > _severity_rank(existing.severity):
            existing.severity = alert.severity
        db.update_incident(existing)
        return existing

    incident = Incident(
        primary_service=root_service,
        alertnames=[alert.alertname],
        alert_count=1,
        severity=alert.severity,
        first_seen=alert.received_at,
        last_seen=alert.received_at,
    )
    return db.create_incident(incident)


def _severity_rank(sev: str) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(sev, 1)
