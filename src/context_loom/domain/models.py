"""Provider-neutral request, fidelity, citation, and token-accounting contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base contract that rejects accidental wire-format expansion."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class CompactionMode(StrEnum):
    HYBRID_SAFE = "hybrid_safe"
    STRICT_EXTRACTIVE = "strict_extractive"
    COMPACT_AGGRESSIVE = "compact_aggressive"
    PASSTHROUGH = "passthrough"


class FidelityStatus(StrEnum):
    PASSED = "passed"
    DEGRADED = "degraded"
    FALLBACK = "fallback"
    FAILED = "failed"


class CountingMethod(StrEnum):
    EXACT_LOCAL = "exact_local"
    PROVIDER_OBSERVED = "provider_observed"
    CALIBRATED_ESTIMATE = "calibrated_estimate"
    ROUGH_ESTIMATE = "rough_estimate"


class ResourceKind(StrEnum):
    CODE = "code"
    DOCUMENTATION = "documentation"
    INSTRUCTION = "instruction"
    CONFIGURATION = "configuration"
    TEST = "test"
    TOOL_CATALOG = "tool_catalog"
    MCP_CATALOG = "mcp_catalog"
    VALIDATION = "validation"
    OTHER = "other"


class ChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNCHANGED = "unchanged"


class TokenEstimate(StrictModel):
    tokens: int = Field(ge=0)
    method: CountingMethod
    tokenizer: str
    tokenizer_version: str | None = None
    provider: str | None = None
    model: str | None = None
    confidence: float = Field(ge=0, le=1)


class ResourceCitation(StrictModel):
    resource_id: str
    version_id: str
    chunk_id: str | None = None
    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    stale: bool = False

    @model_validator(mode="after")
    def validate_line_order(self) -> ResourceCitation:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class ScoreBreakdown(StrictModel):
    lexical: float = 0.0
    dense: float = 0.0
    direct_reference: float = 0.0
    recency: float = 0.0
    authority: float = 0.0
    thread_affinity: float = 0.0
    penalty: float = 0.0
    total: float = 0.0


class ContextItem(StrictModel):
    citation: ResourceCitation
    kind: ResourceKind
    excerpt: str
    score: ScoreBreakdown
    selection_reason: str
    protected_atoms: list[str] = Field(default_factory=list)


class OmittedContext(StrictModel):
    relative_path: str
    version_id: str
    reason: str
    recoverable_uri: str
    estimated_tokens: int = Field(ge=0)


class IntentProfile(StrictModel):
    labels: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    explicit_paths: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    quoted_signals: list[str] = Field(default_factory=list)
    risk_labels: list[str] = Field(default_factory=list)
    tool_routes: list[str] = Field(default_factory=list)


class TokenPlan(StrictModel):
    baseline: TokenEstimate
    hydrated: TokenEstimate
    reserved_output_tokens: int = Field(ge=0)
    local_compactor_input_tokens: int = Field(default=0, ge=0)
    local_compactor_output_tokens: int = Field(default=0, ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def projected_input_tokens_saved(self) -> int:
        return max(self.baseline.tokens - self.hydrated.tokens, 0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def projected_reduction_percent(self) -> float:
        if self.baseline.tokens == 0:
            return 0.0
        return round(self.projected_input_tokens_saved / self.baseline.tokens * 100, 2)


class FidelityReport(StrictModel):
    status: FidelityStatus
    requested_mode: CompactionMode
    effective_mode: CompactionMode
    exact_message_preserved: bool
    citations_valid: bool
    freshness_valid: bool
    protected_atom_coverage: float = Field(ge=0, le=1)
    explicit_reference_coverage: float = Field(ge=0, le=1)
    security_overrides: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    replay_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    fallback_reason: str | None = None


class ProjectSnapshot(StrictModel):
    workspace_id: str
    generation_id: str
    root_name: str
    indexed_resources: int = Field(ge=0)
    changed_resources: int = Field(ge=0)
    generated_at: datetime


class PromptEnvelope(StrictModel):
    schema_version: Literal["prompt-envelope-v1"] = "prompt-envelope-v1"
    hydration_id: str
    workspace_id: str
    thread_id: str
    adapter: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_exact: str = Field(min_length=1)
    intent: IntentProfile
    snapshot: ProjectSnapshot
    context_digest: str | None = None
    context_items: list[ContextItem] = Field(default_factory=list)
    omitted_context: list[OmittedContext] = Field(default_factory=list)
    recovery_manifest: list[str] = Field(default_factory=list)
    fidelity: FidelityReport
    token_plan: TokenPlan
    metadata: dict[str, Any] = Field(default_factory=dict)


class HydrateRequest(StrictModel):
    workspace_id: str
    message: str = Field(min_length=1)
    thread_id: str | None = None
    thread_label: str | None = Field(default=None, min_length=1, max_length=120)
    adapter: str = "generic_markdown"
    mode: CompactionMode = CompactionMode.HYBRID_SAFE
    max_input_tokens: int = Field(default=4_000, ge=256, le=1_000_000)
    reserve_output_tokens: int = Field(default=800, ge=0, le=1_000_000)
    use_local_model: bool = False
    include_debug: bool = False

    @field_validator("thread_label")
    @classmethod
    def validate_thread_label(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("thread_label must not be blank")
        return value


class UsageObservation(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    hydration_id: str | None = None
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    counting_method: CountingMethod = CountingMethod.PROVIDER_OBSERVED
    actual_input_tokens: int | None = Field(default=None, ge=0)
    actual_output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    local_input_tokens: int | None = Field(default=None, ge=0)
    local_output_tokens: int | None = Field(default=None, ge=0)
    billable_input_tokens: int | None = Field(default=None, ge=0)
    billable_output_tokens: int | None = Field(default=None, ge=0)
    verified_baseline_input_tokens: int | None = Field(default=None, ge=0)
    provider_request_id_hash: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("idempotency_key", "thread_id", "provider", "model")
    @classmethod
    def validate_identity_field(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("usage identity fields must not be blank")
        return value

    @model_validator(mode="after")
    def validate_token_evidence(self) -> UsageObservation:
        token_fields = (
            self.actual_input_tokens,
            self.actual_output_tokens,
            self.cached_input_tokens,
            self.reasoning_tokens,
            self.local_input_tokens,
            self.local_output_tokens,
            self.billable_input_tokens,
            self.billable_output_tokens,
            self.verified_baseline_input_tokens,
        )
        if all(value is None for value in token_fields):
            raise ValueError("at least one token field must be provided")
        return self


class ThreadTokenSummary(StrictModel):
    thread_id: str
    turns: int = Field(ge=0)
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


class WorkspaceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    root_path: str


class WorkspaceRecord(StrictModel):
    id: str
    name: str
    root_path: str
    created_at: datetime
    updated_at: datetime
    last_sync_at: datetime | None = None


class SyncReport(StrictModel):
    workspace_id: str
    generation_id: str
    added: int = Field(ge=0)
    modified: int = Field(ge=0)
    deleted: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    excluded: int = Field(ge=0)
    redacted: int = Field(ge=0)
    duration_ms: float = Field(ge=0)


class WorkspaceStatus(StrictModel):
    workspace: WorkspaceRecord
    active_generation_id: str | None
    indexed_resources: int = Field(ge=0)
    indexed_chunks: int = Field(ge=0)
    stale_resources: int = Field(ge=0)
    excluded_resources: int = Field(ge=0)
    last_sync: SyncReport | None = None


class HealthStatus(StrictModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ready", "unavailable"]
    local_model: Literal["disabled", "available", "unavailable"]
    outbound_allowed: bool
    retain_message_content: bool


class AdapterCapability(StrictModel):
    id: str
    display_name: str
    injection: Literal["automatic", "mcp", "wrapper", "manual"]
    usage_visibility: Literal["provider_observed", "importable", "manual", "unknown"]
    formats: list[str]
    install_supported: bool
    status: Literal["ready", "available", "manual_setup"] = "available"
    description: str = "Harness-neutral structured context delivery"
