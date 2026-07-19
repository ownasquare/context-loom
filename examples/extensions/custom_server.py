"""Run Context Loom's local API with the example custom adapter.

Usage:
    uv run uvicorn --factory examples.extensions.custom_server:create_custom_app \
      --host 127.0.0.1 --port 8769
"""

from __future__ import annotations

from fastapi import FastAPI

from context_loom.extensions import AdapterRegistry, Settings, create_application
from examples.extensions.custom_adapter import ChecklistAdapter


def create_custom_app(settings: Settings | None = None) -> FastAPI:
    """Build the normal local service with one explicitly trusted adapter."""

    registry = AdapterRegistry(extra_adapters=[ChecklistAdapter()])
    return create_application(settings or Settings(), adapter_registry=registry)
