"""Harness adapter interfaces and capability metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from context_loom.domain.models import AdapterCapability, PromptEnvelope


class RenderedPrompt(BaseModel):
    """A rendered envelope plus its machine-readable delivery metadata."""

    model_config = ConfigDict(extra="forbid")

    adapter: str
    media_type: str
    payload: str | dict[str, Any]
    exact_message: str
    instructions: list[str] = Field(default_factory=list)


class HarnessAdapter(Protocol):
    """Render one canonical envelope without transporting it."""

    @property
    def capability(self) -> AdapterCapability: ...

    def render(self, envelope: PromptEnvelope) -> RenderedPrompt: ...


class AdapterNotFoundError(LookupError):
    """Raised when a requested public adapter identifier is unknown."""


class AdapterRegistryProtocol(Protocol):
    def get(self, adapter_id: str) -> HarnessAdapter: ...

    def capabilities(self) -> list[AdapterCapability]: ...

    def render(self, adapter_id: str, envelope: PromptEnvelope) -> RenderedPrompt: ...

    def as_mapping(self) -> Mapping[str, HarnessAdapter]: ...
