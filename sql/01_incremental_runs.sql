-- Records every incremental cleaning run applied to this database.
-- The primary key prevents the same light-scraper run from being applied twice.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(255) PRIMARY KEY,
    mode VARCHAR(30) NOT NULL CHECK (mode IN ('incremental')),
    source_manifest_sha256 CHAR(64) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL CHECK (status IN ('running', 'complete', 'failed')),
    action_count INT NOT NULL CHECK (action_count >= 0)
);
