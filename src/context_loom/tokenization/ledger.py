"""Immutable, idempotent per-turn accounting and confidence-separated aggregates."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Protocol, runtime_checkable

from pydantic import ConfigDict, Field

from context_loom.domain.models import (
    CountingMethod,
    PromptEnvelope,
    StrictModel,
    ThreadTokenSummary,
    TokenEstimate,
    UsageObservation,
)
from context_loom.tokenization.estimators import estimate_tokens
from context_loom.tokenization.usage import NormalizedUsage


class TurnTokenRecord(StrictModel):
    """Frozen accounting evidence for exactly one chat turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str
    thread_id: str
    hydration_id: str | None = None
    baseline: TokenEstimate
    hydrated: TokenEstimate
    usage: NormalizedUsage | None = None
    local_compactor_input_tokens: int = Field(default=0, ge=0)
    local_compactor_output_tokens: int = Field(default=0, ge=0)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ThreadLedgerReport(StrictModel):
    """Thread summary plus separately labeled accuracy and billable evidence."""

    summary: ThreadTokenSummary
    estimate_error_input_tokens: int | None = None
    provider_observed_total_tokens: int | None = Field(default=None, ge=0)
    billable_input_tokens: int | None = Field(default=None, ge=0)
    billable_output_tokens: int | None = Field(default=None, ge=0)


@runtime_checkable
class UsageStore(Protocol):
    """Persistence contract the root container must supply to ``TokenLedger``.

    ``append_turn`` must atomically insert by idempotency key and return ``False`` for an existing
    key. ``get_turn`` and ``list_turns`` must return immutable ``TurnTokenRecord`` values in stable
    recorded order. Implementations must never silently replace an existing record.
    """

    def append_turn(self, record: TurnTokenRecord) -> bool:
        """Insert once and return whether the record was newly stored."""

    def get_turn(self, idempotency_key: str) -> TurnTokenRecord | None:
        """Read one immutable record by its global idempotency key."""

    def list_turns(self, thread_id: str) -> Sequence[TurnTokenRecord]:
        """List immutable records for one thread in recorded order."""

    def append_usage(self, usage: NormalizedUsage) -> bool:
        """Append one later provider observation by its own idempotency key."""

    def get_usage(self, idempotency_key: str) -> NormalizedUsage | None:
        """Read one immutable provider observation."""

    def list_usage(self, thread_id: str) -> Sequence[NormalizedUsage]:
        """List later observations for one thread in observed order."""


class InMemoryUsageStore:
    """Thread-safe usage store for tests and single-process demos."""

    def __init__(self) -> None:
        self._records: dict[str, TurnTokenRecord] = {}
        self._order: list[str] = []
        self._usage: dict[str, NormalizedUsage] = {}
        self._usage_order: list[str] = []
        self._lock = RLock()

    def append_turn(self, record: TurnTokenRecord) -> bool:
        with self._lock:
            if record.idempotency_key in self._records:
                return False
            self._records[record.idempotency_key] = record
            self._order.append(record.idempotency_key)
            return True

    def get_turn(self, idempotency_key: str) -> TurnTokenRecord | None:
        with self._lock:
            return self._records.get(idempotency_key)

    def list_turns(self, thread_id: str) -> Sequence[TurnTokenRecord]:
        with self._lock:
            return tuple(
                self._records[key]
                for key in self._order
                if self._records[key].thread_id == thread_id
            )

    def append_usage(self, usage: NormalizedUsage) -> bool:
        with self._lock:
            if usage.idempotency_key in self._usage:
                return False
            self._usage[usage.idempotency_key] = usage
            self._usage_order.append(usage.idempotency_key)
            return True

    def get_usage(self, idempotency_key: str) -> NormalizedUsage | None:
        with self._lock:
            return self._usage.get(idempotency_key)

    def list_usage(self, thread_id: str) -> Sequence[NormalizedUsage]:
        with self._lock:
            return tuple(
                self._usage[key]
                for key in self._usage_order
                if self._usage[key].thread_id == thread_id
            )


class UsageHistoryRepository(Protocol):
    """Canonical repository methods consumed by ``RepositoryUsageStore``."""

    def record_usage_event(self, event: UsageObservation) -> Mapping[str, Any]:
        """Append one idempotent provider observation."""

    def list_thread_hydration_rows(self, thread_id: str) -> Sequence[Mapping[str, Any]]:
        """Read persisted hydration estimates for a thread."""

    def list_thread_usage_rows(self, thread_id: str) -> Sequence[Mapping[str, Any]]:
        """Read persisted usage observations for a thread."""


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(UTC)


def _stored_token_estimate(
    row: Mapping[str, Any], result: Mapping[str, Any], tier: str
) -> TokenEstimate:
    token_plan = result.get("token_plan")
    if isinstance(token_plan, Mapping):
        estimate = token_plan.get(tier)
        if isinstance(estimate, Mapping):
            return TokenEstimate.model_validate(estimate)
    tokens = row.get(f"{tier}_input_tokens")
    return TokenEstimate(
        tokens=int(tokens) if isinstance(tokens, int) else 0,
        method=CountingMethod.ROUGH_ESTIMATE,
        tokenizer="stored-count-profile-unavailable",
        tokenizer_version="repository-v1",
        confidence=0.0,
    )


def _result_mapping(row: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = row.get("result")
    if isinstance(direct, Mapping):
        return direct
    encoded = row.get("result_json")
    if isinstance(encoded, str):
        decoded = json.loads(encoded)
        if isinstance(decoded, Mapping):
            return decoded
    return {}


class RepositoryUsageStore:
    """Join canonical hydration and usage rows into immutable ledger evidence.

    Hydration estimates are written by ``RepositoryHydrationRunSink``. This store validates those
    rows on ``append_turn`` and writes only the later ``UsageObservation``. A fresh instance can
    reconstruct lifetime thread accounting after process restart.
    """

    def __init__(self, repository: UsageHistoryRepository) -> None:
        self._repository = repository
        self._turn_cache: dict[str, TurnTokenRecord] = {}
        self._usage_cache: dict[str, NormalizedUsage] = {}

    def append_turn(self, record: TurnTokenRecord) -> bool:
        if record.idempotency_key in self._turn_cache:
            return False
        if record.hydration_id is None:
            raise ValueError("repository-backed estimates require a hydration_id")
        rows = self._repository.list_thread_hydration_rows(record.thread_id)
        row = next((item for item in rows if item.get("id") == record.hydration_id), None)
        if row is None:
            raise LookupError("hydration estimate must be persisted before ledger association")
        if (
            row.get("baseline_input_tokens") != record.baseline.tokens
            or row.get("hydrated_input_tokens") != record.hydrated.tokens
        ):
            raise ValueError("turn estimates differ from the canonical hydration row")
        self._turn_cache[record.idempotency_key] = record
        return True

    def get_turn(self, idempotency_key: str) -> TurnTokenRecord | None:
        return self._turn_cache.get(idempotency_key)

    def list_turns(self, thread_id: str) -> Sequence[TurnTokenRecord]:
        records: list[TurnTokenRecord] = []
        for row in self._repository.list_thread_hydration_rows(thread_id):
            result = _result_mapping(row)
            hydration_id = str(row["id"])
            records.append(
                TurnTokenRecord(
                    idempotency_key=str(row.get("idempotency_key") or hydration_id),
                    thread_id=thread_id,
                    hydration_id=hydration_id,
                    baseline=_stored_token_estimate(row, result, "baseline"),
                    hydrated=_stored_token_estimate(row, result, "hydrated"),
                    local_compactor_input_tokens=int(row.get("local_input_tokens") or 0),
                    local_compactor_output_tokens=int(row.get("local_output_tokens") or 0),
                    recorded_at=_datetime(row.get("created_at")),
                )
            )
        return tuple(records)

    def append_usage(self, usage: NormalizedUsage) -> bool:
        result = self._repository.record_usage_event(usage.to_observation())
        self._usage_cache[usage.idempotency_key] = usage
        return bool(result.get("inserted", True))

    def get_usage(self, idempotency_key: str) -> NormalizedUsage | None:
        return self._usage_cache.get(idempotency_key)

    def list_usage(self, thread_id: str) -> Sequence[NormalizedUsage]:
        return tuple(
            NormalizedUsage(
                idempotency_key=str(row["idempotency_key"]),
                thread_id=str(row["thread_id"]),
                hydration_id=(
                    str(row["hydration_id"]) if row.get("hydration_id") is not None else None
                ),
                provider=str(row["provider"]),
                model=str(row["model"]),
                counting_method=CountingMethod(str(row["counting_method"])),
                input_tokens=row.get("actual_input_tokens"),
                output_tokens=row.get("actual_output_tokens"),
                cached_input_tokens=row.get("cached_input_tokens"),
                reasoning_tokens=row.get("reasoning_tokens"),
                local_input_tokens=row.get("local_input_tokens"),
                local_output_tokens=row.get("local_output_tokens"),
                billable_input_tokens=row.get("billable_input_tokens"),
                billable_output_tokens=row.get("billable_output_tokens"),
                verified_baseline_input_tokens=row.get("verified_baseline_input_tokens"),
                provider_request_id_hash=row.get("provider_request_id_hash"),
                observed_at=_datetime(row.get("observed_at")),
            )
            for row in self._repository.list_thread_usage_rows(thread_id)
        )


class IdempotencyConflictError(ValueError):
    """An idempotency key was reused for different immutable evidence."""


def _evidence_payload(record: TurnTokenRecord) -> dict[str, Any]:
    payload = record.model_dump()
    payload.pop("recorded_at", None)
    usage = payload.get("usage")
    if isinstance(usage, dict):
        usage.pop("observed_at", None)
    return payload


def _usage_evidence_payload(usage: NormalizedUsage) -> dict[str, Any]:
    payload = usage.model_dump()
    payload.pop("observed_at", None)
    return payload


def _join_later_usage(
    records: Sequence[TurnTokenRecord], usage_events: Sequence[NormalizedUsage]
) -> list[TurnTokenRecord]:
    by_hydration = {
        usage.hydration_id: usage for usage in usage_events if usage.hydration_id is not None
    }
    by_idempotency = {usage.idempotency_key: usage for usage in usage_events}
    return [
        record.model_copy(
            update={
                "usage": (
                    by_hydration.get(record.hydration_id)
                    if record.hydration_id is not None
                    else None
                )
                or by_idempotency.get(record.idempotency_key)
                or record.usage
            }
        )
        for record in records
    ]


def _sum_known(values: Sequence[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def build_thread_report(
    records: Sequence[TurnTokenRecord], *, thread_id: str | None = None
) -> ThreadLedgerReport:
    """Aggregate without moving a number between projected, observed, or verified tiers."""

    resolved_thread_id = thread_id or (records[0].thread_id if records else "")
    if any(record.thread_id != resolved_thread_id for record in records):
        raise ValueError("all records must belong to the same thread")
    baseline = sum(record.baseline.tokens for record in records)
    hydrated = sum(record.hydrated.tokens for record in records)
    actual_inputs = [record.usage.input_tokens if record.usage else None for record in records]
    actual_outputs = [record.usage.output_tokens if record.usage else None for record in records]
    cached_inputs = [
        record.usage.cached_input_tokens if record.usage else None for record in records
    ]
    actual_input = _sum_known(actual_inputs)
    actual_output = _sum_known(actual_outputs)
    completeness = (
        sum(value is not None for value in actual_inputs) / len(records) if records else 0.0
    )
    local_tokens = sum(
        (
            record.local_compactor_input_tokens
            or (record.usage.local_input_tokens if record.usage else None)
            or 0
        )
        + (
            record.local_compactor_output_tokens
            or (record.usage.local_output_tokens if record.usage else None)
            or 0
        )
        for record in records
    )
    verified_pairs = [
        (record.usage.verified_baseline_input_tokens, record.usage.input_tokens)
        for record in records
        if record.usage
        and record.usage.verified_baseline_input_tokens is not None
        and record.usage.input_tokens is not None
    ]
    verified_savings = (
        sum(verified - actual for verified, actual in verified_pairs) if verified_pairs else None
    )
    fully_observed = bool(records) and completeness == 1.0
    adjusted_reduction = (
        baseline - actual_input if fully_observed and actual_input is not None else None
    )
    estimate_error = (
        actual_input - hydrated if fully_observed and actual_input is not None else None
    )
    summary = ThreadTokenSummary(
        thread_id=resolved_thread_id,
        turns=len(records),
        estimated_baseline_input_tokens=baseline,
        estimated_hydrated_input_tokens=hydrated,
        projected_input_tokens_saved=sum(
            max(record.baseline.tokens - record.hydrated.tokens, 0) for record in records
        ),
        actual_input_tokens=actual_input,
        actual_output_tokens=actual_output,
        cached_input_tokens=_sum_known(cached_inputs),
        local_compactor_tokens=local_tokens,
        baseline_estimate_adjusted_reduction=adjusted_reduction,
        verified_counterfactual_tokens_saved=verified_savings,
        actual_usage_completeness=completeness,
    )
    observed_total = (
        (actual_input or 0) + (actual_output or 0)
        if actual_input is not None or actual_output is not None
        else None
    )
    return ThreadLedgerReport(
        summary=summary,
        estimate_error_input_tokens=estimate_error,
        provider_observed_total_tokens=observed_total,
        billable_input_tokens=_sum_known(
            [record.usage.billable_input_tokens if record.usage else None for record in records]
        ),
        billable_output_tokens=_sum_known(
            [record.usage.billable_output_tokens if record.usage else None for record in records]
        ),
    )


def summarize_thread(
    records: Sequence[TurnTokenRecord], *, thread_id: str | None = None
) -> ThreadTokenSummary:
    """Return the stable public summary used by API, MCP, CLI, and UI surfaces."""

    return build_thread_report(records, thread_id=thread_id).summary


def estimated_turn(
    *,
    idempotency_key: str = "estimated-turn",
    thread_id: str = "thread-1",
    baseline: int,
    hydrated: int,
) -> TurnTokenRecord:
    """Small deterministic fixture helper for callers without provider usage."""

    baseline_estimate = estimate_tokens("x" * max(baseline * 4, 1))
    hydrated_estimate = estimate_tokens("x" * max(hydrated * 4, 1))
    baseline_estimate = baseline_estimate.model_copy(update={"tokens": baseline})
    hydrated_estimate = hydrated_estimate.model_copy(update={"tokens": hydrated})
    return TurnTokenRecord(
        idempotency_key=idempotency_key,
        thread_id=thread_id,
        baseline=baseline_estimate,
        hydrated=hydrated_estimate,
    )


def turn_from_envelope(
    envelope: PromptEnvelope, *, idempotency_key: str | None = None
) -> TurnTokenRecord:
    """Convert a persisted hydration envelope into immutable estimate evidence."""

    return TurnTokenRecord(
        idempotency_key=idempotency_key or envelope.hydration_id,
        thread_id=envelope.thread_id,
        hydration_id=envelope.hydration_id,
        baseline=envelope.token_plan.baseline,
        hydrated=envelope.token_plan.hydrated,
        local_compactor_input_tokens=envelope.token_plan.local_compactor_input_tokens,
        local_compactor_output_tokens=envelope.token_plan.local_compactor_output_tokens,
        recorded_at=envelope.generated_at,
    )


class TokenLedger:
    """Application-facing idempotent ledger over a persistence Protocol."""

    def __init__(self, store: UsageStore) -> None:
        self._store = store

    def record_turn(self, record: TurnTokenRecord) -> TurnTokenRecord:
        if self._store.append_turn(record):
            return record
        existing = self._store.get_turn(record.idempotency_key)
        if existing is None:
            raise RuntimeError("usage store rejected an insert but returned no existing record")
        if _evidence_payload(existing) != _evidence_payload(record):
            raise IdempotencyConflictError(
                f"idempotency key already belongs to different evidence: {record.idempotency_key}"
            )
        return existing

    def record_usage(self, usage: NormalizedUsage) -> NormalizedUsage:
        """Append actual usage after a turn without mutating its estimate evidence."""

        if self._store.append_usage(usage):
            return usage
        existing = self._store.get_usage(usage.idempotency_key)
        if existing is None:
            raise RuntimeError("usage store rejected an observation but returned no existing event")
        if _usage_evidence_payload(existing) != _usage_evidence_payload(usage):
            raise IdempotencyConflictError(
                "usage idempotency key already belongs to different evidence: "
                f"{usage.idempotency_key}"
            )
        return existing

    def list_turns(self, thread_id: str) -> Sequence[TurnTokenRecord]:
        return tuple(
            _join_later_usage(self._store.list_turns(thread_id), self._store.list_usage(thread_id))
        )

    def thread_report(self, thread_id: str) -> ThreadLedgerReport:
        return build_thread_report(self.list_turns(thread_id), thread_id=thread_id)

    def thread_summary(self, thread_id: str) -> ThreadTokenSummary:
        return self.thread_report(thread_id).summary
