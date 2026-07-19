"""Transactional repository over Context Loom's canonical SQLite catalog."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from context_loom.domain.models import (
    SyncReport,
    UsageObservation,
    WorkspaceRecord,
    WorkspaceStatus,
)
from context_loom.storage.cas import ContentAddressedStore
from context_loom.storage.database import Database


class WorkspaceNotFound(LookupError):
    """Raised when a workspace id has no durable record."""


class InvalidWorkspace(ValueError):
    """Raised when a workspace root is not a private, indexable directory."""


class IdempotencyConflict(ValueError):
    """Raised when one idempotency key is reused for different data."""


class ThreadNotFound(LookupError):
    """Raised when usage references a thread that was never hydrated."""


class HydrationNotFound(LookupError):
    """Raised when usage references an unknown hydration."""


class ThreadWorkspaceConflict(ValueError):
    """Raised when a global thread identifier is reused across workspaces."""


class HydrationThreadMismatch(ValueError):
    """Raised when usage assigns a hydration to a different thread."""


class HydrationUsageConflict(ValueError):
    """Raised when one hydration receives more than one distinct observation."""


@dataclass(frozen=True, slots=True)
class ChunkInput:
    """Sanitized deterministic chunk ready for one atomic publication."""

    ordinal: int
    text: str
    content_sha256: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    token_estimate: int
    protected_atoms: tuple[str, ...]
    embedding: tuple[float, ...]
    embedding_digest: str
    embedding_algorithm: str = "hashed-lexical-v1"


@dataclass(frozen=True, slots=True)
class ResourceInput:
    """One sanitized resource and its derived, rebuildable chunks."""

    relative_path: str
    kind: str
    origin: str
    sha256: str
    cas_digest: str
    size_bytes: int
    mtime_ns: int | None
    inode: int | None
    device: int | None
    redacted_count: int
    parser_fingerprint: str
    chunker_fingerprint: str
    chunks: tuple[ChunkInput, ...]


@dataclass(frozen=True, slots=True)
class ExclusionInput:
    """A path deliberately omitted from one scan and its non-secret reason."""

    relative_path: str
    reason: str
    preserve_existing: bool = False


@dataclass(frozen=True, slots=True)
class PublishResult:
    """Counts from one successfully published workspace generation."""

    workspace_id: str
    generation_id: str
    sync_run_id: str
    added: int
    modified: int
    deleted: int
    renamed: int
    unchanged: int
    excluded: int
    redacted: int
    duration_ms: float


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}  # noqa: SIM118 - sqlite3.Row iterates values


class ContextRepository:
    """The shared storage service used by API, CLI, MCP, and hydration code."""

    def __init__(
        self,
        database: Database,
        cas: ContentAddressedStore,
        *,
        initialize: bool = True,
    ) -> None:
        self.database = database
        self.cas = cas
        if initialize:
            self.database.initialize()

    def create_workspace(
        self,
        name: str,
        root_path: Path | str,
        *,
        workspace_id: str | None = None,
    ) -> WorkspaceRecord:
        """Allowlist one real, non-symlinked directory for later scanning."""

        original = Path(root_path).expanduser()
        if original.is_symlink() or not original.is_dir():
            raise InvalidWorkspace("workspace root must be an existing non-symlinked directory")
        if not name.strip() or len(name) > 120:
            raise InvalidWorkspace("workspace name must contain 1 to 120 characters")
        root = original.resolve(strict=True)
        identifier = workspace_id or str(uuid4())
        if not identifier.strip():
            raise InvalidWorkspace("workspace id must not be blank")
        now = _utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO workspaces(id, name, root_path, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (identifier, name, str(root), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise InvalidWorkspace("workspace name or root is already registered") from exc
        workspace = self.get_workspace(identifier)
        if workspace is None:  # pragma: no cover - transaction readback invariant
            raise RuntimeError("workspace insert did not persist")
        return workspace

    def list_workspaces(self) -> list[WorkspaceRecord]:
        rows = self.database.rows(
            "SELECT id, name, root_path, created_at, updated_at, last_sync_at "
            "FROM workspaces ORDER BY name COLLATE NOCASE, id"
        )
        return [WorkspaceRecord.model_validate(_row_dict(row)) for row in rows]

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        rows = self.database.rows(
            """
            SELECT id, name, root_path, created_at, updated_at, last_sync_at
            FROM workspaces WHERE id = ?
            """,
            (workspace_id,),
        )
        if not rows:
            return None
        return WorkspaceRecord.model_validate(_row_dict(rows[0]))

    def require_workspace(self, workspace_id: str) -> WorkspaceRecord:
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFound(workspace_id)
        return workspace

    def get_workspace_status(self, workspace_id: str) -> WorkspaceStatus:
        workspace = self.require_workspace(workspace_id)
        rows = self.database.rows(
            """
            SELECT w.active_generation_id,
                   COUNT(DISTINCT CASE WHEN r.is_deleted = 0 THEN r.id END) AS resources,
                   COUNT(DISTINCT CASE WHEN r.is_deleted = 0 THEN c.id END) AS chunks,
                   COUNT(DISTINCT CASE WHEN r.is_deleted = 1 THEN r.id END) AS stale
            FROM workspaces AS w
            LEFT JOIN resources AS r ON r.workspace_id = w.id
            LEFT JOIN chunks AS c ON c.version_id = r.current_version_id
            WHERE w.id = ?
            GROUP BY w.id
            """,
            (workspace_id,),
        )
        summary = rows[0]
        exclusion_count = 0
        active_generation_id = summary["active_generation_id"]
        if active_generation_id is not None:
            exclusion_count = int(
                self.database.scalar(
                    "SELECT COUNT(*) FROM scan_exclusions WHERE generation_id = ?",
                    (active_generation_id,),
                )
                or 0
            )
        sync_rows = self.database.rows(
            """
            SELECT workspace_id, generation_id, added, modified, deleted, unchanged,
                   excluded, redacted, duration_ms
            FROM sync_runs
            WHERE workspace_id = ? AND status = 'published'
            ORDER BY started_at DESC LIMIT 1
            """,
            (workspace_id,),
        )
        last_sync = None
        if sync_rows:
            raw_sync = _row_dict(sync_rows[0])
            raw_sync["modified"] = int(raw_sync["modified"])
            last_sync = SyncReport.model_validate(raw_sync)
        return WorkspaceStatus(
            workspace=workspace,
            active_generation_id=active_generation_id,
            indexed_resources=int(summary["resources"]),
            indexed_chunks=int(summary["chunks"]),
            stale_resources=int(summary["stale"]),
            excluded_resources=exclusion_count,
            last_sync=last_sync,
        )

    def _insert_chunks(
        self,
        connection: sqlite3.Connection,
        *,
        version_id: str,
        resource: ResourceInput,
        now: str,
    ) -> None:
        for chunk in resource.chunks:
            chunk_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO chunks(
                    id, version_id, ordinal, relative_path, kind, text, content_sha256,
                    start_byte, end_byte, start_line, end_line, token_estimate,
                    protected_atoms_json, embedding_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    version_id,
                    chunk.ordinal,
                    resource.relative_path,
                    resource.kind,
                    chunk.text,
                    chunk.content_sha256,
                    chunk.start_byte,
                    chunk.end_byte,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.token_estimate,
                    _json(chunk.protected_atoms),
                    chunk.embedding_digest,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO embeddings(
                    id, chunk_id, algorithm, dimensions, vector_json, vector_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    chunk_id,
                    chunk.embedding_algorithm,
                    len(chunk.embedding),
                    _json(chunk.embedding),
                    chunk.embedding_digest,
                    now,
                ),
            )

    def _insert_version(
        self,
        connection: sqlite3.Connection,
        *,
        resource_id: str,
        generation_id: str,
        resource: ResourceInput,
        now: str,
    ) -> str:
        version_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO resource_versions(
                id, resource_id, generation_id, sha256, cas_digest, size_bytes, mtime_ns,
                inode, device, redacted_count, parser_fingerprint, chunker_fingerprint,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                resource_id,
                generation_id,
                resource.sha256,
                resource.cas_digest,
                resource.size_bytes,
                resource.mtime_ns,
                resource.inode,
                resource.device,
                resource.redacted_count,
                resource.parser_fingerprint,
                resource.chunker_fingerprint,
                now,
            ),
        )
        self._insert_chunks(
            connection,
            version_id=version_id,
            resource=resource,
            now=now,
        )
        return version_id

    def _reuse_or_insert_version(
        self,
        connection: sqlite3.Connection,
        *,
        resource_id: str,
        generation_id: str,
        resource: ResourceInput,
        now: str,
    ) -> str:
        prior = connection.execute(
            """
            SELECT id FROM resource_versions
            WHERE resource_id = ? AND sha256 = ? AND parser_fingerprint = ?
                  AND chunker_fingerprint = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (
                resource_id,
                resource.sha256,
                resource.parser_fingerprint,
                resource.chunker_fingerprint,
            ),
        ).fetchone()
        if prior is not None:
            return str(prior["id"])
        return self._insert_version(
            connection,
            resource_id=resource_id,
            generation_id=generation_id,
            resource=resource,
            now=now,
        )

    def _validate_resource_inputs(self, resources: Sequence[ResourceInput]) -> None:
        """Reject malformed collector output before opening the publication transaction."""

        for resource in resources:
            path = PurePosixPath(resource.relative_path)
            if (
                path.is_absolute()
                or "\\" in resource.relative_path
                or any(part in {"", ".", ".."} for part in path.parts)
            ):
                raise ValueError("resource path must be canonical and workspace-relative")
            if (
                not re.fullmatch(r"[0-9a-f]{64}", resource.sha256)
                or resource.cas_digest != resource.sha256
            ):
                raise ValueError("resource digest must match its canonical CAS address")
            content = self.cas.get(resource.cas_digest)
            if (
                len(content) != resource.size_bytes
                or sha256(content).hexdigest() != resource.sha256
            ):
                raise ValueError("resource metadata does not match sanitized CAS content")
            ordinals = [chunk.ordinal for chunk in resource.chunks]
            if ordinals != list(range(len(resource.chunks))):
                raise ValueError("chunk ordinals must be contiguous and deterministic")
            for chunk in resource.chunks:
                if chunk.end_byte > len(content):
                    raise ValueError("chunk byte locator exceeds its resource")
                excerpt_bytes = content[chunk.start_byte : chunk.end_byte]
                if excerpt_bytes != chunk.text.encode("utf-8"):
                    raise ValueError("chunk text does not match its byte locator")
                if sha256(excerpt_bytes).hexdigest() != chunk.content_sha256:
                    raise ValueError("chunk digest does not match its sanitized text")
                actual_start_line = content[: chunk.start_byte].count(b"\n") + 1
                actual_end_line = actual_start_line + excerpt_bytes.count(b"\n")
                if excerpt_bytes.endswith(b"\n"):
                    actual_end_line -= 1
                if chunk.start_line != actual_start_line or chunk.end_line != max(
                    actual_start_line, actual_end_line
                ):
                    raise ValueError("chunk line locator does not match its byte locator")
                vector_digest = sha256(_json(chunk.embedding).encode("utf-8")).hexdigest()
                if not chunk.embedding or vector_digest != chunk.embedding_digest:
                    raise ValueError("chunk embedding digest is invalid")

    def publish_generation(
        self,
        workspace_id: str,
        resources: Sequence[ResourceInput],
        exclusions: Sequence[ExclusionInput],
        *,
        source_fingerprint: str,
        duration_ms: float,
    ) -> PublishResult:
        """Publish one complete scan, including tombstones and rename reuse, atomically."""

        self.require_workspace(workspace_id)
        relative_paths = [resource.relative_path for resource in resources]
        if len(relative_paths) != len(set(relative_paths)):
            raise ValueError("one generation cannot contain duplicate resource paths")
        if not re.fullmatch(r"[0-9a-f]{64}", source_fingerprint):
            raise ValueError("source fingerprint must be a lowercase SHA-256 digest")
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("sync duration must be finite and non-negative")
        self._validate_resource_inputs(resources)
        generation_id = str(uuid4())
        sync_run_id = str(uuid4())
        now = _utc_now()
        counts = {
            "added": 0,
            "modified": 0,
            "deleted": 0,
            "renamed": 0,
            "unchanged": 0,
        }

        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO index_generations(
                    id, workspace_id, status, created_at, source_fingerprint
                ) VALUES (?, ?, 'building', ?, ?)
                """,
                (generation_id, workspace_id, now, source_fingerprint),
            )
            connection.execute(
                """
                INSERT INTO sync_runs(id, workspace_id, generation_id, status, started_at)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (sync_run_id, workspace_id, generation_id, now),
            )
            current_rows = connection.execute(
                """
                SELECT r.id AS resource_id, r.relative_path, r.kind, r.origin,
                       r.current_version_id AS version_id, rv.sha256,
                       rv.parser_fingerprint, rv.chunker_fingerprint
                FROM resources AS r
                JOIN resource_versions AS rv ON rv.id = r.current_version_id
                WHERE r.workspace_id = ? AND r.is_deleted = 0
                """,
                (workspace_id,),
            ).fetchall()
            current = {str(row["relative_path"]): _row_dict(row) for row in current_rows}
            tombstone_rows = connection.execute(
                """
                SELECT r.id AS resource_id, r.relative_path, r.kind, r.origin,
                       r.current_version_id AS version_id, rv.sha256,
                       rv.parser_fingerprint, rv.chunker_fingerprint
                FROM resources AS r
                JOIN resource_versions AS rv ON rv.id = r.current_version_id
                WHERE r.workspace_id = ? AND r.is_deleted = 1
                """,
                (workspace_id,),
            ).fetchall()
            tombstoned = {str(row["relative_path"]): _row_dict(row) for row in tombstone_rows}
            incoming = {resource.relative_path: resource for resource in resources}

            missing_paths = set(current) - set(incoming)
            new_paths = set(incoming) - set(current)
            old_by_digest: dict[str, list[str]] = {}
            new_by_digest: dict[str, list[str]] = {}
            for path in missing_paths:
                old_by_digest.setdefault(str(current[path]["sha256"]), []).append(path)
            for path in new_paths - set(tombstoned):
                new_by_digest.setdefault(incoming[path].sha256, []).append(path)

            for digest in sorted(set(old_by_digest) & set(new_by_digest)):
                old_candidates = sorted(old_by_digest[digest])
                new_candidates = sorted(new_by_digest[digest])
                if len(old_candidates) != 1 or len(new_candidates) != 1:
                    continue
                old_path = old_candidates[0]
                new_path = new_candidates[0]
                row = current.pop(old_path)
                connection.execute(
                    """
                    UPDATE resources SET relative_path = ?, kind = ?, origin = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_path,
                        incoming[new_path].kind,
                        incoming[new_path].origin,
                        now,
                        row["resource_id"],
                    ),
                )
                connection.execute(
                    """
                    UPDATE chunks SET relative_path = ?, kind = ?
                    WHERE version_id IN (
                        SELECT id FROM resource_versions WHERE resource_id = ?
                    )
                    """,
                    (new_path, incoming[new_path].kind, row["resource_id"]),
                )
                connection.execute(
                    """
                    INSERT INTO change_events(
                        id, workspace_id, generation_id, resource_id, change_type,
                        old_path, new_path, old_version_id, new_version_id, created_at
                    ) VALUES (?, ?, ?, ?, 'renamed', ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        workspace_id,
                        generation_id,
                        row["resource_id"],
                        old_path,
                        new_path,
                        row["version_id"],
                        row["version_id"],
                        now,
                    ),
                )
                row["relative_path"] = new_path
                row["kind"] = incoming[new_path].kind
                row["origin"] = incoming[new_path].origin
                current[new_path] = row
                counts["renamed"] += 1

            active_members: list[tuple[str, str, str, str]] = []
            for path in sorted(incoming):
                item = incoming[path]
                existing = current.get(path)
                resurrected = existing is None and path in tombstoned
                created_resource = existing is None and not resurrected
                if created_resource:
                    resource_id = str(uuid4())
                    connection.execute(
                        """
                        INSERT INTO resources(
                            id, workspace_id, relative_path, kind, origin, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            resource_id,
                            workspace_id,
                            path,
                            item.kind,
                            item.origin,
                            now,
                            now,
                        ),
                    )
                    version_id = self._insert_version(
                        connection,
                        resource_id=resource_id,
                        generation_id=generation_id,
                        resource=item,
                        now=now,
                    )
                    change_type = "added"
                    old_version_id = None
                    counts["added"] += 1
                elif resurrected:
                    existing = tombstoned[path]
                    resource_id = str(existing["resource_id"])
                    old_version_id = str(existing["version_id"])
                    version_id = self._reuse_or_insert_version(
                        connection,
                        resource_id=resource_id,
                        generation_id=generation_id,
                        resource=item,
                        now=now,
                    )
                    change_type = "added"
                    counts["added"] += 1
                    connection.execute(
                        """
                        UPDATE resources
                        SET kind = ?, origin = ?, current_version_id = ?, is_deleted = 0,
                            tombstoned_at = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (item.kind, item.origin, version_id, now, resource_id),
                    )
                else:
                    if existing is None:  # pragma: no cover - branch narrowing invariant
                        raise RuntimeError("active resource lookup failed")
                    resource_id = str(existing["resource_id"])
                    old_version_id = str(existing["version_id"])
                    same_derivation = (
                        existing["sha256"] == item.sha256
                        and existing["parser_fingerprint"] == item.parser_fingerprint
                        and existing["chunker_fingerprint"] == item.chunker_fingerprint
                    )
                    if same_derivation:
                        version_id = old_version_id
                        change_type = "unchanged" if path not in new_paths else "renamed"
                        if change_type == "unchanged":
                            counts["unchanged"] += 1
                    else:
                        version_id = self._reuse_or_insert_version(
                            connection,
                            resource_id=resource_id,
                            generation_id=generation_id,
                            resource=item,
                            now=now,
                        )
                        change_type = "modified"
                        counts["modified"] += 1
                    connection.execute(
                        """
                        UPDATE resources
                        SET kind = ?, origin = ?, current_version_id = ?, is_deleted = 0,
                            tombstoned_at = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (item.kind, item.origin, version_id, now, resource_id),
                    )
                if created_resource:
                    connection.execute(
                        "UPDATE resources SET current_version_id = ? WHERE id = ?",
                        (version_id, resource_id),
                    )
                if change_type != "renamed":
                    connection.execute(
                        """
                        INSERT INTO change_events(
                            id, workspace_id, generation_id, resource_id, change_type,
                            old_path, new_path, old_version_id, new_version_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            workspace_id,
                            generation_id,
                            resource_id,
                            change_type,
                            path if old_version_id is not None else None,
                            path,
                            old_version_id,
                            version_id,
                            now,
                        ),
                    )
                active_members.append((resource_id, version_id, path, item.kind))

            preserve_paths = {
                exclusion.relative_path for exclusion in exclusions if exclusion.preserve_existing
            }
            for path in sorted(preserve_paths & set(current) - set(incoming)):
                existing = current[path]
                active_members.append(
                    (
                        str(existing["resource_id"]),
                        str(existing["version_id"]),
                        path,
                        str(existing["kind"]),
                    )
                )
                connection.execute(
                    """
                    INSERT INTO change_events(
                        id, workspace_id, generation_id, resource_id, change_type,
                        old_path, new_path, old_version_id, new_version_id, created_at
                    ) VALUES (?, ?, ?, ?, 'unchanged', ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        workspace_id,
                        generation_id,
                        existing["resource_id"],
                        path,
                        path,
                        existing["version_id"],
                        existing["version_id"],
                        now,
                    ),
                )
                counts["unchanged"] += 1

            final_paths = set(incoming) | preserve_paths
            for path, existing in sorted(current.items()):
                if path in final_paths:
                    continue
                connection.execute(
                    """
                    UPDATE resources
                    SET is_deleted = 1, tombstoned_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, existing["resource_id"]),
                )
                connection.execute(
                    """
                    INSERT INTO change_events(
                        id, workspace_id, generation_id, resource_id, change_type,
                        old_path, old_version_id, created_at
                    ) VALUES (?, ?, ?, ?, 'deleted', ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        workspace_id,
                        generation_id,
                        existing["resource_id"],
                        path,
                        existing["version_id"],
                        now,
                    ),
                )
                counts["deleted"] += 1

            connection.executemany(
                """
                INSERT INTO generation_resources(
                    generation_id, resource_id, version_id, relative_path, kind
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (generation_id, resource_id, version_id, path, kind)
                    for resource_id, version_id, path, kind in active_members
                ],
            )
            connection.executemany(
                """
                INSERT INTO scan_exclusions(
                    id, workspace_id, generation_id, relative_path, reason,
                    preserve_existing, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(uuid4()),
                        workspace_id,
                        generation_id,
                        exclusion.relative_path,
                        exclusion.reason,
                        int(exclusion.preserve_existing),
                        now,
                    )
                    for exclusion in exclusions
                ],
            )
            chunk_count_row = connection.execute(
                """
                SELECT COUNT(*)
                FROM generation_resources AS gr
                JOIN chunks AS c ON c.version_id = gr.version_id
                WHERE gr.generation_id = ?
                """,
                (generation_id,),
            ).fetchone()
            chunk_count = int(chunk_count_row[0]) if chunk_count_row is not None else 0
            redacted = sum(1 for resource in resources if resource.redacted_count > 0)
            connection.execute(
                """
                UPDATE index_generations
                SET status = 'published', published_at = ?, resource_count = ?, chunk_count = ?
                WHERE id = ?
                """,
                (now, len(active_members), chunk_count, generation_id),
            )
            connection.execute(
                """
                UPDATE sync_runs
                SET status = 'published', finished_at = ?, added = ?, modified = ?, deleted = ?,
                    renamed = ?, unchanged = ?, excluded = ?, redacted = ?, duration_ms = ?
                WHERE id = ?
                """,
                (
                    now,
                    counts["added"],
                    counts["modified"],
                    counts["deleted"],
                    counts["renamed"],
                    counts["unchanged"],
                    len(exclusions),
                    redacted,
                    duration_ms,
                    sync_run_id,
                ),
            )
            connection.execute(
                """
                UPDATE workspaces
                SET active_generation_id = ?, last_sync_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (generation_id, now, now, workspace_id),
            )

        return PublishResult(
            workspace_id=workspace_id,
            generation_id=generation_id,
            sync_run_id=sync_run_id,
            added=counts["added"],
            modified=counts["modified"],
            deleted=counts["deleted"],
            renamed=counts["renamed"],
            unchanged=counts["unchanged"],
            excluded=len(exclusions),
            redacted=sum(1 for resource in resources if resource.redacted_count > 0),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _current_chunk_select() -> str:
        return """
            SELECT r.id AS resource_id, rv.id AS version_id, c.id AS chunk_id,
                   r.relative_path, rv.sha256 AS resource_sha256, rv.sha256 AS sha256,
                   c.text AS content, c.text AS excerpt, c.start_line, c.end_line,
                   c.start_byte, c.end_byte, r.kind, 0 AS stale, r.updated_at,
                   0.5 AS authority, c.token_estimate AS estimated_tokens,
                   c.protected_atoms_json, e.vector_json, e.vector_digest
            FROM resources AS r
            JOIN resource_versions AS rv ON rv.id = r.current_version_id
            JOIN chunks AS c ON c.version_id = rv.id
            JOIN embeddings AS e ON e.chunk_id = c.id
        """

    def list_current_chunks(
        self,
        workspace_id: str,
        *,
        limit: int = 1_000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.require_workspace(workspace_id)
        rows = self.database.rows(
            self._current_chunk_select() + " WHERE r.workspace_id = ? AND r.is_deleted = 0 "
            "ORDER BY r.relative_path, c.ordinal LIMIT ? OFFSET ?",
            (workspace_id, max(0, limit), max(0, offset)),
        )
        return [_row_dict(row) for row in rows]

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE)
        unique_terms = list(dict.fromkeys(term for term in terms if len(term) > 1))[:32]
        return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in unique_terms)

    def search_chunks(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search only current chunks with a parameterized FTS5 expression."""

        self.require_workspace(workspace_id)
        expression = self._fts_query(query)
        if not expression:
            rows = self.list_current_chunks(workspace_id, limit=limit)
            for index, fallback_row in enumerate(rows, start=1):
                fallback_row["rank"] = float(index)
                fallback_row["lexical_score"] = 0.0
            return rows
        fts_rows = self.database.rows(
            """
            SELECT r.id AS resource_id, rv.id AS version_id, c.id AS chunk_id,
                   r.relative_path, rv.sha256 AS resource_sha256, rv.sha256 AS sha256,
                   c.text AS content, c.text AS excerpt, c.start_line, c.end_line,
                   c.start_byte, c.end_byte, r.kind, 0 AS stale, r.updated_at,
                   0.5 AS authority, c.token_estimate AS estimated_tokens,
                   c.protected_atoms_json, e.vector_json, e.vector_digest,
                   bm25(chunk_fts) AS rank
            FROM chunk_fts
            JOIN chunks AS c ON c.rowid = chunk_fts.rowid
            JOIN resource_versions AS rv ON rv.id = c.version_id
            JOIN resources AS r ON r.current_version_id = rv.id
            JOIN embeddings AS e ON e.chunk_id = c.id
            WHERE chunk_fts MATCH ? AND r.workspace_id = ? AND r.is_deleted = 0
            ORDER BY rank, r.relative_path, c.ordinal
            LIMIT ?
            """,
            (expression, workspace_id, max(0, limit)),
        )
        result: list[dict[str, Any]] = []
        for fts_row in fts_rows:
            item = _row_dict(fts_row)
            item["lexical_score"] = 1.0 / (1.0 + abs(float(item["rank"])))
            result.append(item)
        return result

    def get_current_chunk(
        self,
        chunk_id: str,
        *,
        version_id: str | None = None,
    ) -> dict[str, Any] | None:
        parameters: list[Any] = [chunk_id]
        where = " WHERE c.id = ? AND r.current_version_id = c.version_id AND r.is_deleted = 0"
        if version_id is not None:
            where += " AND c.version_id = ?"
            parameters.append(version_id)
        rows = self.database.rows(self._current_chunk_select() + where, parameters)
        return None if not rows else _row_dict(rows[0])

    def get_resource(self, workspace_id: str, relative_path: str) -> dict[str, Any] | None:
        rows = self.database.rows(
            """
            SELECT r.id AS resource_id, r.workspace_id, r.relative_path, r.kind, r.origin,
                   r.is_deleted, r.current_version_id AS version_id, rv.sha256,
                   rv.cas_digest, rv.size_bytes, rv.redacted_count, r.updated_at
            FROM resources AS r
            LEFT JOIN resource_versions AS rv ON rv.id = r.current_version_id
            WHERE r.workspace_id = ? AND r.relative_path = ?
            """,
            (workspace_id, relative_path),
        )
        return None if not rows else _row_dict(rows[0])

    def get_resource_content(self, workspace_id: str, relative_path: str) -> str | None:
        resource = self.get_resource(workspace_id, relative_path)
        if resource is None or resource["is_deleted"]:
            return None
        return self.cas.get_text(str(resource["cas_digest"]))

    def get_resource_version(
        self,
        resource_id: str,
        version_id: str,
    ) -> dict[str, Any] | None:
        """Resolve immutable sanitized content for a stable recovery reference."""

        rows = self.database.rows(
            """
            SELECT r.id AS resource_id, rv.id AS version_id, r.workspace_id,
                   COALESCE(gr.relative_path, r.relative_path) AS relative_path,
                   COALESCE(gr.kind, r.kind) AS kind, rv.sha256, rv.cas_digest,
                   rv.redacted_count, rv.created_at,
                   CASE
                       WHEN r.current_version_id = rv.id AND r.is_deleted = 0 THEN 1
                       ELSE 0
                   END AS current
            FROM resource_versions AS rv
            JOIN resources AS r ON r.id = rv.resource_id
            LEFT JOIN generation_resources AS gr
              ON gr.generation_id = rv.generation_id
             AND gr.resource_id = r.id
             AND gr.version_id = rv.id
            WHERE r.id = ? AND rv.id = ?
            """,
            (resource_id, version_id),
        )
        if not rows:
            return None
        result = _row_dict(rows[0])
        result["current"] = bool(result["current"])
        result["content"] = self.cas.get_text(str(result.pop("cas_digest")))
        return result

    def _ensure_thread(
        self,
        connection: sqlite3.Connection,
        thread_id: str,
        workspace_id: str | None,
        now: str,
        thread_label: str | None = None,
    ) -> None:
        if thread_label is not None and (not thread_label.strip() or len(thread_label) > 120):
            raise ValueError("thread label must contain 1 to 120 characters")
        existing = connection.execute(
            "SELECT workspace_id, label FROM threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO threads(id, workspace_id, label, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (thread_id, workspace_id, thread_label, now, now),
            )
            return
        existing_workspace = existing["workspace_id"]
        if (
            workspace_id is not None
            and existing_workspace is not None
            and str(existing_workspace) != workspace_id
        ):
            raise ThreadWorkspaceConflict(thread_id)
        connection.execute(
            """
            UPDATE threads
            SET workspace_id = COALESCE(workspace_id, ?),
                label = COALESCE(?, label),
                updated_at = ?
            WHERE id = ?
            """,
            (workspace_id, thread_label, now, thread_id),
        )

    def record_hydration_run(
        self,
        *,
        hydration_id: str,
        thread_id: str,
        workspace_id: str,
        request_sha256: str,
        adapter: str,
        requested_mode: str,
        effective_mode: str,
        status: str,
        thread_label: str | None = None,
        generation_id: str | None = None,
        idempotency_key: str | None = None,
        baseline_input_tokens: int | None = None,
        hydrated_input_tokens: int | None = None,
        local_input_tokens: int | None = None,
        local_output_tokens: int | None = None,
        result: Mapping[str, Any] | None = None,
        items: Sequence[Mapping[str, Any]] = (),
        fidelity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record sanitized hydration metadata and cited selections in one transaction."""

        now = _utc_now()
        with self.database.transaction() as connection:
            self._ensure_thread(connection, thread_id, workspace_id, now, thread_label)
            if idempotency_key is not None:
                existing = connection.execute(
                    "SELECT id FROM hydration_runs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    persisted = str(existing["id"])
                    if persisted != hydration_id:
                        raise IdempotencyConflict(
                            "hydration idempotency key was reused for another run"
                        )
                    found = self._get_hydration_run(connection, persisted)
                    if found is None:  # pragma: no cover - same-transaction invariant
                        raise RuntimeError("hydration run disappeared")
                    return found
            connection.execute(
                """
                INSERT INTO hydration_runs(
                    id, idempotency_key, thread_id, workspace_id, generation_id,
                    request_sha256, adapter, requested_mode, effective_mode, status,
                    baseline_input_tokens, hydrated_input_tokens, local_input_tokens,
                    local_output_tokens, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hydration_id,
                    idempotency_key,
                    thread_id,
                    workspace_id,
                    generation_id,
                    request_sha256,
                    adapter,
                    requested_mode,
                    effective_mode,
                    status,
                    baseline_input_tokens,
                    hydrated_input_tokens,
                    local_input_tokens,
                    local_output_tokens,
                    None if result is None else _json(result),
                    now,
                ),
            )
            for ordinal, item in enumerate(items):
                connection.execute(
                    """
                    INSERT INTO hydration_items(
                        id, hydration_id, chunk_id, version_id, ordinal, score_json,
                        selection_reason, citation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        hydration_id,
                        item["chunk_id"],
                        item["version_id"],
                        ordinal,
                        _json(item.get("score", {})),
                        str(item.get("selection_reason", "selected")),
                        _json(item.get("citation", {})),
                    ),
                )
            if fidelity is not None:
                replay_hash = str(fidelity.get("replay_hash", ""))
                if len(replay_hash) != 64:
                    replay_hash = sha256(_json(fidelity).encode("utf-8")).hexdigest()
                connection.execute(
                    """
                    INSERT INTO fidelity_reports(
                        hydration_id, status, requested_mode, effective_mode,
                        replay_hash, report_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hydration_id,
                        str(fidelity.get("status", status)),
                        requested_mode,
                        effective_mode,
                        replay_hash,
                        _json(fidelity),
                        now,
                    ),
                )
            found = self._get_hydration_run(connection, hydration_id)
            if found is None:  # pragma: no cover - same-transaction invariant
                raise RuntimeError("hydration run insert did not persist")
            return found

    @staticmethod
    def _get_hydration_run(
        connection: sqlite3.Connection, hydration_id: str
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM hydration_runs WHERE id = ?", (hydration_id,)
        ).fetchone()
        if row is None:
            return None
        result = _row_dict(row)
        if result["result_json"] is not None:
            result["result"] = json.loads(result.pop("result_json"))
        else:
            result.pop("result_json")
            result["result"] = None
        item_rows = connection.execute(
            "SELECT * FROM hydration_items WHERE hydration_id = ? ORDER BY ordinal",
            (hydration_id,),
        ).fetchall()
        parsed_items: list[dict[str, Any]] = []
        for item_row in item_rows:
            item = _row_dict(item_row)
            item["score"] = json.loads(item["score_json"])
            item["citation"] = json.loads(item["citation_json"])
            parsed_items.append(item)
        result["items"] = parsed_items
        report = connection.execute(
            "SELECT report_json FROM fidelity_reports WHERE hydration_id = ?",
            (hydration_id,),
        ).fetchone()
        result["fidelity"] = None if report is None else json.loads(report["report_json"])
        return result

    def get_hydration_run(self, hydration_id: str) -> dict[str, Any] | None:
        with self.database.connection(readonly=True) as connection:
            return self._get_hydration_run(connection, hydration_id)

    @staticmethod
    def _usage_payload(event: UsageObservation) -> tuple[Any, ...]:
        return (
            event.thread_id,
            event.hydration_id,
            event.provider,
            event.model,
            event.counting_method.value,
            event.actual_input_tokens,
            event.actual_output_tokens,
            event.cached_input_tokens,
            event.reasoning_tokens,
            event.local_input_tokens,
            event.local_output_tokens,
            event.billable_input_tokens,
            event.billable_output_tokens,
            event.verified_baseline_input_tokens,
            event.provider_request_id_hash,
            event.observed_at.isoformat(),
        )

    def record_usage_event(self, event: UsageObservation) -> dict[str, Any]:
        """Insert provider usage once, rejecting conflicting harness retries."""

        now = _utc_now()
        payload = self._usage_payload(event)
        with self.database.transaction() as connection:
            thread = connection.execute(
                "SELECT id FROM threads WHERE id = ?",
                (event.thread_id,),
            ).fetchone()
            if thread is None:
                raise ThreadNotFound(event.thread_id)
            if event.hydration_id is not None:
                hydration = connection.execute(
                    "SELECT thread_id FROM hydration_runs WHERE id = ?",
                    (event.hydration_id,),
                ).fetchone()
                if hydration is None:
                    raise HydrationNotFound(event.hydration_id)
                if str(hydration["thread_id"]) != event.thread_id:
                    raise HydrationThreadMismatch(event.hydration_id)
            existing = connection.execute(
                "SELECT * FROM usage_events WHERE idempotency_key = ?",
                (event.idempotency_key,),
            ).fetchone()
            if existing is not None:
                existing_payload = tuple(
                    existing[column]
                    for column in (
                        "thread_id",
                        "hydration_id",
                        "provider",
                        "model",
                        "counting_method",
                        "actual_input_tokens",
                        "actual_output_tokens",
                        "cached_input_tokens",
                        "reasoning_tokens",
                        "local_input_tokens",
                        "local_output_tokens",
                        "billable_input_tokens",
                        "billable_output_tokens",
                        "verified_baseline_input_tokens",
                        "provider_request_id_hash",
                        "observed_at",
                    )
                )
                if existing_payload != payload:
                    raise IdempotencyConflict(
                        "usage idempotency key was reused for a different observation"
                    )
                result = _row_dict(existing)
                result["inserted"] = False
                return result
            if event.hydration_id is not None:
                existing_hydration_usage = connection.execute(
                    "SELECT id FROM usage_events WHERE hydration_id = ? LIMIT 1",
                    (event.hydration_id,),
                ).fetchone()
                if existing_hydration_usage is not None:
                    raise HydrationUsageConflict(event.hydration_id)
            identifier = str(uuid4())
            try:
                connection.execute(
                    """
                    INSERT INTO usage_events(
                        id, idempotency_key, thread_id, hydration_id, provider, model,
                        counting_method, actual_input_tokens, actual_output_tokens,
                        cached_input_tokens, reasoning_tokens, local_input_tokens,
                        local_output_tokens, billable_input_tokens, billable_output_tokens,
                        verified_baseline_input_tokens,
                        provider_request_id_hash, observed_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (identifier, event.idempotency_key, *payload, now),
                )
            except sqlite3.IntegrityError as error:
                if event.hydration_id is not None:
                    raise HydrationUsageConflict(event.hydration_id) from error
                raise
            connection.execute(
                "UPDATE threads SET updated_at = ? WHERE id = ?",
                (now, event.thread_id),
            )
            inserted = connection.execute(
                "SELECT * FROM usage_events WHERE id = ?", (identifier,)
            ).fetchone()
            if inserted is None:  # pragma: no cover - same-transaction invariant
                raise RuntimeError("usage event insert did not persist")
            result = _row_dict(inserted)
            result["inserted"] = True
            return result

    def list_thread_hydration_rows(self, thread_id: str) -> list[dict[str, Any]]:
        rows = self.database.rows(
            """
            SELECT h.*,
                   EXISTS(
                       SELECT 1 FROM usage_events AS u WHERE u.hydration_id = h.id
                   ) AS usage_recorded
            FROM hydration_runs AS h
            WHERE h.thread_id = ?
            ORDER BY h.created_at, h.id
            """,
            (thread_id,),
        )
        return [_row_dict(row) for row in rows]

    def list_thread_usage_rows(self, thread_id: str) -> list[dict[str, Any]]:
        rows = self.database.rows(
            "SELECT * FROM usage_events WHERE thread_id = ? ORDER BY observed_at, id",
            (thread_id,),
        )
        return [_row_dict(row) for row in rows]

    def thread_aggregate_rows(self, thread_id: str) -> dict[str, list[dict[str, Any]]]:
        """Return immutable low-level rows for confidence-aware token aggregation."""

        return {
            "hydrations": self.list_thread_hydration_rows(thread_id),
            "usage": self.list_thread_usage_rows(thread_id),
        }

    def count_usage_events(self, thread_id: str | None = None) -> int:
        if thread_id is None:
            return int(self.database.scalar("SELECT COUNT(*) FROM usage_events") or 0)
        return int(
            self.database.scalar(
                "SELECT COUNT(*) FROM usage_events WHERE thread_id = ?", (thread_id,)
            )
            or 0
        )

    def dump_publish_result(self, result: PublishResult) -> dict[str, Any]:
        """Return a JSON-ready representation used by thin integration surfaces."""

        return asdict(result)


__all__ = [
    "ChunkInput",
    "ContextRepository",
    "ExclusionInput",
    "HydrationNotFound",
    "HydrationThreadMismatch",
    "HydrationUsageConflict",
    "IdempotencyConflict",
    "InvalidWorkspace",
    "PublishResult",
    "ResourceInput",
    "ThreadNotFound",
    "ThreadWorkspaceConflict",
    "WorkspaceNotFound",
]
