from __future__ import annotations

from context_loom.domain.models import CountingMethod
from context_loom.tokenization.estimators import TokenEstimator, estimate_tokens, profile_for
from context_loom.tokenization.usage import normalize_provider_usage


def test_openai_profile_uses_exact_local_tiktoken_with_fingerprint() -> None:
    profile = profile_for("openai", "gpt-4o")
    estimate = estimate_tokens("hello world", profile=profile)
    assert estimate.method is CountingMethod.EXACT_LOCAL
    assert profile.fingerprint in estimate.tokenizer
    assert estimate.tokens > 0
    assert estimate.confidence == 1.0


def test_unknown_provider_uses_named_rough_estimate() -> None:
    estimator = TokenEstimator("other", "frontier-x")
    estimate = estimator.estimate("four words in text")
    assert estimate.method is CountingMethod.ROUGH_ESTIMATE
    assert estimate.tokenizer_version == "context-loom-v1"
    assert 0 < estimate.confidence < 1


def test_normalization_keeps_missing_fields_unknown() -> None:
    usage = normalize_provider_usage(
        {"input_tokens": 120},
        idempotency_key="usage-1",
        thread_id="thread-1",
        provider="anthropic",
        model="claude",
    )
    assert usage.input_tokens == 120
    assert usage.output_tokens is None
    assert usage.cached_input_tokens is None
    assert usage.billable_input_tokens is None


def test_normalization_supports_nested_openai_usage_and_hashes_request_id() -> None:
    usage = normalize_provider_usage(
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 40},
                "completion_tokens_details": {"reasoning_tokens": 7},
            }
        },
        idempotency_key="usage-1",
        thread_id="thread-1",
        provider="openai",
        model="gpt-4o",
        provider_request_id="request-raw-id",
    )
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.cached_input_tokens == 40
    assert usage.reasoning_tokens == 7
    assert usage.provider_request_id_hash is not None
    assert "request-raw-id" not in usage.provider_request_id_hash
