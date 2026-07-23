"""
Scorer: produces a 0-100 confidence score answering "how likely is this a
real, actionable incident vs noise?".

Deliberately rule-based + weighted, NOT a black-box ML model:
  - On-call engineers need to trust and audit *why* something scored high,
    otherwise they'll ignore the system exactly like they ignore raw alerts.
  - Weights are stored per-alertname and adjusted by real feedback
    (see record_feedback), so the system genuinely learns from your
    environment over time without needing a training pipeline.

Score components:
  + severity of the alert
  + number of correlated alerts (more corroboration = more real)
  + recent deploy correlation (a deploy 12 min ago is a strong signal)
  + historical true-positive rate for this alertname (learned from feedback)
"""

from app.models.schemas import Incident
from app.storage import db

_SEVERITY_WEIGHT = {"critical": 40, "warning": 20, "info": 5}

# Base weight per alertname's historical true-positive rate.
# Starts neutral at 50 and is nudged by feedback over time.
_DEFAULT_TP_WEIGHT = 50


def score(incident: Incident) -> int:
    total = 0

    # 1. severity
    total += _SEVERITY_WEIGHT.get(incident.severity, 10)

    # 2. corroboration - more distinct alerts firing together = more real
    total += min(incident.alert_count * 5, 25)

    # 3. deploy correlation
    if incident.context.get("likely_caused_by_deploy"):
        total += 15

    # 4. learned true-positive rate per alertname (average across all names
    #    involved in this incident)
    tp_scores = [
        db.get_alertname_weight(name) for name in incident.alertnames
    ]
    avg_tp = sum(tp_scores) / len(tp_scores) if tp_scores else _DEFAULT_TP_WEIGHT
    # scale the learned weight (0-100) down to contribute up to 20 points
    total += round((avg_tp / 100) * 20)

    incident.confidence_score = min(total, 100)
    db.update_incident(incident)
    return incident.confidence_score


def record_feedback(incident: Incident, was_real: bool) -> None:
    """Nudge the learned weight for every alertname in this incident based
    on whether it turned out to be a real incident or noise. This is the
    feedback loop that existing tools don't close."""
    delta = 8 if was_real else -8
    for name in incident.alertnames:
        current = db.get_alertname_weight(name)
        updated = max(0, min(100, current + delta))
        db.set_alertname_weight(name, updated)
