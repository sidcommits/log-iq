-- db/migrations/003_intelligence.sql

CREATE TABLE IF NOT EXISTS rca (
    id                TEXT        PRIMARY KEY,
    log_id            TEXT        NOT NULL REFERENCES logs(id),
    trace_id          TEXT,
    summary           TEXT        NOT NULL,
    root_cause        TEXT        NOT NULL,
    affected_services JSONB       NOT NULL DEFAULT '[]',
    confidence        FLOAT       NOT NULL,
    suggested_fixes   JSONB       NOT NULL DEFAULT '[]',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rca_log_id   ON rca (log_id);
CREATE INDEX IF NOT EXISTS idx_rca_trace_id ON rca (trace_id);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT        PRIMARY KEY,
    rca_id      TEXT        NOT NULL REFERENCES rca(id),
    log_id      TEXT        NOT NULL REFERENCES logs(id),
    title       TEXT        NOT NULL,
    description TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending',
    priority    TEXT        NOT NULL DEFAULT 'medium',
    agent_id    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks (priority);
CREATE INDEX IF NOT EXISTS idx_tasks_rca_id   ON tasks (rca_id);

CREATE TABLE IF NOT EXISTS anomalies (
    id          TEXT        PRIMARY KEY,
    log_id      TEXT        NOT NULL REFERENCES logs(id),
    score       FLOAT       NOT NULL,
    is_anomaly  BOOLEAN     NOT NULL,
    threshold   FLOAT       NOT NULL,
    reviewed    BOOLEAN     NOT NULL DEFAULT FALSE,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomalies_log_id   ON anomalies (log_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_reviewed ON anomalies (reviewed);

CREATE TABLE IF NOT EXISTS audit_log (
    id         TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    event_type TEXT        NOT NULL,
    payload    JSONB       NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);
