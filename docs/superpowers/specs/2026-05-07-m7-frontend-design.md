# M7 — Frontend Design

**Date:** 2026-05-07
**Milestone:** M7 — Frontend (Day 9-10)
**Scope:** React UI — Search, Anomalies, Tasks, Health pages

## 1. Context

M6 completed the backend API. M7 builds the frontend from scratch. The `frontend/` directory is empty. The backend exposes all required endpoints at `/api/*`. This is a greenfield Vite + React + TypeScript app.

**Not in scope for M7:** Docker Compose integration (M8), E2E tests (M8), Cmd+K command palette (M8 polish), Elasticsearch adapter (M9).

## 2. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Framework | Vite + React 18 + TypeScript (strict) | Project spec; no SSR needed for a local devtool |
| Styling | Tailwind CSS v4 + Shadcn/ui | Shadcn gives accessible primitives; we override the visual layer completely |
| Routing | React Router v6 | Industry standard, simple 4-page setup |
| Data fetching | TanStack Query v5 | Server state cache, `refetchInterval` for polling, automatic retries |
| Toasts | Sonner (Shadcn default) | Lightweight, composable |
| Build | Vite | Fast dev server with `/api` proxy to FastAPI |

## 3. Aesthetic Direction

**Cyber-industrial** — dark base with amber as the single accent color.

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#07090c` | Page background |
| `--bg-panel` | `#0c1018` | Cards, result rows, table backgrounds |
| `--bg-sidebar` | `#090d13` | Sidebar |
| `--border` | `rgba(251,191,36,0.12)` | Default borders |
| `--border-hot` | `rgba(251,191,36,0.55)` | Active/focused borders |
| `--amber` | `#fbbf24` | Primary accent — active nav, labels, key values |
| `--text-primary` | `#eef3f9` | Body text |
| `--text-secondary` | `#a8bece` | Supporting text |
| `--text-muted` | `#6a8090` | Labels, metadata |
| `--green` | `#22c55e` | Healthy / approved |
| `--red` | `#ef4444` | Error / critical |
| `--blue` | `#60a5fa` | Info severity |

**Typography:**
- Display / nav / labels: `Barlow Condensed` (500, 600, 700) — uppercase, tracked
- Data / code / timestamps: `Azeret Mono` (300, 400, 500) — technical, readable

**Details:** CSS scan-line overlay (repeating-linear-gradient, `z-index: 9999`, pointer-events none), ambient amber radial glow top-left, zero border-radius on interactive elements, active nav item marked by 2px amber left border.

## 4. App Shell

Fixed sidebar (220px) + flex-1 main area. 100vh, no outer scroll.

```
┌─ Sidebar (220px) ──┬─ Main (flex-1) ──────────────────┐
│  ◆ LOGIQ v1.0     │  TopBar: breadcrumb + API status  │
│  ─────────────    │  ──────────────────────────────── │
│  INTELLIGENCE     │                                    │
│  ◈ Search (active)│  <PageContent — scrollable>        │
│  ◈ Anomalies  [12]│                                    │
│  ◈ Tasks       [5]│                                    │
│  SYSTEM           │                                    │
│  ◈ Health         │                                    │
│  ─────────────    │                                    │
│  STATUS PANEL     │                                    │
│  ● 1,247,391 evts │                                    │
│  Last sync 2s ago │                                    │
└────────────────────┴───────────────────────────────────┘
```

**Sidebar status panel** — polls `/api/health` every 5s via TanStack Query `refetchInterval`. Shows: connection dot (green/amber/red), total events ingested, last sync time, sync mode, lag.

**TopBar** — breadcrumb (`LOGIQ / SEARCH`), API connection status, UTC clock.

## 5. Project Structure

```
frontend/
├── src/
│   ├── api/
│   │   ├── search.ts        # postSearch(query, filters) → SearchResponse
│   │   ├── anomalies.ts     # getAnomalies(filters), reviewAnomaly(id)
│   │   ├── tasks.ts         # getTasks(filters), approveTask(id), dismissTask(id)
│   │   └── health.ts        # getHealth() → HealthResponse
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── TopBar.tsx
│   │   │   └── StatusPanel.tsx
│   │   └── ui/
│   │       ├── SeverityBadge.tsx
│   │       ├── ScoreBar.tsx
│   │       ├── FilterBar.tsx
│   │       ├── SkeletonRow.tsx
│   │       └── ErrorState.tsx
│   ├── pages/
│   │   ├── SearchPage.tsx
│   │   ├── AnomaliesPage.tsx
│   │   ├── TasksPage.tsx
│   │   └── HealthPage.tsx
│   ├── hooks/
│   │   ├── useSearch.ts
│   │   ├── useAnomalies.ts
│   │   ├── useTasks.ts
│   │   └── useHealth.ts
│   ├── lib/
│   │   ├── queryClient.ts   # TanStack Query client (staleTime: 30s, retry: 2)
│   │   └── constants.ts     # SEVERITY_COLORS, POLL_INTERVAL_MS = 5000
│   ├── App.tsx              # Router setup, QueryClientProvider, Toaster
│   └── main.tsx
├── vite.config.ts           # /api proxy → http://localhost:8000
├── tailwind.config.ts
├── tsconfig.json            # strict: true
└── package.json
```

## 6. Pages

### 6.1 Search Page (default `/`)

- Large search input with `›_` prefix, full-width
- Filter bar: service dropdown, severity multi-select, time range picker, environment toggle (production/staging/dev)
- On submit → `POST /api/search` → results list
- Each result row: severity badge, service name, message (truncated), timestamp, similarity score bar + value
- Click row → expand to show full log event JSON + all metadata
- "Analyze These Results" button → `POST /api/analyze` → RCA panel renders below results (no animation; content appears on response, loading skeleton while pending)
- Real-time status bar at bottom of sidebar (polled, not page-local)

### 6.2 Anomalies Page (`/anomalies`)

- Filter bar: service, severity, reviewed status, min score, time range
- Data table: anomaly score bar, service, severity, timestamp, message excerpt, reviewed status pill
- Click row → expand: full log + nearest neighbours list + "Mark as Reviewed" button → `POST /api/anomalies/{id}/review`
- Sort: score descending by default

### 6.3 Tasks Page (`/tasks`)

- Filter tabs: Pending / In Progress / Resolved / Dismissed
- Card list per task: priority badge, type label, description, service, estimated effort, created time
- Per-card actions: "Approve" → `POST /api/tasks/{id}/approve`, "Dismiss" → `POST /api/tasks/{id}/dismiss`
- Optimistic update: card moves to correct status tab immediately on action

### 6.4 Health Page (`/health`)

- Dependency status cards (PostgreSQL, Qdrant, Loki, OpenAI, Claude): coloured left-border (green/amber/red), latency in ms, status label
- LogIQ metrics row: total logs ingested, anomalies detected, RCAs generated, pending tasks
- Source sync table: source name, mode (POLL/STREAM), last synced, lag, online/offline status
- All data from `GET /api/health`, polled every 5s

## 7. Data Flow

```
Page mounts
  → useX() hook
    → TanStack Query (cache key)
      → api/*.ts fetch()
        → GET/POST /api/*
          → FastAPI backend
```

- All API calls in `api/` throw on non-2xx (check `response.ok`, throw `new Error(data.error)`)
- TanStack Query surfaces error to React Error Boundary
- `VITE_API_URL` env var for non-local deployments; defaults to empty string (Vite proxy handles it in dev)

## 8. Error Handling

**Loading:** skeleton components matching content dimensions — no layout shift.

**Page errors (5xx / network down):** React Error Boundary per page renders: error code + message + "Retry" button that calls `reset()`.

**Inline empty states:** rendered in content area when query returns 0 results (not an error). Each page has its own empty state message.

**Toast notifications (Sonner):**
- Search → analyze triggered: "Analyzing..." → "Analysis complete" or "Analysis failed"
- Task approved: "Task approved" (green toast)
- Task dismissed: "Task dismissed"
- Anomaly reviewed: "Marked as reviewed"

**Auth (401):** persistent banner replaces TopBar content: `AUTHENTICATION REQUIRED — set X-API-Key`.

## 9. Testing

**Vitest + React Testing Library** — colocated `*.test.tsx` files.

| Test | What it covers |
|---|---|
| `Sidebar.test.tsx` | Active nav item class, badge counts render |
| `SearchPage.test.tsx` | Search fires query, results render, empty state |
| `AnomaliesPage.test.tsx` | Table renders, review mutation fires |
| `TasksPage.test.tsx` | Approve/dismiss fire correct endpoints, optimistic update |
| `HealthPage.test.tsx` | Status cards reflect ok/warn/err |
| `api/*.test.ts` | Each API function returns typed response, throws on non-2xx |

No E2E tests in M7. TypeScript strict mode covers most integration surface at compile time.

## 10. Vite Proxy Config

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true }
  }
}
```

No CORS configuration needed in dev. Backend already has CORS middleware for production.

## 11. Definition of Done

- [ ] `npm run dev` serves the app at `localhost:5173` and all 4 pages load
- [ ] Search page returns real results from the backend
- [ ] Anomalies table populates and review action works
- [ ] Tasks approve/dismiss update state correctly
- [ ] Health page reflects real dependency status with auto-polling
- [ ] All TypeScript strict checks pass (`tsc --noEmit`)
- [ ] All Vitest tests pass (`npm test`)
- [ ] No console errors in any page
