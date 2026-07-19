"""One harness-neutral hydration orchestration service."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from context_loom.compaction.deterministic import build_extractive_digest
from context_loom.compaction.ollama import (
    OllamaCompactionError,
    OllamaCompactionResult,
    OllamaCompactor,
)
from context_loom.compaction.protected_atoms import protected_texts
from context_loom.domain.models import (
    CompactionMode,
    ContextItem,
    FidelityStatus,
    HydrateRequest,
    IntentProfile,
    ProjectSnapshot,
    PromptEnvelope,
    TokenPlan,
)
from context_loom.hydration.budget import BudgetSelection, allocate_budget
from context_loom.hydration.envelope import context_items_from_ranked, render_compiled_prompt
from context_loom.hydration.fidelity import FidelityAuditResult, audit_fidelity
from context_loom.hydration.intent import analyze_intent
from context_loom.hydration.retrieval import RetrievalSource, collect_candidates
from context_loom.hydration.scoring import rank_candidates
from context_loom.tokenization.estimators import TokenEstimator


@runtime_checkable
class HydrationRunSink(Protocol):
    """Optional persistence contract supplied by the root application container."""

    def record_hydration_run(self, envelope: PromptEnvelope) -> None:
        """Atomically persist the envelope, selected items, fidelity report, and token plan."""


class NullHydrationRunSink:
    """No-op sink for read-only use and deterministic tests."""

    def record_hydration_run(self, envelope: PromptEnvelope) -> None:
        del envelope


class HydrationRepositoryLike(Protocol):
    """Structural subset of the canonical repository used for hydration persistence."""

    def record_hydration_run(
        self,
        *,
        hydration_id: str,
        thread_id: str,
        workspace_id: str,
        request_sha256: str,
        adapter: str,
        requested_mode: str,
        effective_mode: str,
        status: str,
        thread_label: str | None = None,
        generation_id: str | None = None,
        idempotency_key: str | None = None,
        baseline_input_tokens: int | None = None,
        hydrated_input_tokens: int | None = None,
        local_input_tokens: int | None = None,
        local_output_tokens: int | None = None,
        result: Mapping[str, Any] | None = None,
        items: Sequence[Mapping[str, Any]] = (),
        fidelity: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Persist one sanitized hydration run and cited selections atomically."""


class RepositoryHydrationRunSink:
    """Persist envelope metadata without storing raw messages or source excerpts."""

    def __init__(self, repository: HydrationRepositoryLike) -> None:
        self._repository = repository

    def record_hydration_run(self, envelope: PromptEnvelope) -> None:
        raw_thread_label = envelope.metadata.get("thread_label")
        thread_label = raw_thread_label if isinstance(raw_thread_label, str) else None
        items = [
            {
                "chunk_id": item.citation.chunk_id,
                "version_id": item.citation.version_id,
                "score": item.score.model_dump(mode="json"),
                "selection_reason": item.selection_reason,
                "citation": item.citation.model_dump(mode="json"),
            }
            for item in envelope.context_items
        ]
        self._repository.record_hydration_run(
            hydration_id=envelope.hydration_id,
            thread_id=envelope.thread_id,
            workspace_id=envelope.workspace_id,
            request_sha256=hashlib.sha256(envelope.message_exact.encode("utf-8")).hexdigest(),
            adapter=envelope.adapter,
            requested_mode=envelope.fidelity.requested_mode.value,
            effective_mode=envelope.fidelity.effective_mode.value,
            status=envelope.fidelity.status.value,
            thread_label=thread_label,
            generation_id=envelope.snapshot.generation_id,
            baseline_input_tokens=envelope.token_plan.baseline.tokens,
            hydrated_input_tokens=envelope.token_plan.hydrated.tokens,
            local_input_tokens=envelope.token_plan.local_compactor_input_tokens,
            local_output_tokens=envelope.token_plan.local_compactor_output_tokens,
            result={
                "schema_version": envelope.schema_version,
                "token_plan": envelope.token_plan.model_dump(mode="json"),
                "omitted_context": [
                    item.model_dump(mode="json") for item in envelope.omitted_context
                ],
                "recovery_manifest": envelope.recovery_manifest,
                "metadata": envelope.metadata,
            },
            items=items,
            fidelity=envelope.fidelity.model_dump(mode="json"),
        )


def _adapter_framing_tokens(adapter: str) -> int:
    return {
        "openai": 32,
        "anthropic": 36,
        "gemini": 40,
        "codex": 48,
        "generic_markdown": 64,
    }.get(adapter, 64)


def _all_protected(message: str, context_items: Sequence[ContextItem]) -> list[str]:
    values = protected_texts(message)
    for item in context_items:
        item_atoms = getattr(item, "protected_atoms", ())
        values.extend(str(atom) for atom in item_atoms)
    return list(dict.fromkeys(values))


class HydrationService:
    """Compile a message and current repository snapshot into a fidelity-audited envelope.

    Root/container dependencies:

    - ``RetrievalSource`` supplies one active snapshot and sanitized current chunks through three
      retrieval channels.
    - ``HydrationRunSink`` optionally persists the final immutable ``PromptEnvelope``.
    - ``TokenEstimator`` supplies profile-qualified deterministic counts.
    """

    def __init__(
        self,
        retrieval: RetrievalSource,
        *,
        sink: HydrationRunSink | None = None,
        estimator: TokenEstimator | None = None,
        policy_labels: Iterable[str] = (),
        allow_outbound: bool = False,
        ollama_url: str = "http://127.0.0.1:11434",
        ollama_model: str = "qwen3:4b",
        ollama_timeout_seconds: float = 30.0,
    ) -> None:
        self._retrieval = retrieval
        self._sink = sink or NullHydrationRunSink()
        self._estimator = estimator or TokenEstimator()
        self._policy_labels = tuple(policy_labels)
        self._allow_outbound = allow_outbound
        self._ollama_url = ollama_url
        self._ollama_model = ollama_model
        self._ollama_timeout_seconds = ollama_timeout_seconds

    def _local_digest(self, context_items: Sequence[ContextItem]) -> OllamaCompactionResult:
        compactor = OllamaCompactor(
            allow_outbound=self._allow_outbound,
            base_url=self._ollama_url,
            model=self._ollama_model,
            timeout_seconds=self._ollama_timeout_seconds,
        )
        return compactor.compact(context_items)

    def _audit(
        self,
        *,
        request: HydrateRequest,
        snapshot: ProjectSnapshot,
        intent: IntentProfile,
        context_items: Sequence[ContextItem],
        digest: str | None,
        effective_mode: CompactionMode,
        security_overrides: Sequence[str],
    ) -> FidelityAuditResult:
        return audit_fidelity(
            original_message=request.message,
            envelope_message=request.message,
            snapshot=snapshot,
            intent=intent,
            items=context_items,
            context_digest=digest,
            protected_atoms=_all_protected(request.message, context_items),
            requested_mode=request.mode,
            effective_mode=effective_mode,
            security_overrides=security_overrides,
        )

    def hydrate(
        self,
        request: HydrateRequest,
        *,
        security_overrides: Sequence[str] = (),
    ) -> PromptEnvelope:
        """Compile and persist one deterministic envelope, falling back instead of guessing."""

        snapshot = self._retrieval.get_snapshot(request.workspace_id)
        intent = analyze_intent(request.message, policy_labels=self._policy_labels)
        candidates = collect_candidates(
            self._retrieval,
            workspace_id=request.workspace_id,
            query=request.message,
            terms=intent.keywords,
            paths=intent.explicit_paths,
            symbols=intent.symbols,
        )
        ranked = rank_candidates(candidates, intent)
        budget: BudgetSelection = allocate_budget(
            ranked,
            message_exact=request.message,
            max_input_tokens=request.max_input_tokens,
            reserve_output_tokens=request.reserve_output_tokens,
            adapter_framing_tokens=_adapter_framing_tokens(request.adapter),
            count_tokens=self._estimator.count,
        )
        context_items = context_items_from_ranked(budget.selected)

        local_model_used = False
        local_model_attempted = False
        local_model_fallback: str | None = None
        local_input = 0
        local_output = 0
        if request.mode is CompactionMode.PASSTHROUGH:
            context_items = []
            digest = None
            effective_mode = CompactionMode.PASSTHROUGH
        elif request.use_local_model and request.mode in {
            CompactionMode.HYBRID_SAFE,
            CompactionMode.COMPACT_AGGRESSIVE,
        }:
            local_model_attempted = True
            try:
                local_result = self._local_digest(context_items)
                digest = local_result.digest
                local_input = local_result.input_tokens
                local_output = local_result.output_tokens
                local_model_used = True
                effective_mode = request.mode
            except OllamaCompactionError as error:
                local_input = error.input_tokens
                local_output = error.output_tokens
                digest = build_extractive_digest(context_items)
                effective_mode = CompactionMode.STRICT_EXTRACTIVE
                local_model_fallback = "local_model_contract_or_gate_failed"
            except ValueError:
                digest = build_extractive_digest(context_items)
                effective_mode = CompactionMode.STRICT_EXTRACTIVE
                local_model_fallback = "local_model_contract_or_gate_failed"
        else:
            digest = build_extractive_digest(context_items)
            effective_mode = (
                CompactionMode.STRICT_EXTRACTIVE
                if request.mode is CompactionMode.STRICT_EXTRACTIVE
                else request.mode
            )

        first_audit = self._audit(
            request=request,
            snapshot=snapshot,
            intent=intent,
            context_items=context_items,
            digest=digest,
            effective_mode=effective_mode,
            security_overrides=security_overrides,
        )
        final_audit = first_audit
        if first_audit.next_mode is CompactionMode.STRICT_EXTRACTIVE:
            original_failures = first_audit.report.failures
            digest = build_extractive_digest(context_items)
            effective_mode = CompactionMode.STRICT_EXTRACTIVE
            strict_audit = self._audit(
                request=request,
                snapshot=snapshot,
                intent=intent,
                context_items=context_items,
                digest=digest,
                effective_mode=effective_mode,
                security_overrides=security_overrides,
            )
            final_audit = strict_audit.model_copy(
                update={
                    "report": strict_audit.report.model_copy(
                        update={
                            "status": FidelityStatus.FALLBACK,
                            "failures": original_failures,
                            "fallback_reason": original_failures[0],
                        }
                    )
                }
            )
        if final_audit.next_mode is CompactionMode.PASSTHROUGH:
            original_failures = final_audit.report.failures
            context_items = []
            digest = None
            effective_mode = CompactionMode.PASSTHROUGH
            passthrough_audit = self._audit(
                request=request,
                snapshot=snapshot,
                intent=intent,
                context_items=context_items,
                digest=digest,
                effective_mode=effective_mode,
                security_overrides=security_overrides,
            )
            final_audit = passthrough_audit.model_copy(
                update={
                    "next_mode": None,
                    "report": passthrough_audit.report.model_copy(
                        update={
                            "status": FidelityStatus.FALLBACK,
                            "failures": original_failures,
                            "fallback_reason": original_failures[0],
                        }
                    ),
                }
            )
        if local_model_fallback and not final_audit.report.failures:
            final_audit = final_audit.model_copy(
                update={
                    "report": final_audit.report.model_copy(
                        update={
                            "status": FidelityStatus.FALLBACK,
                            "failures": [local_model_fallback],
                            "fallback_reason": local_model_fallback,
                        }
                    )
                }
            )

        baseline_text = (
            request.message + "\n" + "\n".join(candidate.excerpt for candidate in candidates)
        )
        hydrated_text = render_compiled_prompt(digest, request.message)
        token_plan = TokenPlan(
            baseline=self._estimator.estimate(baseline_text),
            hydrated=self._estimator.estimate(hydrated_text),
            reserved_output_tokens=request.reserve_output_tokens,
            local_compactor_input_tokens=local_input,
            local_compactor_output_tokens=local_output,
        )
        envelope = PromptEnvelope(
            hydration_id=f"hydration-{uuid.uuid4()}",
            workspace_id=request.workspace_id,
            thread_id=request.thread_id or f"thread-{uuid.uuid4()}",
            adapter=request.adapter,
            message_exact=request.message,
            intent=intent,
            snapshot=snapshot,
            context_digest=digest,
            context_items=context_items,
            omitted_context=budget.omitted,
            recovery_manifest=[item.recoverable_uri for item in budget.omitted],
            fidelity=final_audit.report,
            token_plan=token_plan,
            metadata={
                "budget": {
                    "message_tokens": budget.message_tokens,
                    "framing_tokens": budget.framing_tokens,
                    "available_context_tokens": budget.available_context_tokens,
                    "selected_context_tokens": budget.selected_context_tokens,
                    "input_budget_overflow": budget.input_budget_overflow,
                },
                "candidate_count": len(candidates),
                "selected_count": len(context_items),
                "local_model_attempted": local_model_attempted,
                "local_model_used": local_model_used,
                "local_model_fallback": local_model_fallback,
                **(
                    {"thread_label": request.thread_label}
                    if request.thread_label is not None
                    else {}
                ),
            },
        )
        self._sink.record_hydration_run(envelope)
        return envelope
