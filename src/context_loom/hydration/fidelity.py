"""Fidelity gates, deterministic replay hashing, and safe fallback transitions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from context_loom.domain.models import (
    CompactionMode,
    ContextItem,
    FidelityReport,
    FidelityStatus,
    IntentProfile,
    ProjectSnapshot,
    StrictModel,
)


class FidelityAuditResult(StrictModel):
    report: FidelityReport
    next_mode: CompactionMode | None = None


def deterministic_replay_hash(
    *,
    message_exact: str,
    snapshot: ProjectSnapshot,
    items: Sequence[ContextItem],
    context_digest: str | None,
    requested_mode: CompactionMode,
    effective_mode: CompactionMode,
    security_overrides: Sequence[str] = (),
) -> str:
    """Hash semantic pipeline inputs while excluding wall-clock and random run identifiers."""

    payload = {
        "message_exact": message_exact,
        "workspace_id": snapshot.workspace_id,
        "generation_id": snapshot.generation_id,
        "items": [item.model_dump(mode="json") for item in items],
        "context_digest": context_digest,
        "requested_mode": requested_mode.value,
        "effective_mode": effective_mode.value,
        "security_overrides": list(security_overrides),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coverage(expected: Sequence[str], haystack: str) -> float:
    unique = list(dict.fromkeys(expected))
    if not unique:
        return 1.0
    return sum(atom in haystack for atom in unique) / len(unique)


def _explicit_reference_coverage(intent: IntentProfile, items: Sequence[ContextItem]) -> float:
    expected = {path.removeprefix("./").replace("\\", "/") for path in intent.explicit_paths}
    if not expected:
        return 1.0
    selected = {item.citation.relative_path.removeprefix("./").replace("\\", "/") for item in items}
    return len(expected & selected) / len(expected)


def _next_mode(mode: CompactionMode) -> CompactionMode | None:
    if mode in {CompactionMode.HYBRID_SAFE, CompactionMode.COMPACT_AGGRESSIVE}:
        return CompactionMode.STRICT_EXTRACTIVE
    if mode is CompactionMode.STRICT_EXTRACTIVE:
        return CompactionMode.PASSTHROUGH
    return None


def audit_fidelity(
    *,
    original_message: str,
    envelope_message: str,
    snapshot: ProjectSnapshot,
    intent: IntentProfile,
    items: Sequence[ContextItem],
    context_digest: str | None,
    protected_atoms: Sequence[str],
    requested_mode: CompactionMode,
    effective_mode: CompactionMode,
    security_overrides: Sequence[str] = (),
    extra_failures: Sequence[str] = (),
) -> FidelityAuditResult:
    """Evaluate all source-preservation gates and name the only safe next transition."""

    exact_message = original_message.encode("utf-8") == envelope_message.encode("utf-8")
    citations_valid = all(
        hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest() == item.citation.excerpt_sha256
        and item.citation.version_id
        and item.citation.sha256
        for item in items
    )
    freshness_valid = all(not item.citation.stale for item in items)
    protected_haystack = f"{envelope_message}\n{context_digest or ''}"
    protected_coverage = _coverage(protected_atoms, protected_haystack)
    explicit_coverage = _explicit_reference_coverage(intent, items)

    failures = list(extra_failures)
    if not exact_message:
        failures.append("exact_message_not_preserved")
    if not citations_valid:
        failures.append("citation_validation_failed")
    if not freshness_valid:
        failures.append("freshness_validation_failed")
    if protected_coverage < 1.0:
        failures.append("protected_atom_coverage_failed")
    if explicit_coverage < 1.0:
        failures.append("explicit_reference_coverage_failed")
    failures = list(dict.fromkeys(failures))
    next_mode = _next_mode(effective_mode) if failures else None

    if failures:
        status = FidelityStatus.FAILED if next_mode is None else FidelityStatus.FALLBACK
    elif security_overrides:
        status = FidelityStatus.DEGRADED
    else:
        status = FidelityStatus.PASSED
    report = FidelityReport(
        status=status,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        exact_message_preserved=exact_message,
        citations_valid=citations_valid,
        freshness_valid=freshness_valid,
        protected_atom_coverage=protected_coverage,
        explicit_reference_coverage=explicit_coverage,
        security_overrides=list(security_overrides),
        failures=failures,
        replay_hash=deterministic_replay_hash(
            message_exact=envelope_message,
            snapshot=snapshot,
            items=items,
            context_digest=context_digest,
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            security_overrides=security_overrides,
        ),
        fallback_reason=failures[0] if failures else None,
    )
    return FidelityAuditResult(report=report, next_mode=next_mode)
