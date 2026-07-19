from __future__ import annotations

from datetime import UTC, datetime

import pytest

from context_loom.tokenization.ledger import (
    IdempotencyConflictError,
    InMemoryUsageStore,
    TokenLedger,
    TurnTokenRecord,
    estimated_turn,
    summarize_thread,
)
from context_loom.tokenization.usage import NormalizedUsage


def test_projected_savings_is_not_labeled_verified() -> None:
    summary = summarize_thread([estimated_turn(baseline=1_200, hydrated=400)])
    assert summary.projected_input_tokens_saved == 800
    assert summary.verified_counterfactual_tokens_saved is None
    assert summary.actual_usage_completeness == 0.0


def test_provider_usage_and_verified_counterfactual_remain_separate() -> None:
    base = estimated_turn(idempotency_key="turn-1", baseline=1_200, hydrated=400)
    usage = NormalizedUsage(
        idempotency_key="turn-1",
        thread_id="thread-1",
        provider="openai",
        model="gpt-4o",
        input_tokens=420,
        output_tokens=80,
        cached_input_tokens=50,
        verified_baseline_input_tokens=1_180,
        observed_at=datetime.now(UTC),
    )
    record = base.model_copy(update={"usage": usage})
    ledger = TokenLedger(InMemoryUsageStore())
    ledger.record_turn(record)
    report = ledger.thread_report("thread-1")
    assert report.summary.projected_input_tokens_saved == 800
    assert report.summary.actual_input_tokens == 420
    assert report.summary.verified_counterfactual_tokens_saved == 760
    assert report.summary.baseline_estimate_adjusted_reduction == 780
    assert report.estimate_error_input_tokens == 20


def test_partial_actual_usage_has_fractional_completeness_and_no_adjusted_reduction() -> None:
    first = estimated_turn(idempotency_key="turn-1", baseline=100, hydrated=50)
    first = first.model_copy(
        update={
            "usage": NormalizedUsage(
                idempotency_key="turn-1",
                thread_id="thread-1",
                provider="manual",
                model="unknown",
                input_tokens=55,
            )
        }
    )
    second = estimated_turn(idempotency_key="turn-2", baseline=100, hydrated=50)
    summary = summarize_thread([first, second])
    assert summary.actual_usage_completeness == 0.5
    assert summary.actual_input_tokens == 55
    assert summary.baseline_estimate_adjusted_reduction is None


def test_idempotent_retry_returns_same_record_but_conflict_is_rejected() -> None:
    ledger = TokenLedger(InMemoryUsageStore())
    record = estimated_turn(idempotency_key="turn-1", baseline=100, hydrated=50)
    assert ledger.record_turn(record) == record
    assert ledger.record_turn(record) == record
    conflicting: TurnTokenRecord = record.model_copy(
        update={"hydrated": record.hydrated.model_copy(update={"tokens": 51})}
    )
    with pytest.raises(IdempotencyConflictError):
        ledger.record_turn(conflicting)


def test_idempotent_reconstruction_ignores_observation_timestamps() -> None:
    ledger = TokenLedger(InMemoryUsageStore())
    original = estimated_turn(idempotency_key="turn-1", baseline=100, hydrated=50)
    ledger.record_turn(original)
    reconstructed = estimated_turn(idempotency_key="turn-1", baseline=100, hydrated=50)
    assert reconstructed.recorded_at != original.recorded_at
    assert ledger.record_turn(reconstructed) == original


def test_later_usage_is_joined_without_mutating_estimate_record() -> None:
    ledger = TokenLedger(InMemoryUsageStore())
    estimate = estimated_turn(idempotency_key="estimate-1", baseline=1_000, hydrated=400)
    estimate = estimate.model_copy(update={"hydration_id": "hydration-1"})
    ledger.record_turn(estimate)
    usage = NormalizedUsage(
        idempotency_key="usage-1",
        thread_id="thread-1",
        hydration_id="hydration-1",
        provider="openai",
        model="gpt-4o",
        input_tokens=410,
        output_tokens=90,
    )
    ledger.record_usage(usage)
    assert estimate.usage is None
    assert ledger.list_turns("thread-1")[0].usage == usage
    assert ledger.thread_summary("thread-1").actual_input_tokens == 410
