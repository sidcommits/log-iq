# LogIQ — Product Requirements Document

**Version:** 1.0  
**Author:** Siddhant Deshpande  
**Status:** Draft  
**Last Updated:** May 2026  

---

## Table of Contents

1. [Overview](#1-overview)
2. [Target Users](#2-target-users)
3. [Core Features](#3-core-features)
4. [Functional Requirements](#4-functional-requirements)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [Technical Architecture](#6-technical-architecture)
7. [Data Models](#7-data-models)
8. [API Specification](#8-api-specification)
9. [Frontend Requirements](#9-frontend-requirements)
10. [Agentic DevOps — Future Design](#10-agentic-devops--future-design)
11. [Milestones](#11-milestones)
12. [Roadmap](#12-roadmap)
13. [Open Questions](#13-open-questions)

---

## 1. Overview

### 1.1 Problem Statement

Modern engineering teams already have logging infrastructure — Loki, Elasticsearch, Datadog — but these tools only offer keyword-based search and threshold-based alerting. When something breaks at 3am, engineers spend hours manually grepping through thousands of log lines trying to find root cause.

Current tools give you:
- ✅ Log storage and retention
- ✅ Basic keyword filtering
- ✅ Threshold-based alerting
- ✅ Dashboards and graphs

But they do not give you:
- ❌ Natural language querying ("why did auth fail last night?")
- ❌ Semantic search that understands context, not just keywords
- ❌ Intelligent root cause analysis across services
- ❌ Anomaly detection based on meaning, not just metric thresholds
- ❌ Automatic correlation of related errors across distributed services
- ❌ Machine-actionable diagnosis that future agents can act upon

### 1.2 What is LogIQ

LogIQ is an AI-powered log intelligence layer that sits **on top of** existing logging infrastructure. It adds semantic search, LLM-driven root cause analysis, anomaly detection, and actionable task generation — without requiring any changes to existing infrastructure.

LogIQ is **not** a replacement for Loki, Elasticsearch, or Datadog. It is the intelligence layer those tools are missing.

> **One line:** *Ask your logs anything, in plain English.*

### 1.3 Vision

LogIQ's long-term vision is to become an **Agentic DevOps platform** — where not only are incidents detected and diagnosed automatically, but AI agents are spun up to find the root cause in the codebase, write a fix, open a pull request, run tests, and notify the engineer for final approval. All of this triggered by a log anomaly.

**v1.0** builds the intelligence foundation.  
**v2.0** adds the agentic layer on top.

### 1.4 Goals

- Enable engineers to query logs in natural language with no LogQL or KQL required
- Automatically surface root cause when incidents occur
- Detect anomalies before they escalate into incidents
- Integrate with any existing logging stack with zero friction
- Generate machine-actionable tasks that future agents can consume
- Be fully deployable in under 5 minutes via Docker Compose
- Be extensible — adding a new log source requires implementing 3 methods

### 1.5 Non-Goals

- LogIQ is **not** a log collector or ingestion pipeline
- LogIQ is **not** a replacement for Loki, ELK, Datadog, or Splunk
- LogIQ does **not** handle log retention, archival, or compliance
- LogIQ does **not** replace alerting tools like PagerDuty or OpsGenie
- LogIQ does **not** auto-execute agent actions without human approval (by design)

---

## 2. Target Users

### 2.1 Primary User — Backend / DevOps / SRE Engineer

**Profile:**
- Works on distributed systems with 3+ microservices
- Already has Loki, ELK, or a cloud logging stack set up
- Spends significant time debugging production incidents
- Comfortable with Docker, REST APIs, and developer tooling
- Frustrated by the gap between "alert fires" and "root cause found"

**Pain Points:**
- "I know something is broken but I don't know which service caused it"
- "Searching logs with keywords misses context — I need to know intent"
- "I get flooded with 500 alerts that are all caused by one underlying problem"
- "Writing LogQL or KQL queries is slow and I keep forgetting the syntax"
- "Root cause analysis takes hours of manual log correlation across services"
- "I can't tell the difference between a known error pattern and a new anomaly"

**Goals:**
- Reduce MTTR (Mean Time To Resolution) from hours to minutes
- Spend less time in log dashboards and more time writing code
- Get proactively notified of anomalies before users complain

### 2.2 Secondary User — Engineering Manager / Tech Lead

**Profile:**
- Wants visibility into system health without diving into raw logs
- Needs summarized incident reports for stakeholders
- Cares about engineering KPIs: MTTR, incident frequency, error rates

**Pain Points:**
- "I can't get a clear summary of what happened during an incident"
- "I don't know which services are most error-prone"
- "Post-mortems take too long because root cause is unclear"

**Goals:**
- Dashboard view of system health across all services
- Automated incident summaries
- Trend analysis: which services are degrading over time

### 2.3 Future User — AI Agent (v2.0)

In v2.0, LogIQ's own agent layer becomes a consumer of the intelligence it generates. The agent reads actionable tasks from the task queue and acts on them — finding relevant code, opening issues, writing fixes, running tests.

This user is designed for but not built in v1.0.

---

## 3. Core Features

### 3.1 Feature Priority Matrix

| Priority | Feature | Description | Version |
|---|---|---|---|
| P0 | Loki Source Adapter | Read logs from existing Loki instances | v1.0 |
| P0 | Log Normalisation | Standard LogEvent schema across all sources | v1.0 |
| P0 | Sync Engine | Poll and stream logs from source into LogIQ | v1.0 |
| P0 | Semantic Search | Natural language querying over logs | v1.0 |
| P0 | Root Cause Analysis | LLM-generated diagnosis with actionable tasks | v1.0 |
| P1 | Anomaly Detection | Flag unusual log patterns automatically | v1.0 |
| P1 | Trace Correlation | Group logs by trace ID across services | v1.0 |
| P1 | Task Queue | Store actionable tasks for future agent consumption | v1.0 |
| P1 | Audit Trail | Full log of all LogIQ events and actions | v1.0 |
| P1 | React UI | Clean chat-like search and investigation interface | v1.0 |
| P1 | REST API | Headless usage for integrations | v1.0 |
| P2 | Prometheus Metrics | Expose LogIQ health and usage metrics | v1.0 |
| P2 | Elasticsearch Adapter | Second source integration | v1.1 |
| P2 | Slack Notifications | Alert on anomalies via Slack | v1.1 |
| P3 | Datadog Adapter | Third source integration | v1.2 |
| P3 | CloudWatch Adapter | AWS native log source | v1.2 |
| P3 | Agent Framework | CodeAgent, GitHubAgent, TestAgent | v2.0 |
| P3 | GitHub Integration | Open issues and PRs from task queue | v2.0 |
| P3 | Human Approval Workflow | Approve/dismiss agent actions | v2.0 |

---

## 4. Functional Requirements

### 4.1 Source Adapter System

**FR-001:** LogIQ must define a `BaseSourceAdapter` abstract interface that all log source integrations implement.

**FR-002:** The adapter interface must expose exactly these methods:
```python
async def fetch_logs(
    start: datetime,
    end: datetime,
    filters: dict
) -> list[LogEvent]

async def stream_logs() -> AsyncGenerator[LogEvent, None]

async def health_check() -> bool

def get_source_name() -> str

def normalise(raw_entry: dict) -> LogEvent
```

**FR-003:** LogIQ must ship with a fully functional `LokiAdapter` in v1.0.

**FR-004:** The `LokiAdapter` must use:
- `GET /loki/api/v1/query_range` for historical log fetching
- `GET /loki/api/v1/tail` (WebSocket) for real-time streaming

**FR-005:** Adding a new source adapter must not require changes to any layer above the adapter layer. The core pipeline must be fully source-agnostic.

**FR-006:** Source configuration must be done entirely via `config.yaml` — no code changes required to switch or add sources.

**FR-007:** Multiple source adapters must be able to run concurrently (e.g. Loki + Elasticsearch simultaneously in v1.1+).

---

### 4.2 Log Normalisation

**FR-008:** Every log source must output a standard `LogEvent` schema regardless of source format.

**FR-009:** `LogEvent` must contain these fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | UUID | Yes | Auto-generated unique identifier |
| `timestamp` | datetime | Yes | Event time in ISO8601 |
| `severity` | Enum | Yes | Normalised severity level |
| `service` | str | Yes | Service/application name |
| `environment` | str | No | production, staging, dev |
| `trace_id` | str | No | Distributed trace identifier |
| `span_id` | str | No | Span identifier |
| `message` | str | Yes | Log message content |
| `metadata` | dict | No | Flexible key-value (host, region, etc.) |
| `raw` | str | Yes | Original unparsed log line |
| `source` | str | Yes | Source adapter name (loki, elasticsearch) |

**FR-010:** Severity must be normalised across all sources into a standard enum:
```
ERROR | WARN | INFO | DEBUG | TRACE | UNKNOWN
```

**FR-011:** LogIQ must handle both structured (JSON) and unstructured (plaintext) log formats.

**FR-012:** For unstructured logs, LogIQ must attempt to extract severity, timestamp, and service from common patterns before falling back to defaults.

---

### 4.3 Sync Engine

**FR-013:** LogIQ must support two sync modes, configurable per source:

- **Poll mode:** Call `fetch_logs()` every N seconds (configurable, default 30s)
- **Stream mode:** Maintain a persistent connection via `stream_logs()`, process events as they arrive

**FR-014:** The sync engine must track a cursor (last synced timestamp) per source in PostgreSQL so that on restart it resumes from where it left off without re-ingesting old logs.

**FR-015:** The sync engine must deduplicate logs by `LogEvent.id` before passing to the ingestion pipeline.

**FR-016:** The sync engine must implement exponential backoff retry if the source becomes unreachable. It must not crash — it must log the error, wait, and retry.

**FR-017:** The sync engine must emit a Prometheus metric `logiq_sync_lag_seconds` indicating how far behind real-time each source is.

**FR-018:** The sync engine must be runnable as a background asyncio task, not blocking the API layer.

---

### 4.4 Ingestion Pipeline

**FR-019:** LogIQ must embed log messages using OpenAI `text-embedding-3-small`.

**FR-020:** Messages exceeding 512 tokens must be chunked into smaller overlapping pieces before embedding. Each chunk must retain the parent `LogEvent` metadata.

**FR-021:** Embeddings and full metadata must be stored in Qdrant vector DB with the following payload structure:
```json
{
  "log_event_id": "uuid",
  "timestamp": "ISO8601",
  "severity": "ERROR",
  "service": "auth-service",
  "environment": "production",
  "trace_id": "abc123",
  "message": "...",
  "source": "loki"
}
```

**FR-022:** Raw `LogEvent` must also be stored in PostgreSQL for exact queries, audit trail, and trace correlation.

**FR-023:** Ingestion must be batched — maximum 100 events per batch — to avoid overwhelming the embedding API.

**FR-024:** Ingestion pipeline must return stats after each batch:
```json
{
  "total_received": 150,
  "ingested": 147,
  "duplicates_skipped": 2,
  "errors": 1,
  "duration_ms": 320
}
```

**FR-025:** Anomaly scoring must run automatically as part of the ingestion pipeline for every event.

---

### 4.5 Semantic Search

**FR-026:** Users must be able to search logs using natural language queries with no knowledge of LogQL, KQL, or any query language.

**FR-027:** The search endpoint must support these optional metadata filters:

| Filter | Type | Example |
|---|---|---|
| `service` | string | `"auth-service"` |
| `severity` | enum | `"ERROR"` |
| `environment` | string | `"production"` |
| `start_time` | datetime | `"2026-05-01T02:00:00Z"` |
| `end_time` | datetime | `"2026-05-01T04:00:00Z"` |

**FR-028:** Filters must be applied at the Qdrant query level (not post-filter) for performance.

**FR-029:** Search must return results ranked by semantic similarity score descending.

**FR-030:** If the top result's similarity score is below a configurable threshold (default 0.75), LogIQ must fall back to exact keyword search in PostgreSQL and clearly indicate in the response that fallback was used.

**FR-031:** Each search result must include:
- Full `LogEvent` object
- Similarity score (0.0 — 1.0)
- A short highlighted snippet showing the most relevant portion of the message

**FR-032:** Search must complete in under 500ms for collections up to 1 million log entries (excluding LLM analysis).

---

### 4.6 Root Cause Analysis

**FR-033:** Users must be able to trigger LLM root cause analysis on any set of search results via the `/api/analyze` endpoint.

**FR-034:** Root cause analysis must accept:
- The user's original natural language query
- A list of `log_event_ids` to analyze (from search results)

**FR-035:** Root cause analysis must return a fully structured, machine-actionable response:

```json
{
  "rca_id": "uuid",
  "query": "why did auth service fail at 3am?",
  "root_cause": "Database connection pool exhausted in auth-service due to a spike in concurrent login requests",
  "affected_services": ["auth-service", "user-service"],
  "severity": "critical",
  "suggested_fix": "Increase DB connection pool size from 10 to 50 in auth-service config",
  "confidence": 0.91,
  "related_trace_ids": ["abc123", "def456"],
  "actionable_tasks": [
    {
      "task_id": "uuid",
      "type": "config_change",
      "description": "Increase DB connection pool size in auth-service",
      "target_service": "auth-service",
      "target_file": "src/db/config.py",
      "priority": "high",
      "estimated_effort": "low",
      "status": "pending"
    }
  ],
  "analyzed_log_count": 24,
  "created_at": "ISO8601"
}
```

**FR-036:** The `actionable_tasks` array must be written to the PostgreSQL `tasks` table automatically after every RCA.

**FR-037:** LogIQ must support trace correlation — given a `trace_id`, it must fetch all related logs across all services from PostgreSQL and pass the full request journey to the LLM for analysis.

**FR-038:** LLM calls must degrade gracefully. If the LLM is unavailable or times out (30s), LogIQ must return the search results with a clear error in the analysis field rather than failing the entire request.

**FR-039:** The LLM provider must be configurable via `config.yaml` to support both Claude and OpenAI, with Claude as the default.

---

### 4.7 Anomaly Detection

**FR-040:** LogIQ must automatically score every ingested log event for anomaly likelihood as part of the ingestion pipeline.

**FR-041:** Anomaly scoring algorithm:
1. Embed the incoming log message
2. Search Qdrant for the K nearest neighbours (K=10)
3. Compute average cosine similarity to neighbours
4. If average similarity < configurable threshold (default 0.72), flag as anomalous
5. Anomaly score = 1 - average_similarity (higher = more anomalous)

**FR-042:** Detected anomalies must be written to the PostgreSQL `anomalies` table with:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Anomaly record ID |
| `log_event_id` | UUID | FK to logs table |
| `anomaly_score` | float | 0.0 — 1.0, higher = more anomalous |
| `nearest_neighbours` | jsonb | Top 3 similar known logs for context |
| `detected_at` | datetime | When anomaly was detected |
| `reviewed` | bool | Has a human reviewed this? |
| `reviewed_by` | str | Who reviewed it |
| `reviewed_at` | datetime | When reviewed |

**FR-043:** Users must be able to mark anomalies as reviewed via `POST /api/anomalies/{id}/review`.

**FR-044:** The `/api/anomalies` endpoint must support filtering by: `reviewed`, `service`, `severity`, `min_score`, time range.

**FR-045:** Anomaly threshold must be configurable per service in `config.yaml` to account for services that naturally have more varied log patterns.

---

### 4.8 Task Queue

**FR-046:** Every RCA must generate one or more `ActionableTask` records stored in PostgreSQL.

**FR-047:** The `tasks` table schema:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Task ID |
| `rca_id` | UUID | FK to rca table |
| `log_event_id` | UUID | Triggering log event |
| `type` | Enum | code_fix, config_change, scaling, restart, investigation |
| `description` | str | Human-readable task description |
| `target_service` | str | Which service needs the fix |
| `target_file` | str | Which file (if known) |
| `priority` | Enum | critical, high, medium, low |
| `estimated_effort` | Enum | low, medium, high |
| `status` | Enum | pending, approved, in_progress, resolved, dismissed |
| `created_at` | datetime | When task was created |
| `resolved_at` | datetime | When task was resolved |
| `agent_id` | str | Which agent handled it (v2, nullable) |
| `resolution_notes` | str | What was done to resolve (v2, nullable) |

**FR-048:** Task status flow must be:
```
pending → approved → in_progress → resolved
        ↘ dismissed
```

**FR-049:** `approved` step must never be skipped — no agent action can begin without explicit human approval. This is a hard requirement.

**FR-050:** The `/api/tasks` endpoint must support filtering by: `status`, `priority`, `service`, `type`.

**FR-051:** In v1.0, tasks are created and stored but never acted upon automatically. The task queue is the interface contract for v2.0 agents.

---

### 4.9 Audit Trail

**FR-052:** Every significant event in LogIQ must be written to an `audit_log` table in PostgreSQL.

**FR-053:** Audited event types:

| Event Type | Trigger |
|---|---|
| `search_executed` | User performs a search |
| `rca_created` | Root cause analysis generated |
| `task_created` | Actionable task written to queue |
| `task_approved` | Human approves a task |
| `task_dismissed` | Human dismisses a task |
| `anomaly_detected` | Anomaly flagged during ingestion |
| `anomaly_reviewed` | Human marks anomaly as reviewed |
| `agent_started` | Agent begins working on a task (v2) |
| `agent_completed` | Agent completes a task (v2) |
| `pr_opened` | GitHub PR opened by agent (v2) |

**FR-054:** `audit_log` schema:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Audit record ID |
| `event_type` | str | From the event type list above |
| `actor` | str | "system", "human", or "agent-{id}" |
| `resource_type` | str | log_event, task, rca, anomaly, pull_request |
| `resource_id` | UUID | ID of the resource |
| `details` | jsonb | Event-specific additional context |
| `created_at` | datetime | When the event occurred |

**FR-055:** Audit log must be append-only. No audit records may be updated or deleted.

---

### 4.10 REST API

**FR-056:** LogIQ must expose the following REST API endpoints:

**Search & Analysis:**
```
POST   /api/search
POST   /api/analyze
GET    /api/correlate/{trace_id}
```

**Anomalies:**
```
GET    /api/anomalies
POST   /api/anomalies/{id}/review
```

**Tasks:**
```
GET    /api/tasks
POST   /api/tasks/{id}/approve
POST   /api/tasks/{id}/dismiss
```

**Sources & Health:**
```
GET    /api/sources
GET    /api/health
```

**Observability:**
```
GET    /metrics
```

**Agent Stubs (v1.0 returns 501):**
```
GET    /api/agents
POST   /api/agents/trigger
```

**FR-057:** All endpoints must return consistent error responses:
```json
{
  "error": "Human readable error message",
  "code": "MACHINE_READABLE_CODE",
  "request_id": "uuid",
  "timestamp": "ISO8601"
}
```

**FR-058:** All endpoints must support API key authentication via `X-API-Key` header. Authentication is off by default for local development and enabled via `config.yaml`.

**FR-059:** LogIQ must expose Prometheus metrics at `/metrics`:

| Metric | Type | Description |
|---|---|---|
| `logiq_search_requests_total` | Counter | Total search requests |
| `logiq_analyze_requests_total` | Counter | Total RCA requests |
| `logiq_ingestion_events_total` | Counter | Total log events ingested |
| `logiq_anomalies_detected_total` | Counter | Total anomalies detected |
| `logiq_ingestion_latency_ms` | Histogram | Ingestion pipeline latency |
| `logiq_search_latency_ms` | Histogram | Search query latency |
| `logiq_analyze_latency_ms` | Histogram | RCA latency |
| `logiq_sync_lag_seconds` | Gauge | How far behind real-time each source is |
| `logiq_qdrant_collection_size` | Gauge | Number of vectors in Qdrant |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| Requirement | Target |
|---|---|
| Semantic search p95 latency | < 500ms (up to 1M log entries) |
| RCA response time | < 10 seconds |
| Ingestion throughput | 1,000 events/second in stream mode |
| API health check | < 50ms |
| Embedding batch size | 100 events per batch |

### 5.2 Reliability

- **NFR-001:** Sync engine must recover automatically from source failures without data loss or duplicate ingestion
- **NFR-002:** LogIQ API must remain available even if Qdrant or PostgreSQL is temporarily down — queue events in memory and retry
- **NFR-003:** All external API calls (LLM, embeddings) must have a 30-second timeout with 3 retries using exponential backoff
- **NFR-004:** The system must handle malformed or unparseable log entries gracefully — log the error, skip the entry, continue

### 5.3 Scalability

- **NFR-005:** Ingestion pipeline must support horizontal scaling (multiple workers consuming from a queue)
- **NFR-006:** Qdrant collection must be configured to support sharding for log volumes exceeding 10M entries
- **NFR-007:** Sync engine must support multiple source adapters running concurrently without interference
- **NFR-008:** PostgreSQL schema must include appropriate indexes on `timestamp`, `service`, `severity`, `trace_id`

### 5.4 Security

- **NFR-009:** All API endpoints must support API key authentication via `X-API-Key` header
- **NFR-010:** All sensitive config values (API keys, DB passwords, LLM tokens) must be injectable via environment variables — never hardcoded
- **NFR-011:** LogIQ must never include sensitive values from log payloads in its own operational logs
- **NFR-012:** The audit trail is append-only and must never be modified or deleted, even by administrators
- **NFR-013:** Agent actions (v2) must never execute without a human-approved task record in the database

### 5.5 Developer Experience

- **NFR-014:** Full stack must start with a single `docker compose up` command with zero manual configuration for local development
- **NFR-015:** A fake log generator must start automatically in Docker Compose so there is data to work with immediately
- **NFR-016:** Adding a new source adapter must require implementing exactly 3 methods and one config entry — nothing else
- **NFR-017:** All public functions must have Python type hints and docstrings
- **NFR-018:** README must include a "How to add a new source adapter" section with a step-by-step guide

---

## 6. Technical Architecture

### 6.1 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      LOG SOURCES                            │
│                                                             │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│   │   Loki   │   │   ELK    │   │ Datadog  │  (future)     │
│   └─────┬────┘   └─────┬────┘   └─────┬────┘               │
└─────────┼──────────────┼──────────────┼─────────────────────┘
          ↓              ↓              ↓
┌─────────────────────────────────────────────────────────────┐
│                  SOURCE ADAPTER LAYER                       │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │             BaseSourceAdapter (ABC)                 │   │
│   │   fetch_logs() | stream_logs() | health_check()     │   │
│   │   normalise() | get_source_name()                   │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ┌──────────────┐   ┌──────────────┐                       │
│   │ LokiAdapter  │   │  ELKAdapter  │  (future)             │
│   └──────────────┘   └──────────────┘                       │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  NORMALISATION LAYER                        │
│                                                             │
│   All sources → Standard LogEvent schema                    │
│   id, timestamp, severity, service, environment,           │
│   trace_id, span_id, message, metadata, raw, source        │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     SYNC ENGINE                             │
│                                                             │
│   Poll mode (every N seconds) | Stream mode (WebSocket)    │
│   Cursor tracking in PostgreSQL | Deduplication            │
│   Exponential backoff on failure                           │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  INGESTION PIPELINE                         │
│                                                             │
│   Chunk → Embed (text-embedding-3-small) → Store           │
│   + Anomaly scoring on every event                         │
│   + Actionable task generation on anomalies                │
└────────────────┬──────────────────────┬─────────────────────┘
                 ↓                      ↓
         ┌──────────────┐      ┌────────────────────┐
         │    Qdrant    │      │     PostgreSQL      │
         │  (vectors +  │      │  logs | anomalies  │
         │   metadata)  │      │  tasks | audit_log │
         └──────┬───────┘      └──────────┬─────────┘
                ↓                         ↓
┌─────────────────────────────────────────────────────────────┐
│               INTELLIGENCE LAYER (FastAPI)                  │
│                                                             │
│   /search    → Semantic search over Qdrant                 │
│   /analyze   → LLM root cause analysis + task generation   │
│   /anomalies → Anomaly feed + review                       │
│   /correlate → Full trace analysis across services         │
│   /tasks     → Task queue management                       │
│   /health    → Dependency health check                     │
│   /metrics   → Prometheus metrics                          │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│            TASK QUEUE (PostgreSQL tasks table)              │
│                                                             │
│   pending → approved → in_progress → resolved              │
│           ↘ dismissed                                       │
│                                                             │
│   ← v1.0: tasks stored, awaiting human action              │
│   ← v2.0: agents consume and act on tasks                  │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              AGENT LAYER (v2.0 — not in v1.0)              │
│                                                             │
│   CodeAgent    → reads codebase, proposes fixes            │
│   GitHubAgent  → opens issues and pull requests            │
│   TestAgent    → runs tests to verify fixes                │
│                                                             │
│   All actions require human approval before execution      │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    INTERFACE LAYER                          │
│                                                             │
│   React + TypeScript UI  |  REST API  |  Slack Bot (v1.1)  │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend | FastAPI + Python 3.12 | Async-first, type safe, excellent ecosystem |
| Vector DB | Qdrant | Best performance, production-ready, easy Docker setup |
| Relational DB | PostgreSQL 15 | Raw storage, exact queries, task queue, audit trail |
| Embeddings | OpenAI text-embedding-3-small | Best price/performance for log embeddings |
| LLM | Claude claude-sonnet-4-20250514 | Best reasoning quality for root cause analysis |
| Frontend | React + TypeScript + Tailwind | Modern, type safe, component-based |
| HTTP Client | httpx | Async HTTP for adapter layer |
| WebSocket | websockets library | Real-time streaming from Loki |
| Scheduling | APScheduler | Poll mode scheduling |
| Containerisation | Docker + Docker Compose | Zero-friction deployment |
| Observability | Prometheus + Grafana | Eat your own dogfood |

### 6.3 Project Structure

```
logiq/
├── adapters/
│   ├── base.py              # BaseSourceAdapter ABC
│   ├── loki.py              # LokiAdapter
│   └── elasticsearch.py    # ElasticsearchAdapter (future)
├── models/
│   ├── log_event.py         # LogEvent Pydantic schema
│   ├── rca.py               # RootCauseAnalysis schema
│   ├── task.py              # ActionableTask schema
│   └── anomaly.py           # AnomalyResult schema
├── sync/
│   └── engine.py            # Sync engine (poll + stream)
├── ingestion/
│   └── pipeline.py          # Embed + store + anomaly score
├── intelligence/
│   ├── search.py            # Semantic search
│   ├── analyze.py           # LLM root cause analysis
│   └── anomaly.py           # Anomaly detection
├── api/
│   ├── main.py              # FastAPI app + middleware
│   └── routes/
│       ├── search.py
│       ├── analyze.py
│       ├── anomalies.py
│       ├── tasks.py
│       ├── sources.py
│       └── health.py
├── db/
│   ├── postgres.py          # PostgreSQL connection + queries
│   ├── qdrant.py            # Qdrant client + helpers
│   └── migrations/          # SQL schema files
├── frontend/                # React + TypeScript (Vite)
├── config.yaml              # Full configuration
├── docker-compose.yml       # Full local stack
├── requirements.txt
├── README.md
└── CONTRIBUTING.md
```

### 6.4 Extensibility Contract

Adding a new source adapter requires exactly:

1. Create `adapters/{source_name}.py` extending `BaseSourceAdapter`
2. Implement `fetch_logs()`, `stream_logs()`, `health_check()`, `normalise()`
3. Add entry to `config.yaml`:
   ```yaml
   source:
     type: elasticsearch
     url: http://localhost:9200
   ```

Nothing else in the codebase changes.

---

## 7. Data Models

### 7.1 LogEvent

```python
class Severity(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"
    UNKNOWN = "UNKNOWN"

class LogEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    severity: Severity
    service: str
    environment: str = "production"
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    message: str
    metadata: dict = {}
    raw: str
    source: str
```

### 7.2 RootCauseAnalysis

```python
class ActionableTask(BaseModel):
    task_id: UUID = Field(default_factory=uuid4)
    type: Literal["code_fix", "config_change", "scaling", "restart", "investigation"]
    description: str
    target_service: str
    target_file: Optional[str] = None
    priority: Literal["critical", "high", "medium", "low"]
    estimated_effort: Literal["low", "medium", "high"]
    status: Literal["pending", "approved", "in_progress", "resolved", "dismissed"] = "pending"

class RootCauseAnalysis(BaseModel):
    rca_id: UUID = Field(default_factory=uuid4)
    query: str
    root_cause: str
    affected_services: list[str]
    severity: Literal["critical", "high", "medium", "low"]
    suggested_fix: str
    confidence: float  # 0.0 - 1.0
    related_trace_ids: list[str]
    actionable_tasks: list[ActionableTask]
    analyzed_log_count: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 7.3 AnomalyResult

```python
class AnomalyResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    log_event_id: UUID
    log_event: LogEvent
    anomaly_score: float  # 0.0 - 1.0, higher = more anomalous
    nearest_neighbours: list[dict]  # top 3 similar known logs
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
```

### 7.4 PostgreSQL Schema

```sql
-- Core logs table
CREATE TABLE logs (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    severity VARCHAR(10) NOT NULL,
    service VARCHAR(255) NOT NULL,
    environment VARCHAR(50) DEFAULT 'production',
    trace_id VARCHAR(255),
    span_id VARCHAR(255),
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    raw TEXT NOT NULL,
    source VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_logs_timestamp ON logs(timestamp DESC);
CREATE INDEX idx_logs_service ON logs(service);
CREATE INDEX idx_logs_severity ON logs(severity);
CREATE INDEX idx_logs_trace_id ON logs(trace_id);

-- Anomalies table
CREATE TABLE anomalies (
    id UUID PRIMARY KEY,
    log_event_id UUID REFERENCES logs(id),
    anomaly_score FLOAT NOT NULL,
    nearest_neighbours JSONB DEFAULT '[]',
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX idx_anomalies_detected_at ON anomalies(detected_at DESC);
CREATE INDEX idx_anomalies_reviewed ON anomalies(reviewed);

-- RCA table
CREATE TABLE rca (
    id UUID PRIMARY KEY,
    query TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    affected_services JSONB DEFAULT '[]',
    severity VARCHAR(20) NOT NULL,
    suggested_fix TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    related_trace_ids JSONB DEFAULT '[]',
    analyzed_log_count INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tasks table (agent queue)
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    rca_id UUID REFERENCES rca(id),
    log_event_id UUID REFERENCES logs(id),
    type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    target_service VARCHAR(255) NOT NULL,
    target_file VARCHAR(500),
    priority VARCHAR(20) NOT NULL,
    estimated_effort VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    agent_id VARCHAR(255),
    resolution_notes TEXT
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_priority ON tasks(priority);

-- Audit log (append-only)
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id UUID NOT NULL,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_resource_id ON audit_log(resource_id);

-- Sync cursor table
CREATE TABLE sync_cursors (
    source_name VARCHAR(50) PRIMARY KEY,
    last_synced_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 8. API Specification

### 8.1 POST /api/search

**Request:**
```json
{
  "query": "why did auth service fail at 3am?",
  "filters": {
    "service": "auth-service",
    "severity": "ERROR",
    "environment": "production",
    "start_time": "2026-05-01T02:00:00Z",
    "end_time": "2026-05-01T04:00:00Z"
  },
  "k": 20
}
```

**Response:**
```json
{
  "results": [
    {
      "log_event": { ...LogEvent },
      "similarity_score": 0.94,
      "snippet": "...database connection timeout after 30s...",
      "fallback_used": false
    }
  ],
  "total": 18,
  "query_time_ms": 243,
  "request_id": "uuid"
}
```

### 8.2 POST /api/analyze

**Request:**
```json
{
  "query": "why did auth service fail at 3am?",
  "log_event_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Response:** Full `RootCauseAnalysis` object (see Data Models)

### 8.3 GET /api/anomalies

**Query params:** `reviewed`, `service`, `severity`, `min_score`, `start_time`, `end_time`, `limit`, `offset`

**Response:**
```json
{
  "anomalies": [ ...AnomalyResult[] ],
  "total": 47,
  "unreviewed": 12
}
```

### 8.4 GET /api/correlate/{trace_id}

**Response:**
```json
{
  "trace_id": "abc123",
  "services_involved": ["auth-service", "user-service", "db-proxy"],
  "log_events": [ ...LogEvent[] ],
  "timeline": [ ...ordered events ],
  "rca": { ...RootCauseAnalysis }
}
```

### 8.5 GET /api/health

**Response:**
```json
{
  "status": "healthy",
  "dependencies": {
    "loki": { "status": "healthy", "latency_ms": 12 },
    "qdrant": { "status": "healthy", "latency_ms": 8 },
    "postgresql": { "status": "healthy", "latency_ms": 5 },
    "openai": { "status": "healthy", "latency_ms": 230 },
    "claude": { "status": "healthy", "latency_ms": 410 }
  },
  "sync": {
    "loki": {
      "last_synced_at": "ISO8601",
      "lag_seconds": 12,
      "mode": "stream"
    }
  },
  "version": "1.0.0"
}
```

---

## 9. Frontend Requirements

### 9.1 Pages

**Search Page (default)**
- Large, prominent search bar: *"Ask anything about your logs..."*
- Filter bar: service dropdown, severity multi-select, time range picker, environment toggle
- Results list with: severity badge (colour coded), service name, timestamp, message snippet, similarity score bar
- Click any result → expand to show full log event + all metadata
- "Analyze these results" button → triggers RCA and shows analysis panel below results
- Real-time ingestion status bar at bottom: events ingested, last sync time, lag indicator

**Anomalies Page**
- Table of recent anomalies sorted by score descending
- Columns: anomaly score bar, service, severity, timestamp, message excerpt, reviewed status
- Click row → expand to show full log + nearest neighbours + "Mark as reviewed" button
- Filter bar: service, severity, reviewed status, min score, time range

**Tasks Page**
- List of pending actionable tasks from RCA
- Columns: priority badge, type, description, target service, estimated effort, created at
- Approve / Dismiss buttons per task
- Filter by: status, priority, service

**Health Page**
- Status cards for each dependency: Loki, Qdrant, PostgreSQL, OpenAI, Claude
- Green / amber / red status indicator with latency
- Sync status per source: last synced, lag, mode (poll/stream)
- LogIQ metrics: total logs ingested, anomalies detected, RCAs generated

### 9.2 Design

- Dark theme (Grafana / Linear aesthetic)
- Colour-coded severity badges: ERROR=red, WARN=amber, INFO=blue, DEBUG=grey
- Responsive layout (desktop-first)
- Skeleton loading states for all async operations
- Toast notifications for: RCA complete, anomaly detected, task approved/dismissed

---

## 10. Agentic DevOps — Future Design

> This section documents the v2.0 architecture. Nothing in this section is built in v1.0. It is documented here to ensure v1.0 is designed with the right extensibility points.

### 10.1 Vision

When LogIQ detects an anomaly and generates a root cause analysis, instead of just showing the diagnosis to an engineer, it spins up an AI agent to:

1. Read the relevant source code files
2. Understand the root cause in code context
3. Write a proposed fix
4. Open a GitHub pull request
5. Trigger the test suite
6. Notify the engineer for final review and approval

The engineer goes from "incident alert" to "here's a PR that fixes it" — with one approval click.

### 10.2 Agent Types (v2.0)

| Agent | Responsibility |
|---|---|
| `CodeAgent` | Reads codebase, understands context, proposes code fix |
| `GitHubAgent` | Opens GitHub issues, creates branches, submits PRs |
| `TestAgent` | Triggers CI/CD, monitors test results, reports back |
| `NotifyAgent` | Sends Slack/email summaries of agent actions |

### 10.3 Agent Activation Flow

```
Anomaly detected
      ↓
RCA generated
      ↓
ActionableTask created (status: pending)
      ↓
Human approves task (status: approved)   ← REQUIRED STEP, NEVER SKIPPED
      ↓
Agent assigned to task (status: in_progress)
      ↓
Agent reads codebase via GitHub API
      ↓
Agent generates fix using Claude API
      ↓
Agent opens PR on GitHub
      ↓
TestAgent triggers CI/CD
      ↓
Agent reports results back to LogIQ
      ↓
Task status → resolved (if tests pass)
      ↓
Engineer notified for final merge approval
```

### 10.4 Hard Safety Rules for Agents

These rules are non-negotiable and must be enforced at the database level, not just application level:

- **Rule 1:** No agent may begin work on a task without a database record showing `status = approved`
- **Rule 2:** No agent may merge a PR — only open it. A human must always merge
- **Rule 3:** No agent may modify infrastructure (databases, environment variables, secrets)
- **Rule 4:** No agent may delete any code — only add or modify
- **Rule 5:** Every agent action must be written to `audit_log` before it is executed
- **Rule 6:** If an agent is uncertain (confidence < 0.7), it must pause and request human guidance

### 10.5 GitHub Integration Config (v2.0 placeholder)

```yaml
# Already included in config.yaml as a placeholder in v1.0

integrations:
  github:
    enabled: false
    token: ${GITHUB_TOKEN}
    repos:
      - service: auth-service
        repo: org/auth-service
        default_branch: main
      - service: payments-service
        repo: org/payments-service
        default_branch: main

agents:
  enabled: false
  auto_fix: false
  require_human_approval: true
  confidence_threshold: 0.70
  max_files_per_fix: 3
```

### 10.6 v1.0 Stubs for Agent Endpoints

These endpoints exist in v1.0 but return `501 Not Implemented`:

```
GET  /api/agents              → 501
POST /api/agents/trigger      → 501
```

Response:
```json
{
  "status": "not_implemented",
  "message": "Agentic DevOps features are coming in LogIQ v2.0",
  "docs": "https://github.com/you/logiq#roadmap"
}
```

---

## 11. Milestones

| Milestone | Scope | Target |
|---|---|---|
| **M0 — Setup** | Project scaffold, Docker Compose, fake log generator | Day 1 |
| **M1 — Adapters** | BaseSourceAdapter, LokiAdapter, normalisation, LogEvent schema | Day 2 |
| **M2 — Sync + Ingest** | Sync engine (poll + stream), ingestion pipeline, Qdrant + PostgreSQL storage | Day 3-4 |
| **M3 — Search** | Semantic search endpoint, metadata filters, PostgreSQL fallback | Day 5 |
| **M4 — RCA** | LLM root cause analysis, actionable tasks, trace correlation | Day 6 |
| **M5 — Anomalies** | Anomaly detection pipeline, anomaly table, review endpoint | Day 7 |
| **M6 — API Polish** | All FastAPI routes, Prometheus metrics, error handling, audit trail | Day 8 |
| **M7 — Frontend** | React UI (search, anomalies, tasks, health pages) | Day 9-10 |
| **M8 — Polish** | README, CONTRIBUTING, demo scenarios, Docker Compose final | Day 11 |
| **M9 — Elasticsearch** | Second source adapter | Post-resume |

---

## 12. Roadmap

### v1.0 — Intelligence Foundation ← Building Now
- ✅ Loki source adapter
- ✅ Log normalisation (JSON + plaintext)
- ✅ Sync engine (poll + stream)
- ✅ Qdrant vector storage
- ✅ Semantic natural language search
- ✅ LLM root cause analysis (Claude)
- ✅ Actionable task generation
- ✅ Anomaly detection
- ✅ Task queue (stored, awaiting human action)
- ✅ Audit trail
- ✅ React UI
- ✅ Prometheus metrics
- ✅ Docker Compose deployment

### v1.1 — More Sources + Alerting
- 🔜 Elasticsearch adapter
- 🔜 Slack notifications on anomalies
- 🔜 Email alerting
- 🔜 Webhook support

### v1.2 — Cloud Sources
- 🔜 Datadog adapter
- 🔜 AWS CloudWatch adapter
- 🔜 GCP Cloud Logging adapter
- 🔜 Splunk adapter

### v2.0 — Agentic DevOps
- 🔜 Agent framework (LangChain / CrewAI)
- 🔜 CodeAgent — reads codebase, proposes fixes
- 🔜 GitHubAgent — opens issues and pull requests
- 🔜 TestAgent — triggers CI/CD, monitors results
- 🔜 Human approval workflow UI
- 🔜 Full agent audit trail

### v2.1 — Autonomous Mode
- 🔜 Auto-fix low-risk issues (config changes, scaling)
- 🔜 SLA-aware prioritisation by incident severity
- 🔜 Multi-repo support
- 🔜 Kubernetes operator for auto-discovery

### v3.0 — Hosted SaaS
- 🔜 Multi-tenant architecture
- 🔜 Role-based access control
- 🔜 Usage-based billing (per GB ingested)
- 🔜 Managed cloud deployment

---

## 13. Open Questions

| # | Question | Owner | Priority |
|---|---|---|---|
| 1 | Should anomaly detection thresholds be configurable per service, or global only? | Engineering | High |
| 2 | Should the LLM provider be hot-swappable via config (Claude vs OpenAI vs Ollama for on-prem)? | Product | High |
| 3 | Should LogIQ support on-premise LLMs (Ollama) for privacy-sensitive enterprises? | Product | Medium |
| 4 | What is the log retention policy in Qdrant and PostgreSQL — should LogIQ auto-expire old vectors? | Engineering | Medium |
| 5 | Should task approval require MFA or just API key auth for enterprise customers? | Security | Medium |
| 6 | Should the React UI support SSO (Google, GitHub OAuth) for team usage? | Product | Low |
| 7 | Should multiple simultaneous source adapters share one Qdrant collection or have isolated collections? | Engineering | Low |

---

*LogIQ PRD v1.0 — Siddhant Deshpande — May 2026*
