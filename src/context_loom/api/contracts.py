"""Strict HTTP-only request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from context_loom.domain.models import CompactionMode, FidelityStatus, PromptEnvelope
from context_loom.integrations.base import RenderedPrompt


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiErrorDetail(ApiModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(ApiModel):
    error: ApiErrorDetail


class ReadinessStatus(ApiModel):
    status: Literal["ready", "degraded"]
    database: Literal["ready", "unavailable"]
    local_model: Literal["disabled", "available", "unavailable"]
    migrations_current: bool


class HydrationResponse(ApiModel):
    envelope: PromptEnvelope
    rendered: RenderedPrompt


class ResourceSummary(ApiModel):
    resource_id: str
    version_id: str
    relative_path: str
    kind: str
    sha256: str
    estimated_tokens: int = Field(default=0, ge=0)
    chunks: int = Field(default=0, ge=0)
    status: Literal["current", "changed", "stale", "excluded"] = "current"
    changed_at: datetime
    change_type: Literal["added", "modified", "deleted", "renamed", "unchanged"]


class ResourcePage(ApiModel):
    items: list[ResourceSummary]
    total: int = Field(ge=0)


class ResourceVersionContent(ApiModel):
    resource_id: str
    version_id: str
    workspace_id: str
    relative_path: str
    kind: str
    sha256: str
    content: str
    current: bool
    redacted_count: int = Field(ge=0)
    created_at: datetime


class TurnSummary(ApiModel):
    hydration_id: str
    created_at: datetime
    adapter: str
    effective_mode: CompactionMode
    projected_input_tokens_saved: int
    usage_recorded: bool
    actual_input_tokens: int | None = None
    verified_counterfactual_tokens_saved: int | None = None
    fidelity_status: FidelityStatus


class ThreadSummary(ApiModel):
    thread_id: str
    label: str
    turns: int = Field(ge=0)
    updated_at: datetime
    estimated_baseline_input_tokens: int = Field(ge=0)
    estimated_hydrated_input_tokens: int = Field(ge=0)
    projected_input_tokens_saved: int = Field(ge=0)
    actual_input_tokens: int | None = Field(default=None, ge=0)
    actual_output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    local_compactor_tokens: int = Field(default=0, ge=0)
    baseline_estimate_adjusted_reduction: int | None = None
    verified_counterfactual_tokens_saved: int | None = None
    actual_usage_completeness: float = Field(ge=0, le=1)
    history: list[TurnSummary] = Field(default_factory=list)


class ThreadPage(ApiModel):
    items: list[ThreadSummary]
    total: int = Field(ge=0)


class ExportRequest(ApiModel):
    workspace_id: str | None = None
    thread_id: str | None = None
    format: Literal["jsonl", "parquet"] = "parquet"
    include_content: bool = False


class ExportArtifact(ApiModel):
    id: str
    format: Literal["jsonl", "parquet"]
    path: str
    sha256: str
    rows: int = Field(ge=0)
    includes_content: bool


class ProxyRequest(ApiModel):
    endpoint: Literal["chat/completions", "responses"]
    hydration_id: str
    idempotency_key: str
    payload: dict[str, Any]
