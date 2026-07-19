from __future__ import annotations

from datetime import UTC, datetime

from context_loom.domain.models import (
    CompactionMode,
    ContextItem,
    IntentProfile,
    ProjectSnapshot,
    ResourceCitation,
    ResourceKind,
    ScoreBreakdown,
)
from context_loom.hydration.budget import allocate_budget
from context_loom.hydration.fidelity import audit_fidelity
from context_loom.hydration.retrieval import RetrievalCandidate
from context_loom.hydration.scoring import RankedCandidate


def ranked(*, mandatory: bool = False, stale: bool = False) -> RankedCandidate:
    return RankedCandidate(
        candidate=RetrievalCandidate(
            resource_id="resource-1",
            version_id="version-1",
            chunk_id="chunk-1",
            relative_path="src/app.py",
            resource_sha256="a" * 64,
            excerpt="threshold = 95",
            start_line=1,
            end_line=1,
            stale=stale,
            estimated_tokens=4,
        ),
        score=ScoreBreakdown(total=1.0),
        mandatory=mandatory,
        ranking_reason="direct_reference" if mandatory else "lexical_match",
    )


def test_budget_reserves_message_and_answer_without_truncating_message() -> None:
    message = "  preserve this exact message\n"
    result = allocate_budget(
        [ranked()],
        message_exact=message,
        max_input_tokens=20,
        reserve_output_tokens=5,
        adapter_framing_tokens=2,
        count_tokens=lambda value: len(value.split()),
    )
    assert result.message_tokens == 4
    assert result.selected[0].candidate.excerpt == "threshold = 95"


def test_stale_candidate_is_omitted_even_when_mandatory() -> None:
    result = allocate_budget(
        [ranked(mandatory=True, stale=True)],
        message_exact="Review src/app.py",
        max_input_tokens=100,
        reserve_output_tokens=5,
    )
    assert result.selected == []
    assert result.omitted[0].reason == "stale_current_generation_gate"


def test_fidelity_reports_exact_message_and_deterministic_replay_hash() -> None:
    excerpt = "threshold = 95"
    import hashlib

    item = ContextItem(
        citation=ResourceCitation(
            resource_id="resource-1",
            version_id="version-1",
            chunk_id="chunk-1",
            relative_path="src/app.py",
            sha256="a" * 64,
            excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
            start_line=1,
            end_line=1,
        ),
        kind=ResourceKind.CODE,
        excerpt=excerpt,
        score=ScoreBreakdown(total=1.0),
        selection_reason="direct_reference",
        protected_atoms=["95"],
    )
    snapshot = ProjectSnapshot(
        workspace_id="workspace-1",
        generation_id="generation-1",
        root_name="demo",
        indexed_resources=1,
        changed_resources=0,
        generated_at=datetime.now(UTC),
    )
    kwargs = {
        "original_message": "Review src/app.py and keep 95",
        "envelope_message": "Review src/app.py and keep 95",
        "snapshot": snapshot,
        "intent": IntentProfile(explicit_paths=["src/app.py"]),
        "items": [item],
        "context_digest": "src/app.py threshold = 95",
        "protected_atoms": ["src/app.py", "95"],
        "requested_mode": CompactionMode.HYBRID_SAFE,
        "effective_mode": CompactionMode.HYBRID_SAFE,
    }
    first = audit_fidelity(**kwargs)  # type: ignore[arg-type]
    second = audit_fidelity(**kwargs)  # type: ignore[arg-type]
    assert first.report.exact_message_preserved
    assert first.report.replay_hash == second.report.replay_hash
    assert first.report.protected_atom_coverage == 1.0


def test_fidelity_transitions_hybrid_failure_to_strict_extractive() -> None:
    snapshot = ProjectSnapshot(
        workspace_id="workspace-1",
        generation_id="generation-1",
        root_name="demo",
        indexed_resources=0,
        changed_resources=0,
        generated_at=datetime.now(UTC),
    )
    result = audit_fidelity(
        original_message="exact",
        envelope_message="changed",
        snapshot=snapshot,
        intent=IntentProfile(),
        items=[],
        context_digest=None,
        protected_atoms=[],
        requested_mode=CompactionMode.HYBRID_SAFE,
        effective_mode=CompactionMode.HYBRID_SAFE,
    )
    assert result.next_mode is CompactionMode.STRICT_EXTRACTIVE
    assert "exact_message_not_preserved" in result.report.failures
