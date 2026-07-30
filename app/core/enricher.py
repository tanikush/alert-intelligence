"""
Enricher: this is the piece existing alert tools skip. Before an incident
reaches a human (or the scorer), we attach:

1. Recent deploys to the affected service - matched by (service,
   environment), not service alone, so a staging deploy never gets
   credited/blamed for a production incident and vice versa. Each deploy
   entry also carries a version, so the notification can say exactly
   which release is implicated, not just "something deployed recently".
2. How similar past incidents on this service+environment were resolved
3. The matching runbook, if this alertname is a known pattern

In production, `_get_recent_deploys` would call your CD tool's API
(ArgoCD, Spinnaker, GitHub Deployments) - which would give you this same
(service, environment, version) triple naturally. Here it's stubbed with
an in-memory list so the pipeline is runnable end-to-end without external
dependencies.
"""

from datetime import datetime, timedelta
from app.models.schemas import Incident
from app.storage import db
from app.core import remediation

# Stub deploy log - swap for a real CD-tool API call in production.
# Keyed conceptually by (service, environment); version is what lets the
# notification say "this specific release" instead of "a recent change".
_FAKE_DEPLOY_LOG = [
    {"service": "checkout-api", "environment": "prod",
     "deployed_at": datetime.utcnow() - timedelta(minutes=12),
     "version": "v2.14.0", "author": "priya"},
    {"service": "checkout-api", "environment": "staging",
     "deployed_at": datetime.utcnow() - timedelta(minutes=3),
     "version": "v2.15.0-rc1", "author": "priya"},
]


def _get_recent_deploys(service: str, environment: str, within_minutes: int = 30) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)
    matches = [
        d for d in _FAKE_DEPLOY_LOG
        if d["service"] == service
        and d["environment"] == environment
        and d["deployed_at"] >= cutoff
    ]
    # serialize datetimes to strings so this is JSON-safe once stored as context
    return [{**d, "deployed_at": d["deployed_at"].isoformat()} for d in matches]


def enrich(incident: Incident) -> Incident:
    recent_deploys = _get_recent_deploys(incident.primary_service, incident.environment)
    past_incidents = db.find_resolved_incidents(incident.primary_service, limit=5)
    runbook = remediation.find_runbook(incident.alertnames)

    incident.context = {
        "recent_deploys": recent_deploys,
        "likely_caused_by_deploy": len(recent_deploys) > 0,
        # Exposes exactly which release is implicated, when known - this
        # is the concrete improvement: not just "a deploy happened", but
        # "version X in environment Y happened Z minutes ago".
        "implicated_version": recent_deploys[0]["version"] if recent_deploys else None,
        "past_resolutions": [
            {"resolved_by": p.get("resolved_by"), "when": p.get("last_seen")}
            for p in past_incidents
        ],
        "runbook": runbook,
    }
    db.update_incident(incident)
    return incident