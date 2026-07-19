"""Stable public types and factories for custom prompt-rendering adapters."""

from context_loom.config import Settings
from context_loom.container import create_application
from context_loom.domain.models import AdapterCapability, PromptEnvelope
from context_loom.integrations.base import HarnessAdapter, RenderedPrompt
from context_loom.integrations.renderers import AdapterRegistry, DuplicateAdapterError

__all__ = [
    "AdapterCapability",
    "AdapterRegistry",
    "DuplicateAdapterError",
    "HarnessAdapter",
    "PromptEnvelope",
    "RenderedPrompt",
    "Settings",
    "create_application",
]
