"""
Adapter for Prometheus Alertmanager's native webhook_config payload format.
Alertmanager sends a batch of alerts per POST under the "alerts" key -
this unpacks each one into our common Alert schema.

Real Alertmanager payload shape (simplified):
{
  "alerts": [
    {
      "labels": {"alertname": "HighErrorRate", "service": "checkout-api",
                 "severity": "critical"},
      "annotations": {"summary": "Error rate above 5%"},
      ...
    }
  ]
}
"""

from app.models.schemas import Alert


def parse_alertmanager_payload(payload: dict) -> list[Alert]:
    alerts = []
    for raw in payload.get("alerts", []):
        labels = raw.get("labels", {})
        annotations = raw.get("annotations", {})
        alerts.append(
            Alert(
                source="prometheus",
                service=labels.get("service", labels.get("job", "unknown")),
                alertname=labels.get("alertname", "UnknownAlert"),
                severity=labels.get("severity", "warning"),
                message=annotations.get("summary", annotations.get("description", "")),
                labels=labels,
            )
        )
    return alerts
