# Alert Intelligence Layer

**A DevOps alert-fatigue solver.** Ingests raw alerts from Prometheus, Datadog, or
any generic webhook, correlates them into single incidents, enriches them with
real context (recent deploys, past resolutions, matching runbooks), scores
them by confidence, sends a single enriched notification to Slack, and
safely auto-applies remediation — including real Kubernetes actions — for
well-understood patterns.

Built and tested end-to-end on a real Kubernetes cluster (kind) with a live
Prometheus + Alertmanager + Grafana stack, and a real Slack workspace.

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

## Proof it works

Tested end-to-end — not just written, actually run against a real Kubernetes
cluster, real Prometheus alerts, and a real Slack workspace.

**Interactive API docs**

![API docs](screenshots/01-api-docs.png)

**Pipeline processing a test alert — correlation, confidence scoring, suggested action**

![Pipeline test](screenshots/02-pipeline-test.png)

**Deployed on a real Kubernetes cluster (kind) alongside Prometheus & Grafana**

![Kubernetes pods](screenshots/03-kubernetes-pods.png)

**Real Prometheus/Alertmanager alerts flowing into the app**

![Prometheus alerts](screenshots/04-prometheus-alerts.png)

**Enriched incident notification posted to Slack**

![Slack notification](screenshots/05-slack-notification.png)

**Auto-remediation deciding to act, safely, in dry-run mode**

![Auto-remediation dry-run](screenshots/06-auto-remediation-dryrun.png)

---

## Architecture

```
Alert Sources (Prometheus Alertmanager / Datadog / generic webhook)
        │
        ▼
┌───────────────────┐
│  Ingestion        │  normalizes every source into one common Alert schema
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  Correlator       │  groups related alerts into a single Incident
└───────────────────┘  (same service + topology-aware, time-windowed)
        │
        ▼
┌───────────────────┐
│  Enricher         │  attaches recent deploys, past incident history,
└───────────────────┘  and the matching runbook
        │
        ▼
┌───────────────────┐
│  Scorer           │  produces a 0-100 confidence score
└───────────────────┘  (rule-based + learns from feedback — no black box)
        │
        ▼
┌───────────────────┐
│  Remediation      │  suggests a fix, or auto-runs it — including real
│  Engine           │  Kubernetes pod restarts / scaling / rollbacks —
└───────────────────┘  if confidence and the action are both marked safe
        │
        ▼
┌───────────────────┐
│  Notifier         │  sends ONE enriched incident to Slack, not N raw
└───────────────────┘  alerts (falls back to console if unconfigured)
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
│   ├── config.py                # thresholds, correlation window, Slack + k8s settings
│   ├── models/schemas.py        # Pydantic models: Alert, Incident, Feedback
│   ├── ingestion/
│   │   ├── prometheus_adapter.py    # parses Alertmanager webhook payloads
│   │   └── generic_webhook.py       # parses plain JSON payloads
│   ├── core/
│   │   ├── correlator.py        # groups alerts into incidents (topology-aware)
│   │   ├── enricher.py          # attaches deploy/history/runbook context
│   │   ├── scorer.py            # confidence scoring + feedback learning
│   │   ├── remediation.py       # matches incident pattern → action
│   │   └── k8s_executor.py      # real Kubernetes actions (dry-run by default)
│   ├── storage/db.py             # SQLite persistence layer
│   └── notifier/dispatcher.py    # formats + sends the final incident to Slack
├── data/
│   ├── runbooks.yaml             # known alert patterns → remediation actions
│   └── service_k8s_map.yaml      # service name → namespace/deployment/labels
├── tests/test_correlator.py      # correlation logic unit tests
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env                          # SLACK_WEBHOOK_URL (not committed — see below)
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

## Slack notifications

Incidents are sent to Slack via an Incoming Webhook. If no webhook is
configured, the app falls back to printing the same message to console —
so it runs fine without Slack too.

**1. Create a Slack app and enable Incoming Webhooks**
- Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → *From scratch*
- Open **Incoming Webhooks** → toggle **On** → **Add New Webhook to Workspace**
- Pick a channel and copy the generated webhook URL

**2. Add it to a `.env` file in the project root** (never commit this file):
```bash
echo "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz" > .env
```

That's it — restart the app and every incident notification posts straight
to that Slack channels, with full context (deploy correlation, confidence
score, suggested or applied action).

---

## Kubernetes auto-remediation

When an incident's confidence score clears the automation threshold **and**
its matched runbook action is marked `safe_to_automate: true`, the
remediation engine calls a real Kubernetes action instead of just
suggesting one.

**Safety model — read this before enabling real actions:**
- `config.KUBE_DRY_RUN` defaults to **`True`**. In dry-run mode, every action
  logs exactly what it *would* do and returns without touching the cluster.
- Every action is scoped to exactly one service via `data/service_k8s_map.yaml`
  — there's no "act on everything" code path.
- `MIN_CONFIDENCE_FOR_AUTOMATION` (default `85`) gates automation separately
  from suggestion, so low-confidence incidents are only ever suggested, never
  auto-run.

**Setup:**

1. Map each service you want to auto-remediate to its real Kubernetes
   objects in `data/service_k8s_map.yaml`:
   ```yaml
   checkout-api:
     namespace: production
     deployment_name: checkout-api
     label_selector: "app=checkout-api"
   ```
   Get the real values from your cluster:
   ```bash
   kubectl get deployments -n <namespace>
   kubectl get pods -n <namespace> --show-labels
   ```

2. Leave `KUBE_DRY_RUN = True` while testing. Trigger a high-confidence
   incidents (send the same alert a few times, or submit feedback to raise
   the learned trust score for that alertname) and confirm you see:
   ```
   [DRY-RUN] Would delete pods in ns='...' matching '...'
   ```

3. Only flip `KUBE_DRY_RUN = False` once you've verified the mapping is
   correct, and ideally only against a disposable test cluster/deployment
   first — never point this at production without a staging run.

Supported actions out of the box (see `app/core/k8s_executor.py`):
| Action | What it does |
|---|---|
| `restart_pod` | Deletes matching pods; the owning Deployment recreates them |
| `scale_up` | Patches the Deployment's replica count up by 1 |
| `rollback_deploy` | Runs `kubectl rollout undo` on the Deployment |

---

## Deploying to a real Kubernetes cluster

This has been tested end-to-end on a local **kind** cluster running the
`kube-prometheus-stack` Helm chart (Prometheus + Alertmanager + Grafana).

**1. Build the image**
```bash
docker build -t alert-intelligence:v1 .
```

**2. Loads it into your cluster**

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

**4. Points Alertmanager at it**

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
in, get correlated, enriched, scored, and posted to Slack — live.

---

## Key design decisions

- **SQLite by default** — swap for Postgres in `config.py` for production;
  every storages calls is a thin wrapper so this is a localized change
- **Rule-based, auditable scorer** — not a black-box ML model. On-call
  engineers can see exactly *why* an incident scored the way it did, which
  is what actually earns trust in an alerting system
- **Remediation is opt-in per action** — an action only auto-runs if it's
  explicitly marked `safe_to_automate: true` in `runbooks.yaml` **and**
  confidence clears the automation threshold. Nothing destructive runs
  silently, and real Kubernetes actions stay in dry-run mode until
  explicitly enabled
- **Secrets stay out of git** — the Slack webhook URL lives in a local
  `.env` file (loaded via `python-dotenv`), excluded via `.gitignore`
- **Everything is swappable** — ingestion adapters, the notifier, and
  storage are thin layers so you can plug in PagerDuty or Datadog APIs
  without touching the core pipeline

---

## Roadmap / ideas for contribution

- [ ] Datadog and CloudWatch ingestion adapters
- [ ] PagerDuty notifier integration
- [ ] Service topology pulled from a real services catalog instead of a static dict
- [ ] Web dashboard for incident history and scorer weight visibility
- [ ] Postgres storage backend for multi-instance deployments
- [ ] HPA-aware scaling instead of flats replica increments

---

## License

MIT — use it, fork it, break it, learn from it.
