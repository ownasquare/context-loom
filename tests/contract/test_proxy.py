from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from context_loom.domain.models import (
    CompactionMode,
    CountingMethod,
    FidelityReport,
    FidelityStatus,
    IntentProfile,
    ProjectSnapshot,
    PromptEnvelope,
    TokenEstimate,
    TokenPlan,
)
from context_loom.integrations.proxy import (
    OpenAICompatibleProxy,
    ProxyDisabledError,
    UnsupportedProxyRequestError,
    normalize_openai_usage,
)


def envelope() -> PromptEnvelope:
    return PromptEnvelope(
        hydration_id="hydration-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        adapter="openai_chat",
        message_exact="  exact user text\n",
        intent=IntentProfile(),
        snapshot=ProjectSnapshot(
            workspace_id="workspace-1",
            generation_id="generation-1",
            root_name="demo",
            indexed_resources=0,
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
            protected_atom_coverage=1,
            explicit_reference_coverage=1,
            replay_hash="a" * 64,
        ),
        token_plan=TokenPlan(
            baseline=TokenEstimate(
                tokens=100,
                method=CountingMethod.EXACT_LOCAL,
                tokenizer="test",
                confidence=1,
            ),
            hydrated=TokenEstimate(
                tokens=50,
                method=CountingMethod.EXACT_LOCAL,
                tokenizer="test",
                confidence=1,
            ),
            reserved_output_tokens=10,
        ),
    )


@pytest.mark.asyncio
async def test_proxy_is_disabled_by_default() -> None:
    proxy = OpenAICompatibleProxy(upstream_url="https://provider.example", allow_outbound=False)
    with pytest.raises(ProxyDisabledError):
        await proxy.forward(
            endpoint="chat/completions",
            original_payload={"model": "test-model"},
            envelope=envelope(),
            authorization=None,
            idempotency_key="turn-1",
        )


@pytest.mark.asyncio
async def test_proxy_preserves_user_message_and_records_provider_usage() -> None:
    captured: dict[str, Any] = {}
    recorded = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "provider-request-1",
                "model": "test-model-2026",
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 10},
                },
                "choices": [],
            },
        )

    async def sink(event: Any) -> None:
        recorded.append(event)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    proxy = OpenAICompatibleProxy(
        upstream_url="https://provider.example",
        allow_outbound=True,
        client=client,
        usage_sink=sink,
    )
    try:
        result = await proxy.forward(
            endpoint="chat/completions",
            original_payload={"model": "test-model", "temperature": 0},
            envelope=envelope(),
            authorization="Bearer redacted-test-value",
            idempotency_key="turn-1",
        )
    finally:
        await client.aclose()
    assert captured["messages"][-1]["content"].encode() == envelope().message_exact.encode()
    assert result.usage is not None
    assert result.usage.actual_input_tokens == 80
    assert result.usage.actual_output_tokens == 20
    assert result.usage.cached_input_tokens == 10
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_streaming_is_rejected_until_usage_can_be_accounted() -> None:
    proxy = OpenAICompatibleProxy(upstream_url="https://provider.example", allow_outbound=True)
    with pytest.raises(UnsupportedProxyRequestError, match="streaming"):
        await proxy.forward(
            endpoint="responses",
            original_payload={"model": "test-model", "stream": True},
            envelope=envelope(),
            authorization=None,
            idempotency_key="turn-1",
        )


def test_usage_normalization_leaves_absent_usage_unknown() -> None:
    assert (
        normalize_openai_usage(
            {"id": "request-1"},
            thread_id="thread-1",
            hydration_id="hydration-1",
            idempotency_key="turn-1",
            requested_model="test-model",
        )
        is None
    )


def test_usage_normalizes_responses_fields() -> None:
    usage = normalize_openai_usage(
        {
            "id": "request-1",
            "model": "response-model",
            "usage": {
                "input_tokens": 40,
                "output_tokens": 12,
                "input_tokens_details": {"cached_tokens": 5},
                "output_tokens_details": {"reasoning_tokens": 3},
            },
        },
        thread_id="thread-1",
        hydration_id="hydration-1",
        idempotency_key="turn-1",
        requested_model="requested-model",
    )
    assert usage is not None
    assert usage.actual_input_tokens == 40
    assert usage.actual_output_tokens == 12
    assert usage.reasoning_tokens == 3
