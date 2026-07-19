"""Opt-in, non-streaming OpenAI-compatible forwarding with normalized usage."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict

from context_loom.domain.models import CountingMethod, PromptEnvelope, UsageObservation
from context_loom.integrations.renderers import AdapterRegistry


class ProxyDisabledError(PermissionError):
    """Outbound forwarding is not enabled by local policy."""


class UnsupportedProxyRequestError(ValueError):
    """The compatibility proxy intentionally rejects an unsafe/unsupported request."""


class ProxyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_code: int
    response: dict[str, Any]
    usage: UsageObservation | None


UsageSink = Callable[[UsageObservation], Awaitable[None]]


class OpenAICompatibleProxy:
    """Forward a hydrated request only to one operator-configured upstream."""

    def __init__(
        self,
        *,
        upstream_url: str,
        allow_outbound: bool,
        client: httpx.AsyncClient | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        parsed = urlparse(upstream_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("upstream_url must be an absolute HTTP(S) URL")
        self._upstream_url = upstream_url.rstrip("/")
        self._allow_outbound = allow_outbound
        self._client = client
        self._usage_sink = usage_sink
        self._adapters = AdapterRegistry()

    async def forward(
        self,
        *,
        endpoint: Literal["chat/completions", "responses"],
        original_payload: Mapping[str, Any],
        envelope: PromptEnvelope,
        authorization: str | None,
        idempotency_key: str,
    ) -> ProxyResult:
        if not self._allow_outbound:
            raise ProxyDisabledError("outbound forwarding is disabled")
        if original_payload.get("stream") is True:
            raise UnsupportedProxyRequestError(
                "streaming is not supported by the usage-accounted v1 proxy"
            )
        adapter_id = "openai_chat" if endpoint == "chat/completions" else "openai_responses"
        rendered = self._adapters.render(adapter_id, envelope)
        if not isinstance(rendered.payload, dict):
            raise TypeError("OpenAI-compatible adapter must return JSON")
        payload = dict(original_payload)
        payload.update(rendered.payload)
        headers = {"Content-Type": "application/json", "Idempotency-Key": idempotency_key}
        if authorization:
            headers["Authorization"] = authorization
        owned_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=60)
        try:
            response = await client.post(
                f"{self._upstream_url}/v1/{endpoint}", json=payload, headers=headers
            )
        finally:
            if owned_client:
                await client.aclose()
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("provider response must be a JSON object")
        usage = normalize_openai_usage(
            body,
            thread_id=envelope.thread_id,
            hydration_id=envelope.hydration_id,
            idempotency_key=idempotency_key,
            requested_model=str(original_payload.get("model") or "unknown"),
        )
        if usage is not None and self._usage_sink is not None:
            await self._usage_sink(usage)
        return ProxyResult(status_code=response.status_code, response=body, usage=usage)


def normalize_openai_usage(
    payload: Mapping[str, Any],
    *,
    thread_id: str,
    hydration_id: str,
    idempotency_key: str,
    requested_model: str,
) -> UsageObservation | None:
    raw_usage = payload.get("usage")
    if not isinstance(raw_usage, Mapping):
        return None
    input_tokens = _optional_int(raw_usage.get("input_tokens", raw_usage.get("prompt_tokens")))
    output_tokens = _optional_int(
        raw_usage.get("output_tokens", raw_usage.get("completion_tokens"))
    )
    details = raw_usage.get("input_tokens_details") or raw_usage.get("prompt_tokens_details")
    cached = _optional_int(details.get("cached_tokens")) if isinstance(details, Mapping) else None
    output_details = raw_usage.get("output_tokens_details") or raw_usage.get(
        "completion_tokens_details"
    )
    reasoning = (
        _optional_int(output_details.get("reasoning_tokens"))
        if isinstance(output_details, Mapping)
        else None
    )
    if input_tokens is None and output_tokens is None:
        return None
    request_id = payload.get("id")
    request_hash = (
        hashlib.sha256(str(request_id).encode()).hexdigest() if request_id is not None else None
    )
    return UsageObservation(
        idempotency_key=idempotency_key,
        thread_id=thread_id,
        hydration_id=hydration_id,
        provider="openai_compatible",
        model=str(payload.get("model") or requested_model),
        counting_method=CountingMethod.PROVIDER_OBSERVED,
        actual_input_tokens=input_tokens,
        actual_output_tokens=output_tokens,
        cached_input_tokens=cached,
        reasoning_tokens=reasoning,
        provider_request_id_hash=request_hash,
    )


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return int(value)
