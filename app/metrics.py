"""
Self-observability: this app is itself something worth monitoring. These
metrics are exposed in standard Prometheus exposition format at /metrics,
so the same Prometheus instance watching your services can also watch
this alerting layer - answering "is the thing that watches my alerts
itself healthy?".

Uses the `prometheus_client` library rather than hand-rolling the text
format, since that's what any real Prometheus-instrumented service does.
"""

from prometheus_client import Counter, Histogram

# Every alert that came in, broken down by source (prometheus/datadog/generic)
alerts_ingested_total = Counter(
    "alert_intelligence_alerts_ingested_total",
    "Total number of raw alerts ingested",
    ["source"],
)

# Only increments when a NEW incident is opened (not when an alert merges
# into an existing one) - the gap between this and alerts_ingested_total
# IS the noise-reduction this whole project exists to provide.
incidents_created_total = Counter(
    "alert_intelligence_incidents_created_total",
    "Total number of distinct incidents created (after correlation)",
)

# Every time remediation actually ran (vs. merely being suggested),
# broken down by action and whether it was automatic or would-be dry-run.
remediation_actions_total = Counter(
    "alert_intelligence_remediation_actions_total",
    "Total number of remediation actions taken",
    ["action", "mode"],  # mode = "auto" or "dry_run"
)

# Distribution of confidence scores - lets you see on a Grafana panel
# whether your scorer is trending toward high or low confidence over time,
# which is a useful signal for whether runbooks/feedback are keeping up.
confidence_score = Histogram(
    "alert_intelligence_confidence_score",
    "Distribution of incident confidence scores (0-100)",
    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)