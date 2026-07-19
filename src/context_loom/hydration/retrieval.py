"""Storage-neutral retrieval contracts and deterministic local retrieval helpers."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import Field, field_validator

from context_loom.domain.models import ProjectSnapshot, ResourceKind, StrictModel

_TERM_RE = re.compile(r"[A-Za-z0-9_]+")
_VECTOR_DIMENSIONS = 96


class RetrievalCandidate(StrictModel):
    """A current sanitized chunk that can participate in explainable ranking."""

    resource_id: str
    version_id: str
    chunk_id: str
    relative_path: str
    resource_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    kind: ResourceKind = ResourceKind.OTHER
    stale: bool = False
    estimated_tokens: int = Field(default=0, ge=0)
    lexical_score: float = Field(default=0.0, ge=0.0, le=1.0)
    dense_score: float = Field(default=0.0, ge=0.0, le=1.0)
    authority_score: float | None = Field(default=None, ge=0.0, le=1.0)
    recency_score: float = Field(default=0.5, ge=0.0, le=1.0)
    thread_affinity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    direct_match: bool = False
    direct_match_reason: str | None = None

    @field_validator("end_line")
    @classmethod
    def validate_end_line(cls, value: int, info: Any) -> int:
        start = info.data.get("start_line")
        if isinstance(start, int) and value < start:
            raise ValueError("end_line must be greater than or equal to start_line")
        return value

    @property
    def key(self) -> tuple[str, str]:
        return self.version_id, self.chunk_id


@runtime_checkable
class RetrievalSource(Protocol):
    """Dependency contract the root container must provide to ``HydrationService``.

    Returned chunks must belong to the active generation, must already be sanitized, and must not
    include tombstoned or security-excluded resources.
    """

    def get_snapshot(self, workspace_id: str) -> ProjectSnapshot:
        """Return the active immutable workspace snapshot."""

    def search_lexical(
        self, workspace_id: str, terms: Sequence[str], limit: int
    ) -> Sequence[RetrievalCandidate]:
        """Return FTS/BM25-ready matches with normalized ``lexical_score`` values."""

    def search_vector(
        self, workspace_id: str, query: str, limit: int
    ) -> Sequence[RetrievalCandidate]:
        """Return vector matches with normalized ``dense_score`` values."""

    def resolve_direct_references(
        self,
        workspace_id: str,
        paths: Sequence[str],
        symbols: Sequence[str],
        limit: int,
    ) -> Sequence[RetrievalCandidate]:
        """Resolve only safe indexed paths/symbols and mark them as direct matches."""


class ContextRepositoryLike(Protocol):
    """Narrow structural contract for the storage repository adapter."""

    def get_workspace_status(self, workspace_id: str) -> Any:
        """Return a status object or mapping with active generation counts."""

    def search_chunks(self, workspace_id: str, query: str, *, limit: int = 20) -> Sequence[Any]:
        """Return current FTS result rows."""

    def list_current_chunks(
        self, workspace_id: str, *, limit: int = 1_000, offset: int = 0
    ) -> Sequence[Any]:
        """Return all current sanitized chunk rows."""


def _terms(text: str) -> list[str]:
    return [term.casefold() for term in _TERM_RE.findall(text)]


def _hashed_vector(text: str) -> tuple[float, ...]:
    counts = Counter(_terms(text))
    vector = [0.0] * _VECTOR_DIMENSIONS
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % _VECTOR_DIMENSIONS
        direction = 1.0 if digest[4] & 1 else -1.0
        vector[index] += direction * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(value / norm for value in vector)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    raw = sum(a * b for a, b in zip(left, right, strict=True))
    return max(0.0, min(raw, 1.0))


def _normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


class InMemoryRetrievalSource:
    """Deterministic retrieval source for tests, demos, and repository-independent use."""

    def __init__(self, snapshot: ProjectSnapshot, candidates: Sequence[RetrievalCandidate]) -> None:
        self._snapshot = snapshot
        self._candidates = tuple(candidates)

    def get_snapshot(self, workspace_id: str) -> ProjectSnapshot:
        if workspace_id != self._snapshot.workspace_id:
            raise KeyError(f"unknown workspace: {workspace_id}")
        return self._snapshot

    def search_lexical(
        self, workspace_id: str, terms: Sequence[str], limit: int
    ) -> Sequence[RetrievalCandidate]:
        self.get_snapshot(workspace_id)
        query_counts = Counter(term.casefold() for term in terms if term)
        scored: list[RetrievalCandidate] = []
        for candidate in self._candidates:
            document_counts = Counter(_terms(f"{candidate.relative_path} {candidate.excerpt}"))
            overlap = sum(min(count, document_counts[term]) for term, count in query_counts.items())
            denominator = max(sum(query_counts.values()), 1)
            score = min(overlap / denominator, 1.0)
            if score > 0:
                scored.append(candidate.model_copy(update={"lexical_score": score}))
        return sorted(
            scored,
            key=lambda item: (-item.lexical_score, item.relative_path, item.chunk_id),
        )[:limit]

    def search_vector(
        self, workspace_id: str, query: str, limit: int
    ) -> Sequence[RetrievalCandidate]:
        self.get_snapshot(workspace_id)
        query_vector = _hashed_vector(query)
        scored = [
            candidate.model_copy(
                update={"dense_score": _cosine(query_vector, _hashed_vector(candidate.excerpt))}
            )
            for candidate in self._candidates
        ]
        return sorted(
            scored,
            key=lambda item: (-item.dense_score, item.relative_path, item.chunk_id),
        )[:limit]

    def resolve_direct_references(
        self,
        workspace_id: str,
        paths: Sequence[str],
        symbols: Sequence[str],
        limit: int,
    ) -> Sequence[RetrievalCandidate]:
        self.get_snapshot(workspace_id)
        normalized_paths = {_normalize_path(path) for path in paths}
        symbol_set = set(symbols)
        resolved: list[RetrievalCandidate] = []
        for candidate in self._candidates:
            reason: str | None = None
            if _normalize_path(candidate.relative_path) in normalized_paths:
                reason = "explicit_path"
            elif any(
                re.search(rf"(?<!\w){re.escape(symbol)}(?!\w)", candidate.excerpt)
                for symbol in symbol_set
            ):
                reason = "explicit_symbol"
            if reason is not None:
                resolved.append(
                    candidate.model_copy(
                        update={"direct_match": True, "direct_match_reason": reason}
                    )
                )
        return sorted(
            resolved,
            key=lambda item: (item.relative_path, item.start_line, item.chunk_id),
        )[:limit]


def _row_value(row: Any, *names: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        for name in names:
            if name in row:
                return row[name]
        return default
    for name in names:
        if hasattr(row, name):
            return getattr(row, name)
    return default


def _normalized_search_score(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    numeric = float(value)
    if 0.0 <= numeric <= 1.0:
        return numeric
    return 1.0 / (1.0 + abs(numeric))


def _candidate_from_row(row: Any, *, lexical: bool = False) -> RetrievalCandidate:
    excerpt = str(_row_value(row, "excerpt", "content", "text", default=""))
    sha = _row_value(row, "resource_sha256", "sha256", "content_sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        sha = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    kind_value = _row_value(row, "kind", "resource_kind", default=ResourceKind.OTHER)
    try:
        kind = kind_value if isinstance(kind_value, ResourceKind) else ResourceKind(str(kind_value))
    except ValueError:
        kind = ResourceKind.OTHER
    lexical_score = _normalized_search_score(
        _row_value(row, "lexical_score", "score", "rank", default=0.0)
    )
    return RetrievalCandidate(
        resource_id=str(_row_value(row, "resource_id")),
        version_id=str(_row_value(row, "version_id")),
        chunk_id=str(_row_value(row, "chunk_id", "id")),
        relative_path=str(_row_value(row, "relative_path", "path")),
        resource_sha256=sha,
        excerpt=excerpt,
        start_line=int(_row_value(row, "start_line", default=1)),
        end_line=int(_row_value(row, "end_line", default=1)),
        kind=kind,
        stale=bool(_row_value(row, "stale", default=False)),
        estimated_tokens=max(
            int(_row_value(row, "estimated_tokens", "token_estimate", default=0)), 0
        ),
        lexical_score=lexical_score if lexical else 0.0,
        authority_score=_row_value(row, "authority", "authority_score"),
        recency_score=float(_row_value(row, "recency_score", default=0.5)),
        thread_affinity_score=float(_row_value(row, "thread_affinity_score", default=0.0)),
    )


class RepositoryRetrievalSource:
    """Adapt the canonical storage repository without importing storage implementation types."""

    def __init__(self, repository: ContextRepositoryLike) -> None:
        self._repository = repository

    def get_snapshot(self, workspace_id: str) -> ProjectSnapshot:
        status = self._repository.get_workspace_status(workspace_id)
        workspace = _row_value(status, "workspace", default={})
        generation_id = _row_value(status, "active_generation_id", "generation_id")
        if not generation_id:
            raise LookupError(f"workspace has no active generation: {workspace_id}")
        generated_at = _row_value(status, "generated_at", "last_sync_at")
        if not isinstance(generated_at, datetime):
            generated_at = datetime.now(UTC)
        return ProjectSnapshot(
            workspace_id=workspace_id,
            generation_id=str(generation_id),
            root_name=str(_row_value(workspace, "name", default=workspace_id)),
            indexed_resources=int(_row_value(status, "indexed_resources", default=0)),
            changed_resources=int(_row_value(status, "changed_resources", default=0)),
            generated_at=generated_at,
        )

    def search_lexical(
        self, workspace_id: str, terms: Sequence[str], limit: int
    ) -> Sequence[RetrievalCandidate]:
        query = " ".join(dict.fromkeys(term for term in terms if term))
        if not query:
            return []
        return [
            _candidate_from_row(row, lexical=True)
            for row in self._repository.search_chunks(workspace_id, query, limit=limit)
        ]

    def _all_candidates(self, workspace_id: str) -> list[RetrievalCandidate]:
        rows: list[Any] = []
        page_size = 1_000
        offset = 0
        while True:
            page = list(
                self._repository.list_current_chunks(workspace_id, limit=page_size, offset=offset)
            )
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return [_candidate_from_row(row) for row in rows]

    def search_vector(
        self, workspace_id: str, query: str, limit: int
    ) -> Sequence[RetrievalCandidate]:
        memory = InMemoryRetrievalSource(
            self.get_snapshot(workspace_id), self._all_candidates(workspace_id)
        )
        return memory.search_vector(workspace_id, query, limit)

    def resolve_direct_references(
        self,
        workspace_id: str,
        paths: Sequence[str],
        symbols: Sequence[str],
        limit: int,
    ) -> Sequence[RetrievalCandidate]:
        memory = InMemoryRetrievalSource(
            self.get_snapshot(workspace_id), self._all_candidates(workspace_id)
        )
        return memory.resolve_direct_references(workspace_id, paths, symbols, limit)


def collect_candidates(
    source: RetrievalSource,
    *,
    workspace_id: str,
    query: str,
    terms: Sequence[str],
    paths: Sequence[str],
    symbols: Sequence[str],
    limit_per_channel: int = 40,
) -> list[RetrievalCandidate]:
    """Fuse lexical, vector, and direct channels without losing channel score evidence."""

    merged: dict[tuple[str, str], RetrievalCandidate] = {}
    channels = (
        source.search_lexical(workspace_id, terms, limit_per_channel),
        source.search_vector(workspace_id, query, limit_per_channel),
        source.resolve_direct_references(
            workspace_id, paths, symbols, max(limit_per_channel, len(paths) * 3 + len(symbols))
        ),
    )
    for channel in channels:
        for candidate in channel:
            existing = merged.get(candidate.key)
            if existing is None:
                merged[candidate.key] = candidate
                continue
            merged[candidate.key] = existing.model_copy(
                update={
                    "lexical_score": max(existing.lexical_score, candidate.lexical_score),
                    "dense_score": max(existing.dense_score, candidate.dense_score),
                    "direct_match": existing.direct_match or candidate.direct_match,
                    "direct_match_reason": (
                        candidate.direct_match_reason or existing.direct_match_reason
                    ),
                }
            )
    return list(merged.values())
