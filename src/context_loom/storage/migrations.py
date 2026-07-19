"""Forward-only SQLite schema migrations.

The SQLite database is the durable catalog.  Sanitized source bodies are also
kept in the private content-addressed store; search indexes and hashed vectors
are deliberately rebuildable derivatives.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class Migration:
    """One immutable, forward-only schema migration."""

    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return sha256(self.sql.encode("utf-8")).hexdigest()


INITIAL_SCHEMA = r"""
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_sync_at TEXT,
    active_generation_id TEXT
) STRICT;

CREATE UNIQUE INDEX workspaces_name_unique ON workspaces(name COLLATE NOCASE);

CREATE TABLE index_generations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('building', 'published', 'failed')),
    created_at TEXT NOT NULL,
    published_at TEXT,
    resource_count INTEGER NOT NULL DEFAULT 0 CHECK (resource_count >= 0),
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    source_fingerprint TEXT NOT NULL
) STRICT;

CREATE INDEX index_generations_workspace_created
    ON index_generations(workspace_id, created_at DESC);

CREATE TABLE sync_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    generation_id TEXT REFERENCES index_generations(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'published', 'failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    added INTEGER NOT NULL DEFAULT 0 CHECK (added >= 0),
    modified INTEGER NOT NULL DEFAULT 0 CHECK (modified >= 0),
    deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted >= 0),
    renamed INTEGER NOT NULL DEFAULT 0 CHECK (renamed >= 0),
    unchanged INTEGER NOT NULL DEFAULT 0 CHECK (unchanged >= 0),
    excluded INTEGER NOT NULL DEFAULT 0 CHECK (excluded >= 0),
    redacted INTEGER NOT NULL DEFAULT 0 CHECK (redacted >= 0),
    duration_ms REAL CHECK (duration_ms IS NULL OR duration_ms >= 0),
    error_code TEXT
) STRICT;

CREATE INDEX sync_runs_workspace_started ON sync_runs(workspace_id, started_at DESC);

CREATE TABLE resources (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'file',
    current_version_id TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    tombstoned_at TEXT,
    UNIQUE(workspace_id, relative_path)
) STRICT;

CREATE INDEX resources_workspace_active
    ON resources(workspace_id, is_deleted, relative_path);

CREATE TABLE resource_versions (
    id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL REFERENCES index_generations(id) ON DELETE RESTRICT,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    cas_digest TEXT NOT NULL CHECK (length(cas_digest) = 64),
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    mtime_ns INTEGER,
    inode INTEGER,
    device INTEGER,
    redacted_count INTEGER NOT NULL DEFAULT 0 CHECK (redacted_count >= 0),
    parser_fingerprint TEXT NOT NULL,
    chunker_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(resource_id, sha256, parser_fingerprint, chunker_fingerprint)
) STRICT;

CREATE INDEX resource_versions_digest ON resource_versions(sha256);
CREATE INDEX resource_versions_resource_created
    ON resource_versions(resource_id, created_at DESC);

CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES resource_versions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    relative_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    start_byte INTEGER NOT NULL CHECK (start_byte >= 0),
    end_byte INTEGER NOT NULL CHECK (end_byte >= start_byte),
    start_line INTEGER NOT NULL CHECK (start_line >= 1),
    end_line INTEGER NOT NULL CHECK (end_line >= start_line),
    token_estimate INTEGER NOT NULL CHECK (token_estimate >= 0),
    protected_atoms_json TEXT NOT NULL,
    embedding_digest TEXT NOT NULL CHECK (length(embedding_digest) = 64),
    created_at TEXT NOT NULL,
    UNIQUE(version_id, ordinal)
) STRICT;

CREATE INDEX chunks_version_ordinal ON chunks(version_id, ordinal);
CREATE INDEX chunks_content_digest ON chunks(content_sha256);

CREATE TABLE embeddings (
    id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE REFERENCES chunks(id) ON DELETE CASCADE,
    algorithm TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    vector_json TEXT NOT NULL,
    vector_digest TEXT NOT NULL CHECK (length(vector_digest) = 64),
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX embeddings_vector_digest ON embeddings(vector_digest);

CREATE TABLE generation_resources (
    generation_id TEXT NOT NULL REFERENCES index_generations(id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES resource_versions(id) ON DELETE RESTRICT,
    relative_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY(generation_id, resource_id)
) STRICT;

CREATE INDEX generation_resources_version ON generation_resources(version_id);

CREATE TABLE change_events (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL REFERENCES index_generations(id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL CHECK (
        change_type IN ('added', 'modified', 'deleted', 'renamed', 'unchanged')
    ),
    old_path TEXT,
    new_path TEXT,
    old_version_id TEXT,
    new_version_id TEXT,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX change_events_generation ON change_events(generation_id, change_type);

CREATE TABLE scan_exclusions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL REFERENCES index_generations(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    preserve_existing INTEGER NOT NULL DEFAULT 0 CHECK (preserve_existing IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE(generation_id, relative_path, reason)
) STRICT;

CREATE TABLE threads (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE hydration_runs (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    generation_id TEXT REFERENCES index_generations(id) ON DELETE SET NULL,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    adapter TEXT NOT NULL,
    requested_mode TEXT NOT NULL,
    effective_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    baseline_input_tokens INTEGER
        CHECK (baseline_input_tokens IS NULL OR baseline_input_tokens >= 0),
    hydrated_input_tokens INTEGER
        CHECK (hydrated_input_tokens IS NULL OR hydrated_input_tokens >= 0),
    local_input_tokens INTEGER CHECK (local_input_tokens IS NULL OR local_input_tokens >= 0),
    local_output_tokens INTEGER CHECK (local_output_tokens IS NULL OR local_output_tokens >= 0),
    result_json TEXT,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX hydration_runs_thread_created ON hydration_runs(thread_id, created_at DESC);

CREATE TABLE hydration_items (
    id TEXT PRIMARY KEY,
    hydration_id TEXT NOT NULL REFERENCES hydration_runs(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE RESTRICT,
    version_id TEXT NOT NULL REFERENCES resource_versions(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    score_json TEXT NOT NULL,
    selection_reason TEXT NOT NULL,
    citation_json TEXT NOT NULL,
    UNIQUE(hydration_id, ordinal)
) STRICT;

CREATE TABLE fidelity_reports (
    hydration_id TEXT PRIMARY KEY REFERENCES hydration_runs(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    requested_mode TEXT NOT NULL,
    effective_mode TEXT NOT NULL,
    replay_hash TEXT NOT NULL CHECK (length(replay_hash) = 64),
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE usage_events (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    hydration_id TEXT REFERENCES hydration_runs(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    counting_method TEXT NOT NULL,
    actual_input_tokens INTEGER CHECK (actual_input_tokens IS NULL OR actual_input_tokens >= 0),
    actual_output_tokens INTEGER CHECK (actual_output_tokens IS NULL OR actual_output_tokens >= 0),
    cached_input_tokens INTEGER CHECK (cached_input_tokens IS NULL OR cached_input_tokens >= 0),
    reasoning_tokens INTEGER CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),
    local_input_tokens INTEGER CHECK (local_input_tokens IS NULL OR local_input_tokens >= 0),
    local_output_tokens INTEGER CHECK (local_output_tokens IS NULL OR local_output_tokens >= 0),
    verified_baseline_input_tokens INTEGER CHECK (
        verified_baseline_input_tokens IS NULL OR verified_baseline_input_tokens >= 0
    ),
    provider_request_id_hash TEXT,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX usage_events_thread_observed ON usage_events(thread_id, observed_at DESC);

CREATE TABLE feedback (
    id TEXT PRIMARY KEY,
    hydration_id TEXT REFERENCES hydration_runs(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN -1 AND 1),
    labels_json TEXT NOT NULL,
    note_redacted TEXT,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE adapter_installations (
    id TEXT PRIMARY KEY,
    adapter TEXT NOT NULL,
    scope TEXT NOT NULL,
    target_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(adapter, scope, target_hash)
) STRICT;

CREATE TABLE eval_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
    dataset_fingerprint TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE VIRTUAL TABLE chunk_fts USING fts5(
    text,
    relative_path,
    kind UNINDEXED,
    content='chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_fts_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunk_fts(rowid, text, relative_path, kind)
    VALUES (new.rowid, new.text, new.relative_path, new.kind);
END;

CREATE TRIGGER chunks_fts_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, text, relative_path, kind)
    VALUES ('delete', old.rowid, old.text, old.relative_path, old.kind);
END;

CREATE TRIGGER chunks_fts_update AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, text, relative_path, kind)
    VALUES ('delete', old.rowid, old.text, old.relative_path, old.kind);
    INSERT INTO chunk_fts(rowid, text, relative_path, kind)
    VALUES (new.rowid, new.text, new.relative_path, new.kind);
END;
"""


BILLABLE_USAGE_SCHEMA = r"""
ALTER TABLE usage_events ADD COLUMN billable_input_tokens INTEGER
    CHECK (billable_input_tokens IS NULL OR billable_input_tokens >= 0);
ALTER TABLE usage_events ADD COLUMN billable_output_tokens INTEGER
    CHECK (billable_output_tokens IS NULL OR billable_output_tokens >= 0);
"""


THREAD_LABEL_AND_USAGE_OWNERSHIP_SCHEMA = r"""
ALTER TABLE threads ADD COLUMN label TEXT
    CHECK (label IS NULL OR (length(label) <= 120 AND length(trim(label)) > 0));

CREATE TRIGGER usage_events_one_observation_per_hydration
BEFORE INSERT ON usage_events
WHEN NEW.hydration_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM usage_events WHERE hydration_id = NEW.hydration_id
)
BEGIN
    SELECT RAISE(ABORT, 'hydration already has a usage observation');
END;
"""


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="initial canonical schema", sql=INITIAL_SCHEMA),
    Migration(version=2, name="durable billable usage fields", sql=BILLABLE_USAGE_SCHEMA),
    Migration(
        version=3,
        name="durable thread labels and single hydration usage ownership",
        sql=THREAD_LABEL_AND_USAGE_OWNERSHIP_SCHEMA,
    ),
)


def latest_version() -> int:
    """Return the newest migration bundled with this release."""

    return MIGRATIONS[-1].version if MIGRATIONS else 0
