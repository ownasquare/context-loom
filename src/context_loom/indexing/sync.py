"""Atomic, incremental workspace synchronization service."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from context_loom.collectors.base import VirtualResource
from context_loom.collectors.files import FileCollector
from context_loom.collectors.git import collect_git_metadata
from context_loom.collectors.tools import collect_tool_catalogs
from context_loom.domain.models import WorkspaceStatus
from context_loom.indexing.chunker import chunk_text, chunker_fingerprint
from context_loom.indexing.classifier import classify_resource, parser_fingerprint
from context_loom.indexing.redaction import redact_secrets
from context_loom.indexing.scanner import ScannedFile
from context_loom.storage.repositories import (
    ChunkInput,
    ContextRepository,
    ExclusionInput,
    PublishResult,
    ResourceInput,
)


@dataclass(frozen=True, slots=True)
class WorkspaceSyncResult:
    """Full sync accounting, including rename reuse not present in the wire v1 model."""

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


class WorkspaceSynchronizer:
    """Compile a filesystem snapshot and publish it in one repository transaction."""

    def __init__(
        self,
        repository: ContextRepository,
        *,
        max_file_bytes: int = 2_000_000,
        max_workspace_files: int = 50_000,
        chunk_target_tokens: int = 320,
        chunk_overlap_tokens: int = 40,
    ) -> None:
        self.repository = repository
        self.max_file_bytes = max_file_bytes
        self.max_workspace_files = max_workspace_files
        self.chunk_target_tokens = chunk_target_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens

    def _resource_from_file(self, file: ScannedFile) -> ResourceInput:
        return self._resource(
            relative_path=file.relative_path,
            content=file.content,
            kind=classify_resource(file.relative_path),
            origin="file",
            mtime_ns=file.mtime_ns,
            inode=file.inode,
            device=file.device,
            redacted_count=file.redacted_count,
        )

    def _resource_from_virtual(self, resource: VirtualResource) -> ResourceInput:
        redacted = redact_secrets(resource.content)
        return self._resource(
            relative_path=resource.relative_path,
            content=redacted.text,
            kind=resource.kind,
            origin=resource.origin,
            mtime_ns=None,
            inode=None,
            device=None,
            redacted_count=redacted.count,
        )

    def _resource(
        self,
        *,
        relative_path: str,
        content: str,
        kind: str,
        origin: str,
        mtime_ns: int | None,
        inode: int | None,
        device: int | None,
        redacted_count: int,
    ) -> ResourceInput:
        path = PurePosixPath(relative_path)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("collector produced an unsafe relative path")
        encoded = content.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        cas_digest = self.repository.cas.put(encoded)
        if cas_digest != digest:  # pragma: no cover - CAS address invariant
            raise RuntimeError("content-addressed store returned a mismatched digest")
        chunks = chunk_text(
            content,
            relative_path,
            target_tokens=self.chunk_target_tokens,
            overlap_tokens=self.chunk_overlap_tokens,
        )
        return ResourceInput(
            relative_path=relative_path,
            kind=kind,
            origin=origin,
            sha256=digest,
            cas_digest=cas_digest,
            size_bytes=len(encoded),
            mtime_ns=mtime_ns,
            inode=inode,
            device=device,
            redacted_count=redacted_count,
            parser_fingerprint=parser_fingerprint(relative_path),
            chunker_fingerprint=chunker_fingerprint(
                target_tokens=self.chunk_target_tokens,
                overlap_tokens=self.chunk_overlap_tokens,
            ),
            chunks=tuple(
                ChunkInput(
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    content_sha256=chunk.content_sha256,
                    start_byte=chunk.start_byte,
                    end_byte=chunk.end_byte,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    token_estimate=chunk.token_estimate,
                    protected_atoms=chunk.protected_atoms,
                    embedding=chunk.embedding,
                    embedding_digest=chunk.embedding_digest,
                )
                for chunk in chunks
            ),
        )

    @staticmethod
    def _source_fingerprint(
        resources: tuple[ResourceInput, ...], exclusions: tuple[ExclusionInput, ...]
    ) -> str:
        digest = hashlib.sha256()
        for resource in sorted(resources, key=lambda item: item.relative_path):
            digest.update(resource.relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(resource.sha256.encode("ascii"))
            digest.update(b"\0")
            digest.update(resource.kind.encode("utf-8"))
            digest.update(b"\0")
            digest.update(resource.parser_fingerprint.encode("utf-8"))
            digest.update(b"\0")
            digest.update(resource.chunker_fingerprint.encode("utf-8"))
            digest.update(b"\0")
        for exclusion in sorted(exclusions, key=lambda item: (item.relative_path, item.reason)):
            digest.update(exclusion.relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(exclusion.reason.encode("utf-8"))
            digest.update(b"\1" if exclusion.preserve_existing else b"\0")
        return digest.hexdigest()

    def sync(self, workspace_id: str) -> WorkspaceSyncResult:
        """Scan, sanitize, derive, and atomically publish the next generation."""

        started = time.perf_counter()
        workspace = self.repository.require_workspace(workspace_id)
        root = Path(workspace.root_path)
        batch = FileCollector(
            root,
            max_file_bytes=self.max_file_bytes,
            max_files=self.max_workspace_files,
        ).collect()
        inputs = [self._resource_from_file(file) for file in batch.files]
        virtual = list(collect_tool_catalogs(batch.files))
        git_metadata = collect_git_metadata(root)
        if git_metadata is not None:
            virtual.append(git_metadata)
        inputs.extend(self._resource_from_virtual(resource) for resource in virtual)
        inputs_tuple = tuple(sorted(inputs, key=lambda item: item.relative_path))
        exclusions = tuple(
            ExclusionInput(
                relative_path=item.relative_path,
                reason=item.reason,
                preserve_existing=item.preserve_existing,
            )
            for item in batch.exclusions
        )
        duration_ms = (time.perf_counter() - started) * 1_000
        published: PublishResult = self.repository.publish_generation(
            workspace_id,
            inputs_tuple,
            exclusions,
            source_fingerprint=self._source_fingerprint(inputs_tuple, exclusions),
            duration_ms=duration_ms,
        )
        return WorkspaceSyncResult(
            workspace_id=published.workspace_id,
            generation_id=published.generation_id,
            sync_run_id=published.sync_run_id,
            added=published.added,
            modified=published.modified,
            deleted=published.deleted,
            renamed=published.renamed,
            unchanged=published.unchanged,
            excluded=published.excluded,
            redacted=published.redacted,
            duration_ms=published.duration_ms,
        )

    def status(self, workspace_id: str) -> WorkspaceStatus:
        """Expose repository status without duplicating storage reads."""

        return self.repository.get_workspace_status(workspace_id)

    synchronize = sync
