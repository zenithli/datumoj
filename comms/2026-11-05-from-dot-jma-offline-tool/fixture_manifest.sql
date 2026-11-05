
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE snapshots (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL,
    resource_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,   -- UTC，定宽 ISO，字符串序即时间序
    outcome TEXT NOT NULL,
    sha256 TEXT,
    meta TEXT NOT NULL,
    snapshot TEXT NOT NULL      -- Snapshot 的 JSON，原样还原
);
CREATE INDEX snapshots_url ON snapshots (resource_url, fetched_at, seq);
CREATE INDEX snapshots_source ON snapshots (source_id, fetched_at, seq);
CREATE INDEX snapshots_sha ON snapshots (sha256);
CREATE TABLE parsed (
    sha256 TEXT NOT NULL,
    parser TEXT NOT NULL,
    version TEXT NOT NULL,
    context_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    doc_keys TEXT,
    PRIMARY KEY (sha256, parser, version, context_fingerprint)
);
CREATE TABLE parse_writers (
    doc_key TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    context_fingerprint TEXT NOT NULL,
    PRIMARY KEY (doc_key, sha256)
);
CREATE TABLE publish_states (
    snapshot_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    error TEXT
);
CREATE INDEX publish_states_state ON publish_states (state, snapshot_id);

CREATE TABLE raw_allowed_missing (sha256 TEXT PRIMARY KEY, marked_at TEXT NOT NULL);
