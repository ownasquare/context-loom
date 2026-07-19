export type CompactionMode =
  | "hybrid_safe"
  | "strict_extractive"
  | "compact_aggressive"
  | "passthrough";

export type FidelityStatus = "passed" | "degraded" | "fallback" | "failed";

export type ThemePreference = "light" | "dark" | "system";

export type CountingMethod =
  | "exact_local"
  | "provider_observed"
  | "calibrated_estimate"
  | "rough_estimate";

export interface TokenEstimate {
  tokens: number;
  method: CountingMethod;
  tokenizer: string;
  tokenizer_version: string | null;
  provider: string | null;
  model: string | null;
  confidence: number;
}

export interface ResourceCitation {
  resource_id: string;
  version_id: string;
  chunk_id: string | null;
  relative_path: string;
  sha256: string;
  excerpt_sha256: string;
  start_line: number;
  end_line: number;
  stale: boolean;
}

export interface ScoreBreakdown {
  lexical: number;
  dense: number;
  direct_reference: number;
  recency: number;
  authority: number;
  thread_affinity: number;
  penalty: number;
  total: number;
}

export interface ContextItem {
  citation: ResourceCitation;
  kind:
    | "code"
    | "documentation"
    | "instruction"
    | "configuration"
    | "test"
    | "tool_catalog"
    | "mcp_catalog"
    | "validation"
    | "other";
  excerpt: string;
  score: ScoreBreakdown;
  selection_reason: string;
  protected_atoms: string[];
}

export interface OmittedContext {
  relative_path: string;
  version_id: string;
  reason: string;
  recoverable_uri: string;
  estimated_tokens: number;
}

export interface FidelityReport {
  status: FidelityStatus;
  requested_mode: CompactionMode;
  effective_mode: CompactionMode;
  exact_message_preserved: boolean;
  citations_valid: boolean;
  freshness_valid: boolean;
  protected_atom_coverage: number;
  explicit_reference_coverage: number;
  security_overrides: string[];
  failures: string[];
  replay_hash: string;
  fallback_reason: string | null;
}

export interface TokenPlan {
  baseline: TokenEstimate;
  hydrated: TokenEstimate;
  reserved_output_tokens: number;
  local_compactor_input_tokens: number;
  local_compactor_output_tokens: number;
  projected_input_tokens_saved: number;
  projected_reduction_percent: number;
}

export interface PromptEnvelope {
  schema_version: "prompt-envelope-v1";
  hydration_id: string;
  workspace_id: string;
  thread_id: string;
  adapter: string;
  generated_at: string;
  message_exact: string;
  intent: {
    labels: string[];
    keywords: string[];
    explicit_paths: string[];
    symbols: string[];
    quoted_signals: string[];
    risk_labels: string[];
    tool_routes: string[];
  };
  snapshot: {
    workspace_id: string;
    generation_id: string;
    root_name: string;
    indexed_resources: number;
    changed_resources: number;
    generated_at: string;
  };
  context_digest: string | null;
  context_items: ContextItem[];
  omitted_context: OmittedContext[];
  recovery_manifest: string[];
  fidelity: FidelityReport;
  token_plan: TokenPlan;
  metadata: Record<string, unknown>;
}

export interface HydrateRequest {
  workspace_id: string;
  message: string;
  thread_id?: string;
  thread_label?: string;
  adapter: string;
  mode: CompactionMode;
  max_input_tokens: number;
  reserve_output_tokens: number;
  use_local_model: boolean;
  include_debug: boolean;
}

export interface HydrationResponse {
  envelope: PromptEnvelope;
  rendered: RenderedPrompt;
}

export interface RenderedPrompt {
  adapter: string;
  media_type: string;
  payload: string | Record<string, unknown>;
  exact_message: string;
  instructions: string[];
}

export interface WorkspaceRecord {
  id: string;
  name: string;
  root_path: string;
  created_at: string;
  updated_at: string;
  last_sync_at: string | null;
}

export interface WorkspaceCreate {
  name: string;
  root_path: string;
}

export interface SyncReport {
  workspace_id: string;
  generation_id: string;
  added: number;
  modified: number;
  deleted: number;
  unchanged: number;
  excluded: number;
  redacted: number;
  duration_ms: number;
}

export interface WorkspaceStatus {
  workspace: WorkspaceRecord;
  active_generation_id: string | null;
  indexed_resources: number;
  indexed_chunks: number;
  stale_resources: number;
  excluded_resources: number;
  last_sync: SyncReport | null;
}

export interface ResourceSummary {
  resource_id: string;
  version_id: string;
  relative_path: string;
  kind: ContextItem["kind"];
  sha256: string;
  estimated_tokens: number;
  chunks: number;
  status: "current" | "changed" | "stale" | "excluded";
  changed_at: string;
  change_type: "added" | "modified" | "deleted" | "renamed" | "unchanged";
}

export interface ResourceVersionContent {
  resource_id: string;
  version_id: string;
  workspace_id: string;
  relative_path: string;
  kind: ContextItem["kind"];
  sha256: string;
  content: string;
  current: boolean;
  redacted_count: number;
  created_at: string;
}

export interface UsageObservation {
  idempotency_key: string;
  thread_id: string;
  hydration_id?: string | null;
  provider: string;
  model: string;
  counting_method?: CountingMethod;
  actual_input_tokens?: number | null;
  actual_output_tokens?: number | null;
  cached_input_tokens?: number | null;
  reasoning_tokens?: number | null;
  local_input_tokens?: number | null;
  local_output_tokens?: number | null;
  billable_input_tokens?: number | null;
  billable_output_tokens?: number | null;
  verified_baseline_input_tokens?: number | null;
  provider_request_id_hash?: string | null;
  observed_at?: string;
}

export interface ThreadTokenSummary {
  thread_id: string;
  turns: number;
  estimated_baseline_input_tokens: number;
  estimated_hydrated_input_tokens: number;
  projected_input_tokens_saved: number;
  actual_input_tokens: number | null;
  actual_output_tokens: number | null;
  cached_input_tokens: number | null;
  local_compactor_tokens: number;
  baseline_estimate_adjusted_reduction: number | null;
  verified_counterfactual_tokens_saved: number | null;
  actual_usage_completeness: number;
}

export interface TurnSummary {
  hydration_id: string;
  created_at: string;
  adapter: string;
  effective_mode: CompactionMode;
  projected_input_tokens_saved: number;
  usage_recorded: boolean;
  actual_input_tokens: number | null;
  verified_counterfactual_tokens_saved: number | null;
  fidelity_status: FidelityStatus;
}

export interface ThreadSummary {
  thread_id: string;
  label: string;
  turns: number;
  updated_at: string;
  estimated_baseline_input_tokens: number;
  estimated_hydrated_input_tokens: number;
  projected_input_tokens_saved: number;
  actual_input_tokens: number | null;
  actual_output_tokens: number | null;
  cached_input_tokens: number | null;
  local_compactor_tokens: number;
  baseline_estimate_adjusted_reduction: number | null;
  verified_counterfactual_tokens_saved: number | null;
  actual_usage_completeness: number;
  history: TurnSummary[];
}

export interface AdapterCapability {
  id: string;
  display_name: string;
  injection: "automatic" | "mcp" | "wrapper" | "manual";
  usage_visibility: "provider_observed" | "importable" | "manual" | "unknown";
  formats: string[];
  install_supported: boolean;
  status: "ready" | "available" | "manual_setup";
  description: string;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  version: string;
  database: "ready" | "unavailable";
  local_model: "disabled" | "available" | "unavailable";
  outbound_allowed: boolean;
  retain_message_content: boolean;
}

export interface ReadinessStatus {
  status: "ready" | "degraded";
  database: "ready" | "unavailable";
  local_model: "disabled" | "available" | "unavailable";
  migrations_current: boolean;
}

export interface ApiList<T> {
  items: T[];
}
