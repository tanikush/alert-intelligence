"""
Entrypoint. Wires: ingestion -> correlator -> enricher -> scorer ->
remediation -> notifier, and exposes a feedback endpoint that closes the
learning loop.

Run: uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from app.models.schemas import FeedbackIn
from app.ingestion.generic_webhook import parse_generic_payload
from app.ingestion.prometheus_adapter import parse_alertmanager_payload
from app.core import correlator, enricher, scorer, remediation
from app.notifier import dispatcher
from app.storage import db
from app.dashboard_router import router as dashboard_router

app = FastAPI(title="Alert Intelligence Layer")
app.include_router(dashboard_router)


@app.on_event("startup")
def _startup():
    db.init_db()


def _process(alert):
    """The full pipeline, run once per normalized alert."""
    incident = correlator.correlate(alert)
    incident = enricher.enrich(incident)
    scorer.score(incident)
    incident = remediation.maybe_remediate(incident)
    db.update_incident(incident)
    dispatcher.notify(incident)
    return incident


@app.post("/webhook/generic")
def webhook_generic(payload: dict):
    alert = parse_generic_payload(payload)
    incident = _process(alert)
    return {"incident_id": incident.id, "confidence": incident.confidence_score,
            "suggested_action": incident.suggested_action,
            "auto_remediated": incident.auto_remediated}


@app.post("/webhook/prometheus")
def webhook_prometheus(payload: dict):
    alerts = parse_alertmanager_payload(payload)
    results = [_process(a) for a in alerts]
    return {"processed": len(results), "incident_ids": [r.id for r in results]}


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: int):
    incident = db.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.post("/incidents/{incident_id}/feedback")
def submit_feedback(incident_id: int, feedback: FeedbackIn):
    """This is the loop most alert tools never close: on-call tells the
    system whether it was right, and the scorer's learned weights update
    for next time."""
    incident = db.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    scorer.record_feedback(incident, feedback.was_real)
    status = "resolved" if feedback.was_real else "false_positive"
    db.resolve_incident(incident_id, status, feedback.resolved_by)

    return {"incident_id": incident_id, "status": status, "learning": "weights updated"}
