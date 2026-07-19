from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from context_loom.domain.models import (
    CompactionMode,
    CountingMethod,
    FidelityReport,
    FidelityStatus,
    HydrateRequest,
    ProjectSnapshot,
    PromptEnvelope,
    ThreadTokenSummary,
    TokenEstimate,
    TokenPlan,
    UsageObservation,
)


def test_hydrate_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        HydrateRequest.model_validate(
            {"workspace_id": "workspace-1", "message": "fix it", "surprise": True}
        )


def test_hydrate_request_preserves_message_whitespace() -> None:
    message = "  keep my exact spacing\n"
    request = HydrateRequest(
        workspace_id="workspace-1",
        message=message,
        thread_label="Retry policy review",
    )
    assert request.message == message
    assert request.thread_label == "Retry policy review"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idempotency_key", " "),
        ("thread_id", ""),
        ("provider", "\t"),
        ("model", "x" * 129),
    ],
)
def test_usage_observation_rejects_blank_or_unbounded_identity_fields(
    field: str, value: str
) -> None:
    payload = {
        "idempotency_key": "usage-1",
        "thread_id": "thread-1",
        "provider": "manual",
        "model": "unknown",
        "actual_input_tokens": 0,
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        UsageObservation.model_validate(payload)


def test_usage_observation_requires_one_meaningful_token_field() -> None:
    with pytest.raises(ValidationError):
        UsageObservation(
            idempotency_key="usage-1",
            thread_id="thread-1",
            provider="manual",
            model="unknown",
            counting_method=CountingMethod.ROUGH_ESTIMATE,
        )

    event = UsageObservation(
        idempotency_key="usage-1",
        thread_id="thread-1",
        provider="manual",
        model="unknown",
        counting_method=CountingMethod.ROUGH_ESTIMATE,
        actual_output_tokens=0,
    )
    assert event.actual_input_tokens is None
    assert event.actual_output_tokens == 0


def test_hydrate_request_rejects_blank_or_unbounded_thread_labels() -> None:
    for invalid in (" ", "x" * 121):
        with pytest.raises(ValidationError):
            HydrateRequest(
                workspace_id="workspace-1",
                message="fix it",
                thread_label=invalid,
            )


def test_token_plan_computes_projected_input_savings_only() -> None:
    plan = TokenPlan(
        baseline=TokenEstimate(
            tokens=1_200,
            method=CountingMethod.EXACT_LOCAL,
            tokenizer="cl100k_base",
            confidence=1.0,
        ),
        hydrated=TokenEstimate(
            tokens=400,
            method=CountingMethod.EXACT_LOCAL,
            tokenizer="cl100k_base",
            confidence=1.0,
        ),
        reserved_output_tokens=800,
    )
    assert plan.projected_input_tokens_saved == 800
    assert plan.projected_reduction_percent == pytest.approx(66.67)


def test_prompt_envelope_keeps_message_exact() -> None:
    message = "Review src/ledger.py without changing the threshold 80%.\n"
    envelope = PromptEnvelope(
        hydration_id="hydration-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        adapter="generic_markdown",
        message_exact=message,
        intent={"explicit_paths": ["src/ledger.py"]},
        snapshot=ProjectSnapshot(
            workspace_id="workspace-1",
            generation_id="generation-1",
            root_name="demo",
            indexed_resources=1,
            changed_resources=0,
            generated_at=datetime.now(UTC),
        ),
        fidelity=FidelityReport(
            status=FidelityStatus.PASSED,
            requested_mode=CompactionMode.HYBRID_SAFE,
            effective_mode=CompactionMode.STRICT_EXTRACTIVE,
            exact_message_preserved=True,
            citations_valid=True,
            freshness_valid=True,
            protected_atom_coverage=1.0,
            explicit_reference_coverage=1.0,
            replay_hash="a" * 64,
        ),
        token_plan=TokenPlan(
            baseline=TokenEstimate(
                tokens=200,
                method=CountingMethod.ROUGH_ESTIMATE,
                tokenizer="chars-div-4",
                confidence=0.5,
            ),
            hydrated=TokenEstimate(
                tokens=100,
                method=CountingMethod.ROUGH_ESTIMATE,
                tokenizer="chars-div-4",
                confidence=0.5,
            ),
            reserved_output_tokens=800,
        ),
    )
    assert envelope.message_exact.encode() == message.encode()


def test_thread_summary_does_not_invent_verified_savings() -> None:
    summary = ThreadTokenSummary(
        thread_id="thread-1",
        turns=1,
        estimated_baseline_input_tokens=1_200,
        estimated_hydrated_input_tokens=400,
        projected_input_tokens_saved=800,
        actual_usage_completeness=0.0,
    )
    assert summary.actual_input_tokens is None
    assert summary.verified_counterfactual_tokens_saved is None
