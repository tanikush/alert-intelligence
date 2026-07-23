"""
Generic adapter: for any tool that can send a plain JSON webhook (or for
testing). This is the simplest adapter and doubles as the reference
implementation new adapters should follow.
"""

from app.models.schemas import Alert


def parse_generic_payload(payload: dict) -> Alert:
    return Alert(
        source=payload.get("source", "generic"),
        service=payload["service"],
        alertname=payload["alertname"],
        severity=payload.get("severity", "warning"),
        message=payload.get("message", ""),
        labels=payload.get("labels", {}),
    )
