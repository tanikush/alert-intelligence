# Alert Intelligence Layer

**A DevOps alert-fatigue solver.** Ingests raw alerts from Prometheus, Datadog, or
any generic webhook, correlates them into single incidents, enriches them with
real context (recent deploys, past resolutions, matching runbooks), scores
them by confidence, and suggests — or safely auto-applies — remediation for
well-understood patterns.

Built and tested end-to-end on a real Kubernetes cluster (kind) with a live
Prometheus + Alertmanager + Grafana stack.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active--development-orange.svg)

---

## The Problem

On-call engineers get paged 10-50 times for a single outage. One root cause
(say, a pod crash) cascades into alerts across every dependent service.
Existing tools like PagerDuty and Opsgenie mostly *group duplicate alerts* —
but they don't:

1. **Attach context** — what changed recently, how was this resolved last time
2. **Learn confidence over time** from on-call feedback
3. **Auto-remediate** safe, well-understood patterns

This project is a minimal, extensible core for that missing layer.

---

## Architecture

```
Alert Sources (Prometheus Alertmanager / Datadog / generic webhook)
        │
        ▼
┌───────────────────┐
│  Ingestion         │  normalizes every source into one common Alert schema
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  Correlator        │  groups related alerts into a single Incident
└───────────────────┘  (same service + topology-aware, time-windowed)
        │
        ▼
┌───────────────────┐
│  Enricher          │  attaches recent deploys, past incident history,
└───────────────────┘  and the matching runbook
        │
        ▼
┌───────────────────┐
│  Scorer            │  produces a 0-100 confidence score
└───────────────────┘  (rule-based + learns from feedback — no black box)
        │
        ▼
┌───────────────────┐
│  Remediation       │  suggests a fix, or auto-runs it if confidence and
│  Engine            │  the action are both marked safe
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  Notifier          │  sends ONE enriched incident, not N raw alerts
└───────────────────┘
        │
        ▼
  On-call feedback ──► retrains the scorer's learned weights for next time
```

---

## Project structure

```
alert-intelligence/
├── app/
│   ├── main.py                  # FastAPI entrypoint — wires the full pipeline
│   ├── config.py                # thresholds, correlation window, DB path
│   ├── models/schemas.py        # Pydantic models: Alert, Incident, Feedback
│   ├── ingestion/
│   │   ├── prometheus_adapter.py    # parses Alertmanager webhook payloads
│   │   └── generic_webhook.py       # parses plain JSON payloads
│   ├── core/
│   │   ├── correlator.py        # groups alerts into incidents (topology-aware)
│   │   ├── enricher.py          # attaches deploy/history/runbook context
│   │   ├── scorer.py            # confidence scoring + feedback learning
│   │   └── remediation.py       # matches incident pattern → action
│   ├── storage/db.py             # SQLite persistence layer
│   └── notifier/dispatcher.py    # formats + sends the final incident
├── data/runbooks.yaml            # known alert patterns → remediation actions
├── tests/test_correlator.py      # correlation logic unit tests
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## Quickstart (local)

```bash
git clone https://github.com/<your-username>/alert-intelligence.git
cd alert-intelligence

python -m venv venv
source venv/bin/activate        # Windows Git Bash: source venv/Scripts/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open interactive API docs: **http://localhost:8000/docs**

Send a test alert:
```bash
curl -X POST http://localhost:8000/webhook/generic \
  -H "Content-Type: application/json" -d '{
    "source": "prometheus",
    "service": "checkout-api",
    "alertname": "HighErrorRate",
    "severity": "critical",
    "message": "Error rate above 5% on checkout-api",
    "labels": {"env": "prod", "team": "payments"}
  }'
```

Give feedback on an incident (this is what trains the scorer):
```bash
curl -X POST http://localhost:8000/incidents/1/feedback \
  -H "Content-Type: application/json" \
  -d '{"was_real": true, "resolved_by": "restart_pod"}'
```

---

## Deploying to a real Kubernetes cluster

This has been tested end-to-end on a local **kind** cluster running the
`kube-prometheus-stack` Helm chart (Prometheus + Alertmanager + Grafana).

**1. Build the image**
```bash
docker build -t alert-intelligence:v1 .
```

**2. Load it into your cluster**

kind:
```bash
kind load docker-image alert-intelligence:v1 --name <your-cluster-name>
```
minikube:
```bash
eval $(minikube docker-env)
docker build -t alert-intelligence:v1 .
```

**3. Deploy**
```bash
kubectl apply -f k8s-deploy.yaml
```

**4. Point Alertmanager at it**

Add a receiver to your Alertmanager config pointing at the in-cluster service:
```yaml
receivers:
  - name: 'alert-intelligence'
    webhook_configs:
      - url: 'http://alert-intelligence.monitoring.svc.cluster.local:8000/webhook/prometheus'
        send_resolved: true
```

**5. Watch it work**
```bash
kubectl logs -n monitoring -l app=alert-intelligence -f
```

Real Prometheus alerts (e.g. `TargetDown`, `KubePodCrashLooping`) will flow
in, get correlated, enriched, and scored — live.

---

## Key design decisions

- **SQLite by default** — swap for Postgres in `config.py` for production;
  every storage call is a thin wrapper so this is a localized change
- **Rule-based, auditable scorer** — not a black-box ML model. On-call
  engineers can see exactly *why* an incident scored the way it did, which
  is what actually earns trust in an alerting system
- **Remediation is opt-in per action** — an action only auto-runs if it's
  explicitly marked `safe_to_automate: true` in `runbooks.yaml` **and**
  confidence clears the automation threshold. Nothing destructive runs
  silently
- **Everything is swappable** — ingestion adapters, the notifier, and
  storage are thin layers so you can plug in real Slack, PagerDuty, or
  Datadog APIs without touching the core pipeline

---

## Roadmap / ideas for contribution

- [ ] Datadog and CloudWatch ingestion adapters
- [ ] Real Slack / PagerDuty notifier integrations
- [ ] Kubernetes-native remediation executor (real pod restarts, HPA scaling)
- [ ] Service topology pulled from a real service catalog instead of a static dict
- [ ] Web dashboard for incident history and scorer weight visibility
- [ ] Postgres storage backend for multi-instance deployments

---

## License

MIT — use it, fork it, break it, learn from it.