"""Normalize provider usage without converting missing fields into zeroes."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import ConfigDict, Field

from context_loom.domain.models import CountingMethod, StrictModel, UsageObservation


class NormalizedUsage(StrictModel):
    """Immutable superset of cross-provider usage and billable token fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str
    thread_id: str
    hydration_id: str | None = None
    provider: str
    model: str
    counting_method: CountingMethod = CountingMethod.PROVIDER_OBSERVED
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    local_input_tokens: int | None = Field(default=None, ge=0)
    local_output_tokens: int | None = Field(default=None, ge=0)
    billable_input_tokens: int | None = Field(default=None, ge=0)
    billable_output_tokens: int | None = Field(default=None, ge=0)
    verified_baseline_input_tokens: int | None = Field(default=None, ge=0)
    provider_request_id_hash: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_observation(self) -> UsageObservation:
        return UsageObservation(
            idempotency_key=self.idempotency_key,
            thread_id=self.thread_id,
            hydration_id=self.hydration_id,
            provider=self.provider,
            model=self.model,
            counting_method=self.counting_method,
            actual_input_tokens=self.input_tokens,
            actual_output_tokens=self.output_tokens,
            cached_input_tokens=self.cached_input_tokens,
            reasoning_tokens=self.reasoning_tokens,
            local_input_tokens=self.local_input_tokens,
            local_output_tokens=self.local_output_tokens,
            billable_input_tokens=self.billable_input_tokens,
            billable_output_tokens=self.billable_output_tokens,
            verified_baseline_input_tokens=self.verified_baseline_input_tokens,
            provider_request_id_hash=self.provider_request_id_hash,
            observed_at=self.observed_at,
        )


def _nested(payload: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _first_int(payload: Mapping[str, Any], paths: Sequence[Sequence[str]]) -> int | None:
    for path in paths:
        value = _nested(payload, path)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, float) and value >= 0 and value.is_integer():
            return int(value)
    return None


def _hash_request_id(request_id: str | None) -> str | None:
    if not request_id:
        return None
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def normalize_provider_usage(
    payload: Mapping[str, Any],
    *,
    idempotency_key: str,
    thread_id: str,
    provider: str,
    model: str,
    hydration_id: str | None = None,
    provider_request_id: str | None = None,
    observed_at: datetime | None = None,
) -> NormalizedUsage:
    """Normalize OpenAI, Anthropic, Gemini, and compatible usage field spellings."""

    input_tokens = _first_int(
        payload,
        (
            ("input_tokens",),
            ("prompt_tokens",),
            ("promptTokenCount",),
            ("usage", "input_tokens"),
            ("usage", "prompt_tokens"),
            ("usageMetadata", "promptTokenCount"),
        ),
    )
    output_tokens = _first_int(
        payload,
        (
            ("output_tokens",),
            ("completion_tokens",),
            ("candidatesTokenCount",),
            ("usage", "output_tokens"),
            ("usage", "completion_tokens"),
            ("usageMetadata", "candidatesTokenCount"),
        ),
    )
    cached_input = _first_int(
        payload,
        (
            ("cached_input_tokens",),
            ("cache_read_input_tokens",),
            ("input_tokens_details", "cached_tokens"),
            ("prompt_tokens_details", "cached_tokens"),
            ("usage", "input_tokens_details", "cached_tokens"),
            ("usage", "prompt_tokens_details", "cached_tokens"),
            ("usageMetadata", "cachedContentTokenCount"),
        ),
    )
    reasoning = _first_int(
        payload,
        (
            ("reasoning_tokens",),
            ("output_tokens_details", "reasoning_tokens"),
            ("completion_tokens_details", "reasoning_tokens"),
            ("usage", "output_tokens_details", "reasoning_tokens"),
            ("usage", "completion_tokens_details", "reasoning_tokens"),
            ("usageMetadata", "thoughtsTokenCount"),
        ),
    )
    return NormalizedUsage(
        idempotency_key=idempotency_key,
        thread_id=thread_id,
        hydration_id=hydration_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input,
        reasoning_tokens=reasoning,
        local_input_tokens=_first_int(payload, (("local_input_tokens",),)),
        local_output_tokens=_first_int(payload, (("local_output_tokens",),)),
        billable_input_tokens=_first_int(payload, (("billable_input_tokens",),)),
        billable_output_tokens=_first_int(payload, (("billable_output_tokens",),)),
        verified_baseline_input_tokens=_first_int(payload, (("verified_baseline_input_tokens",),)),
        provider_request_id_hash=_hash_request_id(provider_request_id),
        observed_at=observed_at or datetime.now(UTC),
    )
