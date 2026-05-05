# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LogIQ is an AI-powered log intelligence layer that sits on top of existing logging infrastructure (Loki, ELK, Datadog). It adds semantic search, LLM-driven root cause analysis (RCA), anomaly detection, and actionable task generation — without replacing existing tools.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python 3.12 (async-first) |
| Vector DB | Qdrant |
| Relational DB | PostgreSQL 15 |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | Claude `claude-sonnet-4-20250514` (primary), OpenAI (configurable) |
| Frontend | React + TypeScript + Tailwind (Vite) |
| HTTP Client | httpx (async) |
| WebSocket | websockets library (Loki real-time streaming) |
| Scheduling | APScheduler (poll mode) |
| Containerisation | Docker + Docker Compose |
| Observability | Prometheus + Grafana |

## Planned Project Structure

```
logiq/
├── adapters/        # BaseSourceAdapter ABC + LokiAdapter + future adapters
├── models/          # Pydantic schemas: LogEvent, RootCauseAnalysis, ActionableTask, AnomalyResult
├── sync/            # Sync engine (poll + stream modes, cursor tracking, dedup)
├── ingestion/       # Embed → store → anomaly score pipeline
├── intelligence/    # search.py, analyze.py, anomaly.py
├── api/
│   ├── main.py      # FastAPI app + middleware
│   └── routes/      # search, analyze, anomalies, tasks, sources, health
├── db/
│   ├── postgres.py  # PostgreSQL connection + queries
│   ├── qdrant.py    # Qdrant client + helpers
│   └── migrations/  # SQL schema files
├── frontend/        # React + TypeScript (Vite)
├── config.yaml      # All configuration (sources, thresholds, LLM provider, integrations)
└── docker-compose.yml
```

## Architecture: Key Layers

**Source Adapter Layer** — `BaseSourceAdapter` ABC defines exactly 5 methods: `fetch_logs()`, `stream_logs()`, `health_check()`, `get_source_name()`, `normalise()`. Adding a new adapter requires implementing these 4 methods + 1 config entry in `config.yaml` — nothing else in the codebase changes.

**Normalisation** — every source outputs a standard `LogEvent` Pydantic schema with: `id`, `timestamp`, `severity` (enum: ERROR/WARN/INFO/DEBUG/TRACE/UNKNOWN), `service`, `environment`, `trace_id`, `span_id`, `message`, `metadata`, `raw`, `source`.

**Sync Engine** — runs as a background asyncio task. Two modes per source: poll (APScheduler, default 30s) and stream (WebSocket). Tracks a cursor in the `sync_cursors` PostgreSQL table to survive restarts without re-ingestion. Implements exponential backoff on source failure.

**Ingestion Pipeline** — batches of ≤100 events: chunk long messages (>512 tokens) → embed via OpenAI → store vectors + metadata in Qdrant → store full `LogEvent` in PostgreSQL → anomaly score every event.

**Intelligence Layer (FastAPI)** — semantic search over Qdrant with optional metadata pre-filters; PostgreSQL fallback if top similarity < 0.75 threshold. LLM RCA via Claude claude-sonnet-4-20250514, degrades gracefully on timeout (30s). Anomaly detection: KNN (K=10) in Qdrant, flag if avg similarity < 0.72.

**Task Queue** — RCA generates `ActionableTask` records in PostgreSQL. Status flow: `pending → approved → in_progress → resolved` or `dismissed`. Human approval is a hard requirement — never skippable, enforced at DB level. Task queue is the v2.0 agent interface contract.

**Audit Trail** — append-only `audit_log` table. Records: search_executed, rca_created, task_created/approved/dismissed, anomaly_detected/reviewed. Never updated or deleted.

## API Endpoints

```
POST   /api/search              # Semantic search
POST   /api/analyze             # LLM root cause analysis
GET    /api/correlate/{trace_id} # Full trace analysis across services
GET    /api/anomalies           # Anomaly feed (filterable)
POST   /api/anomalies/{id}/review
GET    /api/tasks               # Task queue (filterable)
POST   /api/tasks/{id}/approve
POST   /api/tasks/{id}/dismiss
GET    /api/sources
GET    /api/health
GET    /metrics                 # Prometheus
GET    /api/agents              # 501 stub (v2.0)
POST   /api/agents/trigger      # 501 stub (v2.0)
```

All error responses: `{ "error": str, "code": str, "request_id": uuid, "timestamp": ISO8601 }`.
Auth via `X-API-Key` header — off by default for local dev, enabled via `config.yaml`.

## PostgreSQL Schema Key Points

- `logs` table: indexes on `timestamp DESC`, `service`, `severity`, `trace_id`
- `anomalies` table: FK to `logs(id)`, tracks `reviewed` state
- `rca` table: stores full analysis results
- `tasks` table: FK to `rca(id)` and `logs(id)`, status enum, `agent_id` nullable (v2)
- `audit_log` table: append-only, `DEFAULT gen_random_uuid()` PK
- `sync_cursors` table: PK is `source_name`, tracks `last_synced_at`

## Configuration

All configuration in `config.yaml`. Sensitive values (API keys, DB passwords, LLM tokens) must be injected via environment variables — never hardcoded. LLM provider is configurable (Claude default, OpenAI supported).

## Frontend Design

- Dark theme (Grafana/Linear aesthetic)
- Four pages: Search (default), Anomalies, Tasks, Health
- Severity badge colours: ERROR=red, WARN=amber, INFO=blue, DEBUG=grey
- Desktop-first, responsive

## Non-Functional Targets

- Semantic search p95 latency: <500ms (up to 1M log entries)
- RCA response time: <10s
- Ingestion throughput: 1,000 events/second in stream mode
- All external API calls: 30s timeout, 3 retries with exponential backoff
- Full stack starts with `docker compose up` — fake log generator included for immediate data

## v2.0 Agent Safety Rules (design constraint, not built in v1.0)

These rules must be reflected in the DB schema and task queue design now:
- No agent action begins without `status = approved` in DB
- Agents may only open PRs, never merge them
- No agent modifies infrastructure or deletes code
- Every agent action written to `audit_log` before execution
