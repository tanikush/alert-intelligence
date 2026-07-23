"""
Remediation engine: matches an incident's alertnames against known patterns
in data/runbooks.yaml. If the matched action is marked safe_to_automate AND
the incident's confidence score clears MIN_CONFIDENCE_FOR_AUTOMATION, the
action is auto-run (stubbed here as a log line - wire up to your actual
runner, e.g. a Kubernetes API call or Ansible playbook, in `_execute`).

Otherwise, it's surfaced as a *suggestion* only - never silently applied.
"""

import yaml
from app.models.schemas import Incident
from app import config

_runbooks_cache = None


def _load_runbooks() -> dict:
    global _runbooks_cache
    if _runbooks_cache is None:
        with open(config.RUNBOOKS_PATH) as f:
            _runbooks_cache = yaml.safe_load(f) or {}
    return _runbooks_cache


def find_runbook(alertnames: list[str]) -> dict | None:
    runbooks = _load_runbooks()
    for name in alertnames:
        if name in runbooks:
            return {"alertname": name, **runbooks[name]}
    return None


def maybe_remediate(incident: Incident) -> Incident:
    runbook = incident.context.get("runbook")
    if not runbook:
        return incident

    if incident.confidence_score < config.MIN_CONFIDENCE_FOR_SUGGESTION:
        return incident  # too low confidence even to suggest

    incident.suggested_action = runbook.get("action")

    can_automate = (
        runbook.get("safe_to_automate", False)
        and incident.confidence_score >= config.MIN_CONFIDENCE_FOR_AUTOMATION
    )
    if can_automate:
        _execute(runbook.get("action"), incident.primary_service)
        incident.auto_remediated = True

    return incident


def _execute(action: str, service: str) -> None:
    """Stub executor. Replace with real integrations:
    - "restart_pod"      -> kubernetes client: delete pod / rollout restart
    - "scale_up"         -> kubernetes client: patch HPA / deployment replicas
    - "rollback_deploy"  -> call your CD tool's rollback API
    """
    print(f"[AUTO-REMEDIATION] Running '{action}' on service '{service}'")
