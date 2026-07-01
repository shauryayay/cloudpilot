# cloudpilot

A self-service database provisioning API built on GitOps principles. One API call provisions a managed database cluster — Postgres, MySQL, MongoDB, or Redis — with full audit trail, deterministic credentials, and environment-aware defaults.

## What it does

You send a JSON payload to a single endpoint. Behind the scenes:

1. **Pydantic** validates the request (engine, environment, tier, users)
2. A **Celery** task is queued — the API returns a tracking ID immediately
3. The worker renders declarative config files (`Chart.yaml` + `values.yaml`)
4. Files are committed to a **Git repo** (the GitOps source of truth)
5. Cluster creation is simulated (stands in for a cloud provider)
6. Credentials are derived **deterministically via SHA-256** — no passwords in Git, ever

Poll `/status` to watch it progress through: `accepted → rendering → committed → creating → ready`.

## Architecture

```
                   ┌──────────────┐
  POST /provision  │   FastAPI    │──── tracking_id ──→ caller
                   │  (Pydantic)  │
                   └──────┬───────┘
                          │ queue
                   ┌──────▼───────┐
                   │    Celery    │
                   │   (Redis)    │
                   └──────┬───────┘
                          │
               ┌──────────┼──────────┐
               ▼          ▼          ▼
         ┌──────────┐ ┌────────┐ ┌──────────┐
         │  Config  │ │  Git   │ │  Secret  │
         │ Renderer │ │ Commit │ │Derivation│
         └──────────┘ └────────┘ └──────────┘
```

## Key design patterns

| Pattern | How it works |
|---------|-------------|
| **Async provisioning** | API returns a tracking ID immediately; a Celery worker drives the pipeline in the background |
| **GitOps source of truth** | Every provision generates config and commits it to Git — auditable, rollback-ready |
| **Deterministic secrets** | Passwords are derived from a seed via SHA-256, never stored in Git or config files |
| **Environment-aware defaults** | dev gets starter instances with 1-day backups; prod enforces deletion protection and multi-replica |
| **Infrastructure abstraction** | Users pick tier aliases (starter/standard/performance); the system resolves to concrete instance types |
| **Unified multi-engine API** | Postgres, MySQL, MongoDB, Redis — same endpoints, different payloads |

## API

### Provision a cluster

```bash
curl -X POST http://localhost:8000/api/v1/clusters/provision \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "data-team",
    "cluster_name": "analytics-db",
    "environment": "dev",
    "engine": "postgres",
    "tier": "starter",
    "database": "analytics",
    "users": [
      {"name": "app_rw", "privileges": "readWrite"},
      {"name": "app_ro", "privileges": "readOnly"}
    ]
  }'
```

Response (HTTP 202):
```json
{
  "tracking_id": "a1b2c3d4e5f6",
  "status": "accepted",
  "message": "Provisioning postgres cluster 'analytics-db' for 'data-team' (dev). Poll /api/v1/clusters/a1b2c3d4e5f6/status for progress."
}
```

### Poll status

```bash
curl http://localhost:8000/api/v1/clusters/a1b2c3d4e5f6/status
```

### Get credentials (only after status = ready)

```bash
curl http://localhost:8000/api/v1/clusters/a1b2c3d4e5f6/credentials
```

### List all clusters

```bash
curl http://localhost:8000/api/v1/clusters
```

### Delete (blocked if deletion_protection is on)

```bash
curl -X DELETE http://localhost:8000/api/v1/clusters/a1b2c3d4e5f6
```

## Run it

### With Docker Compose (recommended)

```bash
docker compose up --build
```

This starts three containers:
- **redis** — message broker + state store
- **api** — FastAPI on port 8000
- **worker** — Celery worker processing provision tasks

### Without Docker

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: API
pip install -r requirements.txt
uvicorn app.main:app --reload

# Terminal 3: Worker
celery -A app.worker worker --loglevel=info
```

API docs at [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI).

## Tech stack

- **Python 3.12** / **FastAPI** / **Pydantic v2** — request validation, API framework
- **Celery** + **Redis** — async task queue and state persistence
- **GitPython** — programmatic Git commits (GitOps automation)
- **PyYAML** — declarative config generation
- **Docker Compose** — local orchestration (3 services)
- **SHA-256** — deterministic password derivation (no secrets in Git)

## Project structure

```
cloudpilot/
├── app/
│   ├── main.py        FastAPI endpoints
│   ├── models.py      Pydantic schemas + validation rules
│   ├── config.py      Settings via pydantic-settings
│   ├── secrets.py     Deterministic credential derivation
│   ├── generator.py   Config file generation
│   ├── gitops.py      Git commit automation
│   ├── store.py       Redis-backed cluster state
│   ├── tasks.py       Celery provisioning pipeline
│   └── worker.py      Celery configuration
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```
