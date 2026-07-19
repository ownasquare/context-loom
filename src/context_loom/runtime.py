"""Composition root shared by the HTTP, CLI, MCP, and proxy surfaces."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from context_loom import __version__
from context_loom.api.contracts import (
    ExportArtifact,
    ExportRequest,
    ReadinessStatus,
    ResourceSummary,
    ResourceVersionContent,
    ThreadSummary,
    TurnSummary,
)
from context_loom.api.errors import ConflictError, ContextLoomError, NotFoundError
from context_loom.application.thread_service import ThreadService
from context_loom.config import Settings
from context_loom.domain.models import (
    HealthStatus,
    HydrateRequest,
    PromptEnvelope,
    SyncReport,
    ThreadTokenSummary,
    UsageObservation,
    WorkspaceCreate,
    WorkspaceRecord,
    WorkspaceStatus,
)
from context_loom.exports import ExportPolicy, export_jsonl, export_parquet
from context_loom.hydration.retrieval import RepositoryRetrievalSource
from context_loom.hydration.service import HydrationService, RepositoryHydrationRunSink
from context_loom.indexing.sync import WorkspaceSynchronizer
from context_loom.storage.cas import ContentAddressedStore
from context_loom.storage.database import Database
from context_loom.storage.migrations import latest_version
from context_loom.storage.repositories import (
    ContextRepository,
    HydrationNotFound,
    HydrationThreadMismatch,
    HydrationUsageConflict,
    IdempotencyConflict,
    InvalidWorkspace,
    ThreadNotFound,
    ThreadWorkspaceConflict,
    WorkspaceNotFound,
)
from context_loom.tokenization.ledger import RepositoryUsageStore, TokenLedger
from context_loom.tokenization.usage import NormalizedUsage


def _sum_known(values: Sequence[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _row_dict(row: Any) -> dict[str, Any]:
    return {str(key): row[key] for key in row.keys()}  # noqa: SIM118 - sqlite Row semantics


class _RuntimeHydrationSink:
    def __init__(self, runtime: ContextLoomRuntime) -> None:
        self._runtime = runtime

    def record_hydration_run(self, envelope: PromptEnvelope) -> None:
        self._runtime._record_hydration(envelope)


class ContextLoomRuntime:
    """Own the canonical local services and implement every public backend protocol."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.prepare()
        self.database = Database(settings.database_path)
        self.repository = ContextRepository(
            self.database,
            ContentAddressedStore(settings.objects_dir),
        )
        self.synchronizer = WorkspaceSynchronizer(
            self.repository,
            max_file_bytes=settings.max_file_bytes,
            max_workspace_files=settings.max_workspace_files,
            chunk_target_tokens=settings.chunk_target_tokens,
            chunk_overlap_tokens=settings.chunk_overlap_tokens,
        )
        self._hydration_cache: OrderedDict[str, tuple[float, PromptEnvelope]] = OrderedDict()
        self._cache_lock = threading.RLock()
        self._metadata_sink = RepositoryHydrationRunSink(self.repository)
        self.thread_service = ThreadService(TokenLedger(RepositoryUsageStore(self.repository)))
        self.hydration_service = HydrationService(
            RepositoryRetrievalSource(self.repository),
            sink=_RuntimeHydrationSink(self),
            allow_outbound=settings.allow_outbound,
            ollama_url=settings.ollama_url,
            ollama_model=settings.ollama_model,
            ollama_timeout_seconds=settings.local_model_timeout_seconds,
        )

    def _record_hydration(self, envelope: PromptEnvelope) -> None:
        if not self.settings.retain_message_content:
            self._metadata_sink.record_hydration_run(envelope)
            self.thread_service.record_hydration(envelope)
            self._remember_hydration(envelope)
            return
        persisted_result = envelope.model_dump(mode="json", exclude_computed_fields=True)
        raw_thread_label = envelope.metadata.get("thread_label")
        thread_label = raw_thread_label if isinstance(raw_thread_label, str) else None
        self.repository.record_hydration_run(
            hydration_id=envelope.hydration_id,
            thread_id=envelope.thread_id,
            workspace_id=envelope.workspace_id,
            generation_id=envelope.snapshot.generation_id,
            request_sha256=hashlib.sha256(envelope.message_exact.encode("utf-8")).hexdigest(),
            adapter=envelope.adapter,
            requested_mode=envelope.fidelity.requested_mode.value,
            effective_mode=envelope.fidelity.effective_mode.value,
            status=envelope.fidelity.status.value,
            thread_label=thread_label,
            baseline_input_tokens=envelope.token_plan.baseline.tokens,
            hydrated_input_tokens=envelope.token_plan.hydrated.tokens,
            local_input_tokens=envelope.token_plan.local_compactor_input_tokens,
            local_output_tokens=envelope.token_plan.local_compactor_output_tokens,
            result=persisted_result,
            items=[
                {
                    "chunk_id": item.citation.chunk_id,
                    "version_id": item.citation.version_id,
                    "score": item.score.model_dump(mode="json"),
                    "selection_reason": item.selection_reason,
                    "citation": item.citation.model_dump(mode="json"),
                }
                for item in envelope.context_items
                if item.citation.chunk_id is not None
            ],
            fidelity=envelope.fidelity.model_dump(mode="json"),
        )
        self.thread_service.record_hydration(envelope)
        self._remember_hydration(envelope)

    def _remember_hydration(self, envelope: PromptEnvelope) -> None:
        now = time.monotonic()
        with self._cache_lock:
            self._prune_hydration_cache(now)
            self._hydration_cache.pop(envelope.hydration_id, None)
            self._hydration_cache[envelope.hydration_id] = (now, envelope)
            while len(self._hydration_cache) > self.settings.hydration_cache_max_entries:
                self._hydration_cache.popitem(last=False)

    def _cached_hydration(self, hydration_id: str) -> PromptEnvelope | None:
        now = time.monotonic()
        with self._cache_lock:
            self._prune_hydration_cache(now)
            entry = self._hydration_cache.get(hydration_id)
            if entry is None:
                return None
            self._hydration_cache.move_to_end(hydration_id)
            return entry[1]

    def _prune_hydration_cache(self, now: float) -> None:
        expired = [
            hydration_id
            for hydration_id, (created_at, _envelope) in self._hydration_cache.items()
            if now - created_at > self.settings.hydration_cache_ttl_seconds
        ]
        for hydration_id in expired:
            self._hydration_cache.pop(hydration_id, None)

    async def health(self) -> HealthStatus:
        try:
            await asyncio.to_thread(self.database.scalar, "SELECT 1")
        except Exception:
            return HealthStatus(
                status="degraded",
                version=__version__,
                database="unavailable",
                local_model="disabled" if not self.settings.allow_outbound else "unavailable",
                outbound_allowed=self.settings.allow_outbound,
                retain_message_content=self.settings.retain_message_content,
            )
        return HealthStatus(
            status="ok",
            version=__version__,
            database="ready",
            local_model="disabled" if not self.settings.allow_outbound else "unavailable",
            outbound_allowed=self.settings.allow_outbound,
            retain_message_content=self.settings.retain_message_content,
        )

    async def readiness(self) -> ReadinessStatus:
        try:
            version = await asyncio.to_thread(
                self.database.scalar,
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations",
            )
            database_status = "ready"
            migrations_current = int(version or 0) == latest_version()
        except Exception:
            database_status = "unavailable"
            migrations_current = False
        local_model = await self._local_model_status()
        return ReadinessStatus(
            status=("ready" if database_status == "ready" and migrations_current else "degraded"),
            database=database_status,
            local_model=local_model,
            migrations_current=migrations_current,
        )

    async def _local_model_status(self) -> str:
        if not self.settings.allow_outbound:
            return "disabled"
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get(f"{self.settings.ollama_url.rstrip('/')}/api/tags")
                response.raise_for_status()
        except (httpx.HTTPError, OSError):
            return "unavailable"
        return "available"

    async def create_workspace(self, request: WorkspaceCreate) -> WorkspaceRecord:
        try:
            return await asyncio.to_thread(
                self.repository.create_workspace,
                request.name,
                request.root_path,
            )
        except InvalidWorkspace as error:
            raise ConflictError("workspace_invalid", str(error)) from error

    async def list_workspaces(self) -> list[WorkspaceRecord]:
        return await asyncio.to_thread(self.repository.list_workspaces)

    async def workspace_status(self, workspace_id: str) -> WorkspaceStatus:
        try:
            return await asyncio.to_thread(self.repository.get_workspace_status, workspace_id)
        except WorkspaceNotFound as error:
            raise NotFoundError("workspace", workspace_id) from error

    async def sync_workspace(self, workspace_id: str) -> SyncReport:
        try:
            result = await asyncio.to_thread(self.synchronizer.sync, workspace_id)
        except WorkspaceNotFound as error:
            raise NotFoundError("workspace", workspace_id) from error
        return SyncReport(
            workspace_id=result.workspace_id,
            generation_id=result.generation_id,
            added=result.added,
            modified=result.modified + result.renamed,
            deleted=result.deleted,
            unchanged=result.unchanged,
            excluded=result.excluded,
            redacted=result.redacted,
            duration_ms=result.duration_ms,
        )

    async def list_resources(self, workspace_id: str) -> list[ResourceSummary]:
        if await asyncio.to_thread(self.repository.get_workspace, workspace_id) is None:
            raise NotFoundError("workspace", workspace_id)
        rows = await asyncio.to_thread(
            self.database.rows,
            """
            SELECT r.id AS resource_id, r.relative_path, r.kind, rv.sha256,
                   rv.id AS version_id, r.updated_at AS changed_at,
                   COALESCE(SUM(c.token_estimate), 0) AS estimated_tokens,
                   COUNT(c.id) AS chunks,
                   COALESCE(
                       (SELECT ce.change_type FROM change_events AS ce
                        WHERE ce.resource_id = r.id
                        ORDER BY ce.created_at DESC, ce.id DESC LIMIT 1),
                       'unchanged'
                   ) AS change_type
            FROM resources AS r
            JOIN resource_versions AS rv ON rv.id = r.current_version_id
            LEFT JOIN chunks AS c ON c.version_id = rv.id
            WHERE r.workspace_id = ? AND r.is_deleted = 0
            GROUP BY r.id, r.relative_path, r.kind, rv.sha256, rv.id, r.updated_at
            ORDER BY r.relative_path
            """,
            (workspace_id,),
        )
        resources: list[ResourceSummary] = []
        for row in rows:
            item = _row_dict(row)
            item["status"] = (
                "changed" if item["change_type"] in {"added", "modified", "renamed"} else "current"
            )
            resources.append(ResourceSummary.model_validate(item))
        return resources

    async def resolve_resource_version(
        self,
        resource_id: str,
        version_id: str,
    ) -> ResourceVersionContent:
        resource = await asyncio.to_thread(
            self.repository.get_resource_version,
            resource_id,
            version_id,
        )
        if resource is None:
            raise NotFoundError("resource_version", f"{resource_id}/{version_id}")
        return ResourceVersionContent.model_validate(resource)

    async def hydrate(self, request: HydrateRequest) -> PromptEnvelope:
        try:
            return await asyncio.to_thread(self.hydration_service.hydrate, request)
        except WorkspaceNotFound as error:
            raise NotFoundError("workspace", request.workspace_id) from error
        except ThreadWorkspaceConflict as error:
            raise ConflictError(
                "thread_workspace_conflict",
                "Thread identifier already belongs to another workspace",
                details={
                    "thread_id": request.thread_id,
                    "workspace_id": request.workspace_id,
                },
            ) from error
        except LookupError as error:
            raise ContextLoomError(
                "workspace_not_synced",
                "The workspace must be synchronized before hydration",
                status_code=409,
                details={"workspace_id": request.workspace_id},
            ) from error

    async def get_hydration(self, hydration_id: str) -> PromptEnvelope:
        cached = self._cached_hydration(hydration_id)
        if cached is not None:
            return cached
        row = await asyncio.to_thread(self.repository.get_hydration_run, hydration_id)
        if row is None:
            raise NotFoundError("hydration", hydration_id)
        result = row.get("result")
        if not isinstance(result, Mapping) or "message_exact" not in result:
            raise ContextLoomError(
                "hydration_content_not_retained",
                "Hydration content was not retained; submit the message again",
                status_code=410,
                details={"hydration_id": hydration_id},
            )
        envelope = PromptEnvelope.model_validate(result)
        self._remember_hydration(envelope)
        return envelope

    async def explain_hydration(self, hydration_id: str) -> dict[str, Any]:
        envelope = await self.get_hydration(hydration_id)
        return {
            "hydration_id": envelope.hydration_id,
            "intent": envelope.intent.model_dump(mode="json"),
            "selected": [
                {
                    "citation": item.citation.model_dump(mode="json"),
                    "score": item.score.model_dump(mode="json"),
                    "selection_reason": item.selection_reason,
                }
                for item in envelope.context_items
            ],
            "omitted": [item.model_dump(mode="json") for item in envelope.omitted_context],
            "fidelity": envelope.fidelity.model_dump(mode="json"),
            "token_plan": envelope.token_plan.model_dump(mode="json"),
        }

    async def record_usage(self, observation: UsageObservation) -> ThreadTokenSummary:
        normalized = NormalizedUsage(
            idempotency_key=observation.idempotency_key,
            thread_id=observation.thread_id,
            hydration_id=observation.hydration_id,
            provider=observation.provider,
            model=observation.model,
            counting_method=observation.counting_method,
            input_tokens=observation.actual_input_tokens,
            output_tokens=observation.actual_output_tokens,
            cached_input_tokens=observation.cached_input_tokens,
            reasoning_tokens=observation.reasoning_tokens,
            local_input_tokens=observation.local_input_tokens,
            local_output_tokens=observation.local_output_tokens,
            billable_input_tokens=observation.billable_input_tokens,
            billable_output_tokens=observation.billable_output_tokens,
            verified_baseline_input_tokens=observation.verified_baseline_input_tokens,
            provider_request_id_hash=observation.provider_request_id_hash,
            observed_at=observation.observed_at,
        )
        try:
            await asyncio.to_thread(self.thread_service.record_usage, normalized)
        except ThreadNotFound as error:
            raise NotFoundError("thread", observation.thread_id) from error
        except HydrationNotFound as error:
            raise NotFoundError("hydration", str(observation.hydration_id)) from error
        except HydrationThreadMismatch as error:
            raise ConflictError(
                "hydration_thread_mismatch",
                "Hydration does not belong to the usage thread",
                details={
                    "hydration_id": observation.hydration_id,
                    "thread_id": observation.thread_id,
                },
            ) from error
        except HydrationUsageConflict as error:
            raise ConflictError(
                "hydration_usage_conflict",
                "Hydration already has a provider usage observation",
                details={"hydration_id": observation.hydration_id},
            ) from error
        except (IdempotencyConflict, ValueError) as error:
            raise ConflictError("usage_idempotency_conflict", str(error)) from error
        return await self.thread_stats(observation.thread_id)

    async def thread_stats(self, thread_id: str) -> ThreadTokenSummary:
        summary = await asyncio.to_thread(self.thread_service.get_summary, thread_id)
        aggregates = await asyncio.to_thread(self.repository.thread_aggregate_rows, thread_id)
        hydrations = aggregates["hydrations"]
        usage = aggregates["usage"]
        hydration_ids = {str(row["id"]) for row in hydrations}
        standalone_usage = [
            row
            for row in usage
            if row.get("hydration_id") is None or str(row["hydration_id"]) not in hydration_ids
        ]
        if not standalone_usage:
            return summary
        turns = summary.turns + len(standalone_usage)
        standalone_inputs = [
            int(row["actual_input_tokens"]) if row.get("actual_input_tokens") is not None else None
            for row in standalone_usage
        ]
        standalone_outputs = [
            int(row["actual_output_tokens"])
            if row.get("actual_output_tokens") is not None
            else None
            for row in standalone_usage
        ]
        standalone_cached = [
            int(row["cached_input_tokens"]) if row.get("cached_input_tokens") is not None else None
            for row in standalone_usage
        ]
        observed_turns = round(summary.actual_usage_completeness * summary.turns) + sum(
            value is not None for value in standalone_inputs
        )
        completeness = observed_turns / turns if turns else 0.0
        actual_input = _sum_known([summary.actual_input_tokens, *standalone_inputs])
        verified_pairs = [
            (int(row["verified_baseline_input_tokens"]), int(row["actual_input_tokens"]))
            for row in standalone_usage
            if row.get("verified_baseline_input_tokens") is not None
            and row.get("actual_input_tokens") is not None
        ]
        standalone_local = sum(
            int(row.get("local_input_tokens") or 0) + int(row.get("local_output_tokens") or 0)
            for row in standalone_usage
        )
        return ThreadTokenSummary(
            thread_id=thread_id,
            turns=turns,
            estimated_baseline_input_tokens=summary.estimated_baseline_input_tokens,
            estimated_hydrated_input_tokens=summary.estimated_hydrated_input_tokens,
            projected_input_tokens_saved=summary.projected_input_tokens_saved,
            actual_input_tokens=actual_input,
            actual_output_tokens=_sum_known([summary.actual_output_tokens, *standalone_outputs]),
            cached_input_tokens=_sum_known([summary.cached_input_tokens, *standalone_cached]),
            local_compactor_tokens=summary.local_compactor_tokens + standalone_local,
            baseline_estimate_adjusted_reduction=None,
            verified_counterfactual_tokens_saved=(
                _sum_known(
                    [
                        summary.verified_counterfactual_tokens_saved,
                        (
                            sum(expected - actual for expected, actual in verified_pairs)
                            if verified_pairs
                            else None
                        ),
                    ]
                )
            ),
            actual_usage_completeness=completeness,
        )

    async def list_threads(self, workspace_id: str | None = None) -> list[ThreadSummary]:
        if workspace_id is None:
            rows = await asyncio.to_thread(
                self.database.rows,
                "SELECT id, label, updated_at FROM threads ORDER BY updated_at DESC, id",
            )
        else:
            rows = await asyncio.to_thread(
                self.database.rows,
                "SELECT id, label, updated_at FROM threads "
                "WHERE workspace_id = ? ORDER BY updated_at DESC, id",
                (workspace_id,),
            )
        return await asyncio.gather(*(self._thread_view(_row_dict(row)) for row in rows))

    async def _thread_view(self, thread_row: Mapping[str, Any]) -> ThreadSummary:
        thread_id = str(thread_row["id"])
        summary, aggregates = await asyncio.gather(
            self.thread_stats(thread_id),
            asyncio.to_thread(self.repository.thread_aggregate_rows, thread_id),
        )
        usage_by_hydration: dict[str, list[dict[str, Any]]] = {}
        for usage in aggregates["usage"]:
            hydration_id = usage.get("hydration_id")
            if hydration_id is not None:
                usage_by_hydration.setdefault(str(hydration_id), []).append(usage)
        history: list[TurnSummary] = []
        for hydration in aggregates["hydrations"]:
            hydration_id = str(hydration["id"])
            observations = usage_by_hydration.get(hydration_id, [])
            actual_values = [
                int(item["actual_input_tokens"])
                if item.get("actual_input_tokens") is not None
                else None
                for item in observations
            ]
            verified_pairs = [
                (int(item["verified_baseline_input_tokens"]), int(item["actual_input_tokens"]))
                for item in observations
                if item.get("verified_baseline_input_tokens") is not None
                and item.get("actual_input_tokens") is not None
            ]
            baseline = int(hydration.get("baseline_input_tokens") or 0)
            hydrated = int(hydration.get("hydrated_input_tokens") or 0)
            history.append(
                TurnSummary(
                    hydration_id=hydration_id,
                    created_at=hydration["created_at"],
                    adapter=str(hydration["adapter"]),
                    effective_mode=str(hydration["effective_mode"]),
                    projected_input_tokens_saved=max(baseline - hydrated, 0),
                    usage_recorded=bool(hydration["usage_recorded"]),
                    actual_input_tokens=_sum_known(actual_values),
                    verified_counterfactual_tokens_saved=(
                        sum(expected - actual for expected, actual in verified_pairs)
                        if verified_pairs
                        else None
                    ),
                    fidelity_status=str(hydration["status"]),
                )
            )
        return ThreadSummary(
            thread_id=summary.thread_id,
            label=str(thread_row.get("label") or summary.thread_id),
            turns=summary.turns,
            updated_at=thread_row["updated_at"],
            estimated_baseline_input_tokens=summary.estimated_baseline_input_tokens,
            estimated_hydrated_input_tokens=summary.estimated_hydrated_input_tokens,
            projected_input_tokens_saved=summary.projected_input_tokens_saved,
            actual_input_tokens=summary.actual_input_tokens,
            actual_output_tokens=summary.actual_output_tokens,
            cached_input_tokens=summary.cached_input_tokens,
            local_compactor_tokens=summary.local_compactor_tokens,
            baseline_estimate_adjusted_reduction=summary.baseline_estimate_adjusted_reduction,
            verified_counterfactual_tokens_saved=summary.verified_counterfactual_tokens_saved,
            actual_usage_completeness=summary.actual_usage_completeness,
            history=history,
        )

    async def create_export(self, request: ExportRequest) -> ExportArtifact:
        records = await asyncio.to_thread(self._export_records, request)
        identifier = str(uuid.uuid4())
        destination = self.settings.exports_dir / f"context-loom-{identifier}.{request.format}"
        policy = ExportPolicy(include_raw_content=request.include_content)
        if request.format == "jsonl":
            result = await asyncio.to_thread(
                export_jsonl,
                records,
                destination,
                policy=policy,
            )
        else:
            result = await asyncio.to_thread(
                export_parquet,
                records,
                destination,
                policy=policy,
            )
        return ExportArtifact(
            id=identifier,
            format=request.format,
            path=result.path,
            sha256=result.sha256,
            rows=result.rows,
            includes_content=request.include_content,
        )

    def _export_records(self, request: ExportRequest) -> list[dict[str, Any]]:
        if request.thread_id is not None and request.workspace_id is not None:
            hydration_query = (
                "SELECT h.*, 'hydration' AS record_type FROM hydration_runs AS h "
                "JOIN threads AS t ON t.id = h.thread_id "
                "WHERE t.id = ? AND t.workspace_id = ? ORDER BY h.created_at, h.id"
            )
            usage_query = (
                "SELECT u.*, 'usage' AS record_type FROM usage_events AS u "
                "JOIN threads AS t ON t.id = u.thread_id "
                "WHERE t.id = ? AND t.workspace_id = ? ORDER BY u.observed_at, u.id"
            )
            parameters = [request.thread_id, request.workspace_id]
        elif request.thread_id is not None:
            hydration_query = (
                "SELECT h.*, 'hydration' AS record_type FROM hydration_runs AS h "
                "JOIN threads AS t ON t.id = h.thread_id "
                "WHERE t.id = ? ORDER BY h.created_at, h.id"
            )
            usage_query = (
                "SELECT u.*, 'usage' AS record_type FROM usage_events AS u "
                "JOIN threads AS t ON t.id = u.thread_id "
                "WHERE t.id = ? ORDER BY u.observed_at, u.id"
            )
            parameters = [request.thread_id]
        elif request.workspace_id is not None:
            hydration_query = (
                "SELECT h.*, 'hydration' AS record_type FROM hydration_runs AS h "
                "JOIN threads AS t ON t.id = h.thread_id "
                "WHERE t.workspace_id = ? ORDER BY h.created_at, h.id"
            )
            usage_query = (
                "SELECT u.*, 'usage' AS record_type FROM usage_events AS u "
                "JOIN threads AS t ON t.id = u.thread_id "
                "WHERE t.workspace_id = ? ORDER BY u.observed_at, u.id"
            )
            parameters = [request.workspace_id]
        else:
            hydration_query = (
                "SELECT h.*, 'hydration' AS record_type FROM hydration_runs AS h "
                "JOIN threads AS t ON t.id = h.thread_id ORDER BY h.created_at, h.id"
            )
            usage_query = (
                "SELECT u.*, 'usage' AS record_type FROM usage_events AS u "
                "JOIN threads AS t ON t.id = u.thread_id ORDER BY u.observed_at, u.id"
            )
            parameters = []
        hydration_rows = self.database.rows(hydration_query, parameters)
        usage_rows = self.database.rows(usage_query, parameters)
        records = [_row_dict(row) for row in (*hydration_rows, *usage_rows)]
        for record in records:
            raw_result = record.pop("result_json", None)
            if request.include_content and isinstance(raw_result, str):
                record["result"] = json.loads(raw_result)
        return records


def build_runtime(settings: Settings) -> ContextLoomRuntime:
    """Named factory used by entrypoints and third-party embedders."""

    return ContextLoomRuntime(settings)


__all__ = ["ContextLoomRuntime", "build_runtime"]
