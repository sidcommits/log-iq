ALTER TABLE logs ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_logs_unembedded ON logs (id)
WHERE embedded_at IS NULL;
