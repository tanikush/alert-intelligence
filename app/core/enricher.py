"""
Enricher: this is the piece existing alert tools skip. Before an incident
reaches a human (or the scorer), we attach:

1. Recent deploys to the affected service (was there a change right before
   this fired? - the single most useful piece of context in an incident)
2. How similar past incidents on this service were resolved
3. The matching runbook, if this alertname is a known pattern

In production, `_get_recent_deploys` would call your CD tool's API
(ArgoCD, Spinnaker, GitHub Deployments). Here it's stubbed with a simple
in-memory list so the pipeline is runnable end-to-end without external
dependencies.
"""

from datetime import datetime, timedelta
from app.models.schemas import Incident
from app.storage import db
from app.core import remediation

# Stub deploy log - swap for a real CD-tool API call in production
_FAKE_DEPLOY_LOG = [
    {"service": "checkout-api", "deployed_at": datetime.utcnow() - timedelta(minutes=12),
     "version": "v2.14.0", "author": "priya"},
]


def _get_recent_deploys(service: str, within_minutes: int = 30) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)
    matches = [d for d in _FAKE_DEPLOY_LOG if d["service"] == service and d["deployed_at"] >= cutoff]
    # serialize datetimes to strings so this is JSON-safe once stored as context
    return [{**d, "deployed_at": d["deployed_at"].isoformat()} for d in matches]


def enrich(incident: Incident) -> Incident:
    recent_deploys = _get_recent_deploys(incident.primary_service)
    past_incidents = db.find_resolved_incidents(incident.primary_service, limit=5)
    runbook = remediation.find_runbook(incident.alertnames)

    incident.context = {
        "recent_deploys": recent_deploys,
        "likely_caused_by_deploy": len(recent_deploys) > 0,
        "past_resolutions": [
            {"resolved_by": p.get("resolved_by"), "when": p.get("last_seen")}
            for p in past_incidents
        ],
        "runbook": runbook,
    }
    db.update_incident(incident)
    return incident
