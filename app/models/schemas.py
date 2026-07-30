"""
Common normalized schema. Every ingestion adapter (Prometheus, Datadog,
generic webhook) must convert its native payload into this shape before
it reaches the correlator. This is what makes the rest of the pipeline
source-agnostic.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Alert(BaseModel):
    source: str                     # "prometheus", "datadog", "generic"
    service: str                    # e.g. "checkout-api"
    alertname: str                  # e.g. "HighErrorRate"
    severity: str = "warning"       # "critical" | "warning" | "info"
    message: str
    labels: dict = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=datetime.utcnow)


class Incident(BaseModel):
    id: Optional[int] = None
    primary_service: str
    environment: str = "prod"
    alertnames: list[str]
    alert_count: int
    severity: str
    first_seen: datetime
    last_seen: datetime
    context: dict = Field(default_factory=dict)      # deploys, history, runbook
    confidence_score: int = 0
    suggested_action: Optional[str] = None
    auto_remediated: bool = False
    status: str = "open"            # "open" | "resolved" | "false_positive"


class FeedbackIn(BaseModel):
    was_real: bool                  # True = real incident, False = noise
    resolved_by: Optional[str] = None   # which action actually fixed it
