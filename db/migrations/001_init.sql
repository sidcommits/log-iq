CREATE TABLE IF NOT EXISTS sync_cursors (
    source_name    TEXT        PRIMARY KEY,
    last_synced_at TIMESTAMPTZ NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logs (
    id          TEXT        PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    severity    TEXT        NOT NULL,
    service     TEXT        NOT NULL,
    environment TEXT        NOT NULL,
    trace_id    TEXT,
    span_id     TEXT,
    message     TEXT        NOT NULL,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    raw         JSONB       NOT NULL DEFAULT '{}',
    source      TEXT        NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_service   ON logs (service);
CREATE INDEX IF NOT EXISTS idx_logs_severity  ON logs (severity);
CREATE INDEX IF NOT EXISTS idx_logs_trace_id  ON logs (trace_id);
