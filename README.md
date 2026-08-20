# Alert Intelligence Layer

**A DevOps alert-fatigue solver.** Ingests raw alerts from Prometheus, Datadog, or
any generic webhook, correlates them into single incidents using service
topology discovered live from Kubernetes, enriches them with real context
(recent deploys, past resolutions, matching runbooks), scores them by
confidence, sends a single enriched notification to Slack, shows
everything on a live dashboard, and safely auto-applies remediation —
including real Kubernetes actions — for well-understood patterns. Runs on
SQLite locally or Postgres in production, safely across multiple replicas.

Built and tested end-to-end on a real Kubernetes cluster (kind) with a live
Prometheus + Alertmanager + Grafana stack, a real Slack workspace, a custom
Prometheus alerting rule, a CI/CD pipeline that builds and publishes the
Docker image automatically, dynamic topology discovery via the Kubernetes
API, and a real Postgres database shared across 2 app replicas.

![CI](https://github.com/tanikush/alert-intelligence/actions/workflows/ci.yml/badge.svg)
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
cluster, real Prometheus alerts, a real Slack workspace, and a real CI/CD
pipeline.

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

**Auto-remediation deciding to acts, safely, in dry-run mode**

![Auto-remediation dry-run](screenshots/06-auto-remediation-dryrun.png)

**Live dashboard showing real cluster alerts as they arrive**

![Live dashboard with real alerts](screenshots/07-live-dashboard-real-alerts.png)

**A custom, hand-written PrometheusRule firing and flowing through the full pipeline**

![Custom rule on live dashboard](screenshots/08-custom-rule-live-dashboard.png)

---

## Architecture:-

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
┌───────────────────┐
│  Dashboard        │  live view of every incident, confidence score, and
└───────────────────┘  remediation status, polling every 4 seconds
        │
        ▼
  On-call feedback ──► retrains the scorer's learned weights for next time
```

---

## Project structure:-

```
alert-intelligence/
├── .github/workflows/ci.yml      # tests + Docker build/push on every push to main
├── app/
│   ├── main.py                  # FastAPI entrypoint — wires the full pipeline
│   ├── config.py                # thresholds, correlation window, Slack + k8s + DB settings
│   ├── dashboard_router.py      # serves the live dashboard + /api/incidents
│   ├── models/schemas.py        # Pydantic models: Alert, Incident, Feedback
│   ├── ingestion/
│   │   ├── prometheus_adapter.py    # parses Alertmanager webhook payloads
│   │   └── generic_webhook.py       # parses plain JSON payloads
│   ├── core/
│   │   ├── correlator.py        # groups alerts into incidents (topology-aware)
│   │   ├── k8s_topology.py      # discovers service topology from K8s annotations
│   │   ├── enricher.py          # attaches deploy/history/runbook context
│   │   ├── scorer.py            # confidence scoring + feedback learning
│   │   ├── remediation.py       # matches incident pattern → action
│   │   └── k8s_executor.py      # real Kubernetes actions (dry-run by default)
│   ├── storage/db.py             # SQLAlchemy storage layer (SQLite or Postgres)
│   └── notifier/dispatcher.py    # formats + sends the final incident to Slack
├── static/dashboard.html          # live incident dashboard (vanilla JS, no build step)
├── data/
│   ├── runbooks.yaml             # known alert patterns → remediation actions
│   └── service_k8s_map.yaml      # service name → namespace/deployment/labels
├── custom-prometheus-rules.yaml   # hand-written PrometheusRule, not from the default stack
├── rbac-topology-reader.yaml      # read-only RBAC for dynamic topology discovery
├── k8s/                           # manifests managed via ArgoCD (GitOps)
│   ├── k8s-deploy.yaml            # app Deployment + Service
│   └── postgres-deploy.yaml       # Postgres Deployment + Secret
├── argocd-application.yaml        # ArgoCD Application pointing at k8s/
├── tests/test_correlator.py      # correlation logic unit tests
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env                          # SLACK_WEBHOOK_URL (not committed — see below)
```

---

## Quickstart (local):-

```bash
git clone https://github.com/<your-username>/alert-intelligence.git
cd alert-intelligence

python -m venv venv
source venv/bin/activate        # Windows Git Bash: source venv/Scripts/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open interactive API docs: **http://localhost:8000/docs**
Open the live dashboard: **http://localhost:8000/dashboard**

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

## Live dashboard:-

`GET /dashboard` serves a small, dependency-free HTML page that polls
`GET /api/incidents` every 4 seconds and renders every incident with a
color-coded confidence bar, severity badge, and remediation status —
no separate frontend build, no framework, just one static file served by
FastAPI.

Useful when demoing the project live: alerts you trigger (or real cluster
alerts) show up within seconds without needing to read raw JSON or logs.

---

## Slack notifications:-

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
to that Slack channel, with full context (deploy correlation, confidence
score, suggested or applied action).

---

## Kubernetes auto-remediation:-

When an incident's confidence scores clears the automation threshold **and**
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
   incident (send the same alert a few times, or submit feedback to raise
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

## Custom Prometheus alerting rule's

`custom-prometheus-rules.yaml` is a hand-written `PrometheusRule` — not one
of the default rules that ship with `kube-prometheus-stack` — proving the
whole alerting stack is understood end-to-end, not just consumed.

It defines two rules:
- `DemoCustomRuleFiring` — an always-true condition (`vector(1) > 0`) that
  fires within ~30 seconds, useful for proving the full path (Prometheus →
  Alertmanager → this app → Slack → dashboard) works without waiting on a
  real threshold
- `AlertIntelligenceServiceDown` — a realistic rule that fires if the app
  itself becomes unreachable (`up{job="alert-intelligence"} == 0`) for
  over a minute

Apply it to a cluster running `kube-prometheus-stack`:
```bash
kubectl apply -f custom-prometheus-rules.yaml
kubectl get prometheusrules -n monitoring
```
The `release: monitoring` label in the file must match your Helm release
name so the Prometheus Operator auto-discovers it.

---

## CI/CD pipeline

`.github/workflows/ci.yml` runs on every push and pull request to `main`:

1. **`test`** — installs dependencies and runs the `pytest` suite
2. **`docker-build`** — only runs if tests pass; builds the Docker image,
   and on a push to `main`, pushes it to Docker Hub tagged both `latest`
   and with the commit SHA

To enable the Docker Hub push in your own fork, add two repository secrets
under **Settings → Secrets and variables → Actions**:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN` (a Docker Hub access token, not your password)

Once set up, anyone can run the project without building it themselves:
```bash
docker pull <your-dockerhub-username>/alert-intelligence:latest
docker run -p 8000:8000 <your-dockerhub-username>/alert-intelligence:latest
```

---

## Postgres and multi-instance deployments

By default this runs on SQLite (`DATABASE_URL` unset) - zero setup, great
for local development. But SQLite is a single file: two app instances
writing to it at once isn't safe and doesn't scale.

The storage layer (`app/storage/db.py`) is built on SQLAlchemy Core, so
the exact same code works against Postgres too - only `DATABASE_URL`
changes, nothing else. This has been tested against a real running
Postgres instance, not just checked for SQL-dialect compatibility.

**To run with Postgres (e.g. in Kubernetes):**

1. Deploy Postgres (see `postgres-deploy.yaml` for a ready-to-use example
   with a Secret for credentials)
2. Set `DATABASE_URL` on the app deployment:
   ```yaml
   env:
     - name: DATABASE_URL
       value: "postgresql+psycopg2://user:password@postgres-host:5432/dbname"
   ```
3. Scale to multiple replicas safely - `k8s-deploy.yaml` runs 2 replicas by
   default, both pointing at the same Postgres instance. Kubernetes
   load-balances requests between them; every replica sees the same
   incident data, since it's shared in Postgres instead of split across
   separate SQLite files.

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

**3. Deploy Postgres, then the app**
```bash
kubectl apply -f postgres-deploy.yaml
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
in, get correlated, enriched, scored, and posted to Slack — live. View them
visually via the dashboard with:
```bash
kubectl port-forward -n monitoring svc/alert-intelligence 8080:8000
```
then opening `http://localhost:8080/dashboard`.

---

## Environment and version-aware correlation

Correlation and deploy-matching are scoped by **(service, environment)**,
not service name alone. A `checkout-api` alert in `staging` will never
merge into a `checkout-api` incident in `prod`, and deploy correlation
only credits a deploy to an incident if it happened in the *same*
environment - so the notification can say exactly which release is
implicated, not just "something deployed recently".

The environment comes from the alert's `env` label (defaults to `prod`
if absent). This came directly from a LinkedIn comment on this project -
a founder building alerting infra pointed out that real systems key
deploy correlation off a `(service, env, version)` triple rather than
service name alone; this is that idea applied here.

```bash
# These stay as two separate incidents instead of merging:
curl -X POST http://localhost:8000/webhook/generic -d '{"service":"checkout-api","alertname":"HighErrorRate","labels":{"env":"prod"}, ...}'
curl -X POST http://localhost:8000/webhook/generic -d '{"service":"checkout-api","alertname":"HighErrorRate","labels":{"env":"staging"}, ...}'
```

---

## Dynamic Kubernetes topology

Service dependency mapping used to be a hardcoded Python dictionary. Now
it's read live from Kubernetes: annotate any Service with which upstream
service it depends on, and the correlator picks it up automatically - no
code change or redeploy required.

```bash
kubectl annotate service payments-service -n monitoring \
  alert-intelligence.io/upstream=checkout-api --overwrite
```

How it works (see `app/core/k8s_topology.py`):
- Uses the Kubernetes Python client (in-cluster config, scoped via RBAC -
  see `rbac-topology-reader.yaml` - to read-only access on Services in one
  namespace)
- Caches the result for 60 seconds so correlation doesn't hit the
  Kubernetes API on every single alert
- Falls back to a small static map if the cluster is unreachable, so the
  app - and its unit tests - keep working without a live cluster

**Required RBAC** (grants read-only access to Service objects, nothing else):
```bash
kubectl apply -f rbac-topology-reader.yaml
```

---

## Key design decisions

- **SQLite by default, Postgres for production** — both work through the
  same SQLAlchemy-based storage layer; only `DATABASE_URL` changes.
  Verified against a real Postgres instance, and safe for multiple app
  replicas sharing one database
- **Rule-based, auditable scorer** — not a black-box ML model. On-call
  engineers can see exactly *why* an incident scored the way it did, which
  is what actually earns trust in an alerting system
- **Remediation is opt-in per action** — an action only auto-runs if it's
  explicitly marked `safe_to_automate: true` in `runbooks.yaml` **and**
  confidence clears the automation threshold. Nothing destructive runs
  silently, and real Kubernetes actions stay in dry-run mode until
  explicitly enabled
- **Topology is discovered, not hardcoded** — read live from Kubernetes
  Service annotations, scoped by RBAC to read-only access, with a static
  fallback so the apps never depends on the cluster being reachable
- **Secrets stay out of git** — the Slack webhook URL and API key live in a
  local `.env` file (loaded via `python-dotenv`), excluded via
  `.gitignore`; Docker Hub and Postgres credentials live in GitHub Actions
  secrets / Kubernetes Secrets, never in code
- **Write endpoints are authenticated, read endpoints aren't** — webhook
  ingestion and feedback submission require an API key (checked via
  `X-API-Key` or `Authorization: Bearer`); the dashboard and incident-lookup
  endpoints stay open since they're for internal viewing, not external
  systems pushing data in
- **Dashboard has zero build step** — plain HTML/CSS/JS served directly by
  FastAPI, so there's no separate frontend toolchain to maintain
- **Everything is swappable** — ingestion adapters, the notifier, and
  storages are thin layers so you can plug in PagerDuty or Datadog APIs
  without touching the core pipeline

---

## API authentication

Webhook and feedback endpoints (`/webhook/generic`, `/webhook/prometheus`,
`/incidents/{id}/feedback`) require an API key. Read-only/internal
endpoints (`/dashboard`, `/api/incidents`, `/docs`, `GET /incidents/{id}`)
stay open, since they're for viewing during a demo, not for external
systems pushing data in.

**Setup:**

1. Generate a random key (don't hand-write one - it needs to be
   unguessable to actually adds security):
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Add it to `.env`:
   ```bash
   echo "API_KEY=<paste the generated key>" >> .env
   ```
3. Restart the app. Protected endpoints now requires the key, sent either way:
   ```bash
   curl -X POST http://localhost:8000/webhook/generic \
     -H "X-API-Key: <your key>" \
     -H "Content-Type: application/json" -d '{ ... }'
   ```
   or via `Authorization: Bearer <your key>` (this is what Alertmanager's
   `http_config.authorization` sends, so both real Alertmanager and manual
   `curl`/Postman testing work without extra wrangling).

**If `API_KEY` is unset** (e.g. a fresh clone with no `.env` configured
yet), authentication is skipped entirely and a warning is logged - so the
app still runs out of the box for local development, but this should never
be left unset anywhere beyond that.

See `.env.example` for the full list of environment variables this app reads.

---

## Self-observability (/metrics)

This app is itself something worth monitoring - `GET /metrics` exposes
standard Prometheus exposition formats, so the same Prometheus instance
watching your services can also watch this alerting layer.

```bash
curl http://localhost:8000/metrics
```

Metrics exposed (see `app/metrics.py`):

| Metric | What it shows |
|---|---|
| `alert_intelligence_alerts_ingested_total{source}` | Every raw alert received, by sources |
| `alert_intelligence_incidents_created_total` | Distinct incidents opened (not merges) - the gap between this and alerts ingested **is** the noise reduction this project provides |
| `alert_intelligence_remediation_actions_total{action,mode}` | Every remediation action taken, tagged `dry_run` or `auto` |
| `alert_intelligence_confidence_score` | Histogram of confidence scores across all incidents |

No auth on this endpoint - Prometheus needs to scrape it directly, and
it's read-only, not a way to push data in (same reasoning as the dashboard
staying open).

---

## GitOps deployment with ArgoCD

Insteads of manually running `kubectl apply` for every change, ArgoCD
continuously watches this repo's `k8s/` folder and keeps the cluster in
sync with whatever is committed to `main` - Git becomes the single source
of truth for what should be running.

`argocd-application.yaml` defines the ArgoCD `Application` resource:
- **Source:** this repo, `k8s/` folder, `main` branch
- **Destination:** the `monitoring` namespace
- **Sync policy:** automated, with `selfHeal` (reverts manual `kubectl`
  changes back to match Git) and `prune` (removes resources deleted from Git)

**Setup:**
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f argocd-application.yaml
```

**Verified end-to-end:** changed `replicas: 2` to `replicas: 3` in
`k8s/k8s-deploy.yaml` directly on GitHub (no local `kubectl` command at
all), and ArgoCD picked up the changes and scaled the deployment on its own
within its sync interval - confirmed via `kubectl get pods -n monitoring`
showing a third replica appear with zero manual intervention.

---

## Roadmap / ideas for contribution

- [ ] Datadog and CloudWatch ingestion adapters
- [ ] PagerDuty notifier integration
- [ ] HPA-aware scaling instead of flats replica increments
- [ ] Persistent volume for Postgres (current manifest uses emptyDir, fine for demos, not for real data durability)

---

## License

MIT — use it, fork it, break it, learn from it.
