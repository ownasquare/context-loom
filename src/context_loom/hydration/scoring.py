"""Explainable hybrid scoring and deterministic maximal-marginal-relevance ordering."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import Field

from context_loom.domain.models import IntentProfile, ResourceKind, ScoreBreakdown, StrictModel
from context_loom.hydration.retrieval import RetrievalCandidate

_TERM_RE = re.compile(r"[A-Za-z0-9_]+")
_DEFAULT_AUTHORITY = {
    ResourceKind.INSTRUCTION: 1.0,
    ResourceKind.VALIDATION: 0.9,
    ResourceKind.TEST: 0.85,
    ResourceKind.CODE: 0.8,
    ResourceKind.CONFIGURATION: 0.8,
    ResourceKind.DOCUMENTATION: 0.7,
    ResourceKind.TOOL_CATALOG: 0.65,
    ResourceKind.MCP_CATALOG: 0.65,
    ResourceKind.OTHER: 0.5,
}


class ScoreWeights(StrictModel):
    """Weights for base relevance; values intentionally need not sum to one."""

    lexical: float = Field(default=0.30, ge=0)
    dense: float = Field(default=0.22, ge=0)
    direct_reference: float = Field(default=0.28, ge=0)
    recency: float = Field(default=0.05, ge=0)
    authority: float = Field(default=0.10, ge=0)
    thread_affinity: float = Field(default=0.05, ge=0)
    stale_penalty: float = Field(default=0.75, ge=0)


class RankedCandidate(StrictModel):
    """A candidate with preserved score evidence and deterministic MMR evidence."""

    candidate: RetrievalCandidate
    score: ScoreBreakdown
    mandatory: bool = False
    mmr_score: float = 0.0
    ranking_reason: str


def _normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def _direct_match(candidate: RetrievalCandidate, intent: IntentProfile) -> bool:
    paths = {_normalized_path(path) for path in intent.explicit_paths}
    return candidate.direct_match or _normalized_path(candidate.relative_path) in paths


def score_candidate(
    candidate: RetrievalCandidate,
    intent: IntentProfile,
    *,
    weights: ScoreWeights | None = None,
) -> RankedCandidate:
    """Compute a fully explainable hybrid score for one candidate."""

    active_weights = weights or ScoreWeights()
    direct = 1.0 if _direct_match(candidate, intent) else 0.0
    authority = (
        candidate.authority_score
        if candidate.authority_score is not None
        else _DEFAULT_AUTHORITY[candidate.kind]
    )
    penalty = active_weights.stale_penalty if candidate.stale else 0.0
    total = (
        candidate.lexical_score * active_weights.lexical
        + candidate.dense_score * active_weights.dense
        + direct * active_weights.direct_reference
        + candidate.recency_score * active_weights.recency
        + authority * active_weights.authority
        + candidate.thread_affinity_score * active_weights.thread_affinity
        - penalty
    )
    mandatory = bool(direct or candidate.kind is ResourceKind.INSTRUCTION)
    reasons = []
    if direct:
        reasons.append(candidate.direct_match_reason or "direct_reference")
    if candidate.kind is ResourceKind.INSTRUCTION:
        reasons.append("mandatory_policy")
    if candidate.lexical_score:
        reasons.append("lexical_match")
    if candidate.dense_score:
        reasons.append("vector_match")
    if candidate.stale:
        reasons.append("stale_penalty")
    return RankedCandidate(
        candidate=candidate,
        score=ScoreBreakdown(
            lexical=candidate.lexical_score,
            dense=candidate.dense_score,
            direct_reference=direct,
            recency=candidate.recency_score,
            authority=authority,
            thread_affinity=candidate.thread_affinity_score,
            penalty=penalty,
            total=total,
        ),
        mandatory=mandatory,
        ranking_reason=",".join(reasons) or "background_relevance",
    )


def _tokens(candidate: RetrievalCandidate) -> set[str]:
    return {
        term.casefold()
        for term in _TERM_RE.findall(f"{candidate.relative_path} {candidate.excerpt}")
    }


def _similarity(left: RetrievalCandidate, right: RetrievalCandidate) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def rank_candidates(
    candidates: Sequence[RetrievalCandidate],
    intent: IntentProfile,
    *,
    weights: ScoreWeights | None = None,
    diversity: float = 0.25,
) -> list[RankedCandidate]:
    """Order all candidates with direct/policy forcing followed by deterministic MMR."""

    if not 0.0 <= diversity <= 1.0:
        raise ValueError("diversity must be between zero and one")
    pending = [score_candidate(candidate, intent, weights=weights) for candidate in candidates]
    mandatory = sorted(
        (item for item in pending if item.mandatory),
        key=lambda item: (
            -item.score.direct_reference,
            -item.score.authority,
            -item.score.total,
            item.candidate.relative_path,
            item.candidate.chunk_id,
        ),
    )
    remaining = [item for item in pending if not item.mandatory]
    ordered = [
        item.model_copy(
            update={"mmr_score": item.score.total, "ranking_reason": item.ranking_reason}
        )
        for item in mandatory
    ]

    while remaining:
        evaluated: list[tuple[float, RankedCandidate]] = []
        for item in remaining:
            redundancy = max(
                (_similarity(item.candidate, selected.candidate) for selected in ordered),
                default=0.0,
            )
            mmr_score = (1.0 - diversity) * item.score.total - diversity * redundancy
            evaluated.append((mmr_score, item))
        mmr_score, selected = min(
            evaluated,
            key=lambda pair: (
                -pair[0],
                -pair[1].score.total,
                pair[1].candidate.relative_path,
                pair[1].candidate.chunk_id,
            ),
        )
        ordered.append(
            selected.model_copy(
                update={
                    "mmr_score": mmr_score,
                    "ranking_reason": f"{selected.ranking_reason},mmr_diversity",
                }
            )
        )
        remaining.remove(selected)
    return ordered
