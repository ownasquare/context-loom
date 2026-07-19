"""Public dependency construction helpers for embedders and process entrypoints."""

from __future__ import annotations

from fastapi import FastAPI

from context_loom.api.app import create_app
from context_loom.config import Settings, load_settings
from context_loom.domain.models import UsageObservation
from context_loom.integrations.proxy import OpenAICompatibleProxy
from context_loom.integrations.renderers import AdapterRegistry
from context_loom.runtime import ContextLoomRuntime


def create_runtime(settings: Settings | None = None) -> ContextLoomRuntime:
    """Build the single canonical runtime without starting a transport."""

    return ContextLoomRuntime(settings or load_settings())


def create_application(
    settings: Settings | None = None,
    *,
    adapter_registry: AdapterRegistry | None = None,
) -> FastAPI:
    """Build the production FastAPI application and optional configured proxy."""

    active_settings = settings or load_settings()
    runtime = create_runtime(active_settings)
    proxy = None
    if active_settings.proxy_upstream_url:

        async def record_usage(observation: UsageObservation) -> None:
            await runtime.record_usage(observation)

        proxy = OpenAICompatibleProxy(
            upstream_url=active_settings.proxy_upstream_url,
            allow_outbound=active_settings.allow_outbound,
            usage_sink=record_usage,
        )
    return create_app(runtime, proxy=proxy, adapter_registry=adapter_registry)


__all__ = ["create_application", "create_runtime"]
