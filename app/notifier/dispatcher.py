"""
Dispatcher: takes a fully correlated + enriched + scored incident and sends
ONE notification with full context, instead of N raw alerts.

Stubbed to print a formatted message. Swap `_send` for a real Slack webhook
POST or PagerDuty Events API v2 call in production.
"""

from app.models.schemas import Incident


def notify(incident: Incident) -> None:
    message = _format(incident)
    _send(message)


def _format(incident: Incident) -> str:
    deploys = incident.context.get("recent_deploys", [])
    deploy_line = (
        f"⚠️  Deployed {deploys[0]['version']} by {deploys[0]['author']} "
        f"shortly before this fired"
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
        f"[Incident #{incident.id}] {incident.primary_service} "
        f"({incident.severity}, confidence {incident.confidence_score}/100)\n"
        f"  Alerts merged: {', '.join(incident.alertnames)} (x{incident.alert_count})\n"
        f"  {deploy_line}\n"
        f"  {action_line}"
    )


def _send(message: str) -> None:
    # Replace with: requests.post(SLACK_WEBHOOK_URL, json={"text": message})
    print("\n=== NOTIFICATION ===")
    print(message)
    print("====================\n")
