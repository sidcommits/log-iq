# LogIQ M0 — Project Scaffold Design

**Date:** 2026-05-05
**Milestone:** M0 — Setup
**Status:** Approved
**Scope:** Project scaffold, Docker Compose (full local stack), fake log generator

---

## 1. Objective

Stand up a runnable local environment with a single `docker compose up`. On first boot, the fake log generator starts pushing realistic microservice logs into Loki immediately, Grafana is pre-wired with Loki and Prometheus datasources, and the LogIQ API stub responds on `/api/health`. No manual configuration required.

---

## 2. Project Scaffold

Directory structure follows the PRD exactly. Two additions: `infra/` for service configuration files, `tools/log_generator/` for the fake generator (isolated from application code).

```
logiq/
├── adapters/              # BaseSourceAdapter ABC + LokiAdapter (M1)
│   └── __init__.py
├── models/                # Pydantic schemas (M1)
│   └── __init__.py
├── sync/                  # Sync engine (M2)
│   └── __init__.py
├── ingestion/             # Embed → store pipeline (M2)
│   └── __init__.py
├── intelligence/          # search, analyze, anomaly (M3-M5)
│   └── __init__.py
├── api/
│   ├── __init__.py
│   ├── main.py            # FastAPI app — grows each milestone
│   └── routes/
│       ├── __init__.py
│       └── health.py      # /api/health (M0)
├── db/
│   ├── __init__.py
│   └── migrations/        # SQL schema files (M2)
├── tools/
│   └── log_generator/
│       ├── Dockerfile
│       ├── generator.py
│       └── requirements.txt
├── infra/
│   ├── loki/
│   │   └── loki-config.yaml
│   ├── prometheus/
│   │   └── prometheus.yaml
│   └── grafana/
│       ├── datasources/
│       │   └── datasources.yaml
│       └── dashboards/
│           └── logiq-overview.json
├── frontend/              # React app (M7)
├── config.yaml            # Full config skeleton
├── docker-compose.yml
├── Dockerfile             # LogIQ API image
├── requirements.txt
├── .env.example           # Template — committed
├── .env                   # Actual secrets — gitignored
└── README.md
```

---

## 3. Docker Compose Services

All seven services start with `docker compose up`. No manual steps.

| Service | Image | Role |
|---|---|---|
| `postgres` | `postgres:15` | Raw log storage, task queue, audit trail |
| `qdrant` | `qdrant/qdrant` | Vector DB for embeddings |
| `loki` | `grafana/loki:2.9.0` | Log storage read by LokiAdapter |
| `prometheus` | `prom/prometheus` | Scrapes `/metrics` from LogIQ API |
| `grafana` | `grafana/grafana:10.2.0` | Pre-wired dashboards: Loki + Prometheus |
| `logiq-api` | built from `Dockerfile` | FastAPI stub — `/api/health` + `/metrics` |
| `log-generator` | built from `tools/log_generator/Dockerfile` | Custom Python generator → Loki |

**Startup order:**
1. `postgres`, `qdrant`, `loki` — no dependencies
2. `logiq-api` — waits on `postgres`, `qdrant`, `loki` healthchecks
3. `log-generator` — waits on `loki` healthcheck
4. `grafana` — waits on `prometheus`

All state is stored in named Docker volumes (persist across restarts). Secrets come from `.env`.

---

## 4. Fake Log Generator

A standalone Python service (`tools/log_generator/generator.py`) that runs continuously, pushing structured JSON logs to Loki's HTTP push API at `http://loki:3100/loki/api/v1/push`.

### 4.1 Traffic Rate

- Baseline (normal): ~2 logs/second across all 4 services combined
- During failure bursts: ~10 logs/second on affected services

### 4.2 Simulated Services

| Service | Baseline log mix |
|---|---|
| `auth-service` | INFO (login/logout/token validation), occasional WARN |
| `api-gateway` | INFO (routing, rate limiting) |
| `payments-service` | INFO/WARN (transaction processing) |
| `user-service` | INFO/DEBUG (profile reads/writes) |

### 4.3 Scripted Failure Cycles

Failure cycles loop continuously from generator startup:

| Failure | Affected services | Every | Duration | Log pattern |
|---|---|---|---|---|
| DB pool exhaustion | `auth-service` | 10 min | 60s | `ERROR: connection pool exhausted after N retries` |
| Auth spike / brute force | `auth-service`, `api-gateway` | 20 min | 90s | `ERROR: 401 Unauthorized`, `ERROR: rate limit exceeded` |
| Payment timeout | `payments-service` | 15 min | 45s | `ERROR: upstream timeout after 30s`, `ERROR: transaction rolled back` |
| User service degradation | `user-service` | 25 min | 120s | `WARN: high latency 2500ms` escalating to `ERROR: DB query failed` |

### 4.4 Log Format

Every log event is structured JSON matching the `LogEvent` schema the LokiAdapter will normalise in M1:

```json
{
  "timestamp": "2026-05-05T10:23:41.123Z",
  "severity": "ERROR",
  "service": "auth-service",
  "environment": "production",
  "trace_id": "a1b2c3d4e5f6",
  "span_id": "f1e2d3c4",
  "message": "connection pool exhausted after 3 retries",
  "metadata": {
    "host": "auth-service-1",
    "region": "us-east-1",
    "db_host": "postgres:5432",
    "pool_size": 10,
    "active_connections": 10
  }
}
```

**Trace ID propagation:** when `api-gateway` routes a request that causes a downstream failure, it shares the same `trace_id` with `auth-service`. This makes trace correlation functional from day one.

### 4.5 Loki Push

Logs are batched (up to 50 per push) and sent as:

```
POST http://loki:3100/loki/api/v1/push
Content-Type: application/json

{
  "streams": [
    {
      "stream": {
        "service": "auth-service",
        "environment": "production",
        "severity": "ERROR"
      },
      "values": [
        ["<unix_timestamp_ns>", "<json_log_string>"]
      ]
    }
  ]
}
```

Labels `{service, environment, severity}` match exactly what LokiAdapter will use to filter and normalise in M1 — no schema migration needed when the real adapter lands.

---

## 5. FastAPI Stub (M0)

`api/main.py` creates the real FastAPI instance that every subsequent milestone adds routes to.

**M0 exposes:**
- `GET /api/health` — returns 200 with placeholder dependency statuses
- `GET /metrics` — Prometheus metrics via `prometheus-fastapi-instrumentator`

**Middleware (wired once, inherited by all future routes):**
- Request ID injection: UUID generated per request, attached to response as `X-Request-ID`
- CORS: open for local dev, lockable via `config.yaml`

**Health response shape (M0):**
```json
{
  "status": "healthy",
  "dependencies": {
    "loki":       { "status": "not_configured" },
    "qdrant":     { "status": "not_configured" },
    "postgresql": { "status": "not_configured" },
    "openai":     { "status": "not_configured" },
    "claude":     { "status": "not_configured" }
  },
  "version": "0.1.0"
}
```

M2 replaces `"not_configured"` with real health checks.

---

## 6. config.yaml Skeleton

Full skeleton committed in M0. Every milestone fills in values — the shape never changes.

```yaml
sources:
  - name: loki
    type: loki
    url: http://loki:3100
    mode: stream            # poll | stream
    poll_interval_seconds: 30

database:
  url: ${POSTGRES_URL}

qdrant:
  host: qdrant
  port: 6333
  collection: logiq_logs

embeddings:
  provider: openai
  model: text-embedding-3-small
  api_key: ${OPENAI_API_KEY}

llm:
  provider: claude          # claude | openai | openrouter
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}
  timeout_seconds: 30
  # OpenRouter config (used when provider: openrouter)
  openrouter:
    api_key: ${OPENROUTER_API_KEY}
    base_url: https://openrouter.ai/api/v1
    model: anthropic/claude-sonnet-4             # any OpenRouter model slug

ingestion:
  batch_size: 100
  max_chunk_tokens: 512

anomaly:
  enabled: true
  knn_k: 10
  threshold: 0.72
  per_service_overrides: {}

auth:
  enabled: false            # set true in production
  api_key: ${LOGIQ_API_KEY}

integrations:
  github:
    enabled: false          # v2.0 placeholder
  slack:
    enabled: false          # v1.1 placeholder

agents:
  enabled: false            # v2.0 placeholder
  require_human_approval: true
  confidence_threshold: 0.70
  max_files_per_fix: 3
```

Sensitive values are always injected via env vars. `.env.example` is committed with placeholder values; `.env` is gitignored.

**LLM provider routing:** three providers supported — `claude` (Anthropic SDK), `openai` (OpenAI SDK), `openrouter` (OpenAI-compatible SDK, base URL overridden to `https://openrouter.ai/api/v1`). The intelligence layer uses a single provider interface; switching providers requires only a config change, no code changes.

---

## 7. Definition of Done

M0 is complete when:

- [ ] `docker compose up` starts all 7 services with no manual steps
- [ ] `log-generator` is pushing logs to Loki within 10 seconds of startup
- [ ] Grafana is reachable at `http://localhost:3000` with Loki and Prometheus datasources pre-configured
- [ ] `GET http://localhost:8000/api/health` returns 200
- [ ] `GET http://localhost:8000/metrics` returns Prometheus metrics
- [ ] All failure cycles are scripted and confirmed visible in Grafana Loki explorer
- [ ] `.env.example` documents all required env vars
- [ ] README has a "Quick Start" section: clone → copy `.env.example` → `docker compose up`
