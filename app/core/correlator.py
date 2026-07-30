"""
Correlator: the heart of "stop paging me 40 times for one outage".

Strategy (kept simple and auditable on purpose - no black box):
1. Alerts on the SAME service within CORRELATION_WINDOW_SECONDS are merged.
2. Alerts on a DIFFERENT but TOPOLOGICALLY RELATED service (e.g. a downstream
   dependency) within the same window are merged into the same incident,
   with the upstream/root service marked as primary_service.
3. Everything else opens a new incident.

Service topology is fetched dynamically from Kubernetes (see
app/core/k8s_topology.py) with a static fallback - the correlator itself
doesn't care where the topology comes from, just that it's a
{downstream: upstream} dict.
"""

from datetime import datetime, timedelta
from app.models.schemas import Alert, Incident
from app.storage import db
from app.core import k8s_topology
from app import config


def _find_root_service(service: str) -> str:
    """If `service` is a known downstream of something else, return the
    upstream root so alerts get grouped under the actual cause, not the
    symptom. Topology is looked up fresh each call (k8s_topology caches
    internally on a TTL), so newly annotated services are picked up
    without restarting this app."""
    topology = k8s_topology.get_topology()
    return topology.get(service, service)


def correlate(alert: Alert) -> Incident:
    root_service = _find_root_service(alert.service)
    # Environment comes from the alert's labels (e.g. Prometheus/Alertmanager
    # sets label "env"). Defaults to "prod" so alerts without this label
    # still correlate sensibly instead of erroring.
    environment = alert.labels.get("env", "prod")
    window_start = alert.received_at - timedelta(seconds=config.CORRELATION_WINDOW_SECONDS)

    # Scoping by (service, environment) - not service alone - means a
    # staging alert never merges into a prod incident just because the
    # service name matches. This was a real gap: a service can run
    # multiple environments/versions at once, and lumping them together
    # under one incident hides which one is actually affected.
    existing = db.find_open_incident(root_service, environment, window_start)

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
        environment=environment,
        alertnames=[alert.alertname],
        alert_count=1,
        severity=alert.severity,
        first_seen=alert.received_at,
        last_seen=alert.received_at,
    )
    return db.create_incident(incident)


def _severity_rank(sev: str) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(sev, 1)