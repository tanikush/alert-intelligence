"""
Entrypoint. Wires: ingestion -> correlator -> enricher -> scorer ->
remediation -> notifier, and exposes a feedback endpoint that closes the
learning loop.

Run: uvicorn app.main:app --reload --port 8000
"""
from fastapi import Depends, Response
from app.security import require_api_key
from fastapi import FastAPI, HTTPException
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.models.schemas import FeedbackIn
from app.ingestion.generic_webhook import parse_generic_payload
from app.ingestion.prometheus_adapter import parse_alertmanager_payload
from app.core import correlator, enricher, scorer, remediation
from app.notifier import dispatcher
from app.storage import db
from app.dashboard_router import router as dashboard_router
from app import metrics

app = FastAPI(title="Alert Intelligence Layer")
app.include_router(dashboard_router)


@app.on_event("startup")
def _startup():
    db.init_db()


def _process(alert):
    """The full pipeline, run once per normalized alert."""
    metrics.alerts_ingested_total.labels(source=alert.source).inc()

    incident = correlator.correlate(alert)
    if incident.alert_count == 1:
        # alert_count == 1 right after correlate() means this alert
        # opened a brand new incident rather than merging into one -
        # this counter vs. alerts_ingested_total IS the noise reduction
        # this project exists to provide.
        metrics.incidents_created_total.inc()

    incident = enricher.enrich(incident)
    scorer.score(incident)
    metrics.confidence_score.observe(incident.confidence_score)

    incident = remediation.maybe_remediate(incident)
    db.update_incident(incident)
    dispatcher.notify(incident)
    return incident


@app.post("/webhook/generic", dependencies=[Depends(require_api_key)])
def webhook_generic(payload: dict):
    alert = parse_generic_payload(payload)
    incident = _process(alert)
    return {"incident_id": incident.id, "confidence": incident.confidence_score,
            "suggested_action": incident.suggested_action,
            "auto_remediated": incident.auto_remediated}


@app.post("/webhook/prometheus", dependencies=[Depends(require_api_key)])
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


@app.post("/incidents/{incident_id}/feedback", dependencies=[Depends(require_api_key)])
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


@app.get("/metrics")
def get_metrics():
    """No auth on this - Prometheus needs to scrape it directly, and it's
    read-only metrics, not a way to push data in (same reasoning as
    /dashboard and /api/incidents staying open)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)