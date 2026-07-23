"""
Run with: pytest tests/test_correlator.py
Uses a temp sqlite file so it doesn't touch your dev database.
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import config

# Point config at a throwaway DB before importing anything that uses it
config.DB_PATH = tempfile.mktemp(suffix=".db")

from app.storage import db
from app.core import correlator
from app.models.schemas import Alert

db.init_db()


def test_same_service_alerts_merge_into_one_incident():
    now = datetime.utcnow()
    alert1 = Alert(source="prometheus", service="checkout-api",
                    alertname="HighErrorRate", severity="critical",
                    message="err", received_at=now)
    alert2 = Alert(source="prometheus", service="checkout-api",
                    alertname="HighLatency", severity="warning",
                    message="lat", received_at=now + timedelta(seconds=30))

    inc1 = correlator.correlate(alert1)
    inc2 = correlator.correlate(alert2)

    assert inc1.id == inc2.id
    assert inc2.alert_count == 2
    assert set(inc2.alertnames) == {"HighErrorRate", "HighLatency"}
    # severity should escalate to the worse of the two... but critical was
    # already first, so it stays critical
    assert inc2.severity == "critical"


def test_downstream_service_groups_under_root():
    now = datetime.utcnow()
    root_alert = Alert(source="prometheus", service="checkout-api",
                        alertname="HighErrorRate", severity="critical",
                        message="err", received_at=now)
    downstream_alert = Alert(source="prometheus", service="payments-service",
                              alertname="PaymentTimeout", severity="warning",
                              message="timeout", received_at=now + timedelta(seconds=10))

    inc1 = correlator.correlate(root_alert)
    inc2 = correlator.correlate(downstream_alert)

    assert inc1.id == inc2.id
    assert inc2.primary_service == "checkout-api"


if __name__ == "__main__":
    test_same_service_alerts_merge_into_one_incident()
    test_downstream_service_groups_under_root()
    print("All tests passed.")
