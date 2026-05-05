# LogIQ

AI-powered log intelligence layer — semantic search, root cause analysis, and anomaly detection on top of your existing logging stack.

## Quick Start

**Requirements:** Docker + Docker Compose

```bash
git clone <repo-url> logiq
cd logiq
cp .env.example .env
docker compose up
```

That's it. Open:

| Service | URL | Credentials |
|---|---|---|
| LogIQ API | http://localhost:8000/api/health | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Loki | http://localhost:3100/ready | — |

The log generator starts automatically and produces ~2 realistic microservice logs/second from `auth-service`, `api-gateway`, `payments-service`, and `user-service`, with scripted failure cycles every 10-25 minutes.

## Development

```bash
pip install -r requirements.txt
pytest
```

## Architecture

See [`docs/LogIQ_PRD.md`](docs/LogIQ_PRD.md) for the full product specification.

LogIQ is a layered system:

```
Log Sources (Loki) → Source Adapters → Sync Engine → Ingestion Pipeline
    → Qdrant (vectors) + PostgreSQL (raw logs)
    → Intelligence Layer (search, RCA, anomaly detection)
    → FastAPI REST API + React UI
```
