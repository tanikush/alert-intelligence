"""
Dispatcher: takes a fully correlated + enriched + scored incident and sends
ONE notification with full context, instead of N raw alerts.

Sends to Slack via an Incoming Webhook if SLACK_WEBHOOK_URL is configured
(see .env / config.py). If it's not configured, or the request fails for
any reason, falls back to printing to console so the app never crashes
just because Slack is unreachable.
"""

import requests
from app.models.schemas import Incident
from app import config


def notify(incident: Incident) -> None:
    message = _format(incident)
    _send(message)


def _format(incident: Incident) -> str:
    deploys = incident.context.get("recent_deploys", [])
    deploy_line = (
        f"⚠️  Deployed {deploys[0]['version']} by {deploys[0]['author']} "
        f"to {incident.environment} shortly before this fired"
        if deploys else "No recent deploys detected"
    )
    action_line = (
        f"✅ Auto-remediated with: {incident.suggested_action}"
        if incident.auto_remediated
        else f"💡 Suggested action: {incident.suggested_action}"
        if incident.suggested_action
        else "No known remediation for this pattern yet"
    )

    return (
        f"[Incident #{incident.id}] {incident.primary_service} [{incident.environment}] "
        f"({incident.severity}, confidence {incident.confidence_score}/100)\n"
        f"  Alerts merged: {', '.join(incident.alertnames)} (x{incident.alert_count})\n"
        f"  {deploy_line}\n"
        f"  {action_line}"
    )


def _send(message: str) -> None:
    if not config.SLACK_WEBHOOK_URL:
        _print_to_console(message)
        return

    try:
        response = requests.post(
            config.SLACK_WEBHOOK_URL,
            json={"text": message},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        # Never let a Slack outage take down alert processing - fall back
        # to console so the incident is still visible somewhere.
        print(f"[WARN] Slack notification failed: {e}")
        _print_to_console(message)


def _print_to_console(message: str) -> None:
    print("\n=== NOTIFICATION ===")
    print(message)
    print("====================\n")