from __future__ import annotations

from datetime import UTC, datetime

from context_loom.domain.models import ProjectSnapshot, ResourceKind
from context_loom.hydration.intent import analyze_intent
from context_loom.hydration.retrieval import (
    InMemoryRetrievalSource,
    RetrievalCandidate,
    collect_candidates,
)
from context_loom.hydration.scoring import rank_candidates


def candidate(
    chunk_id: str,
    path: str,
    excerpt: str,
    *,
    kind: ResourceKind = ResourceKind.CODE,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        resource_id=f"resource-{chunk_id}",
        version_id=f"version-{chunk_id}",
        chunk_id=chunk_id,
        relative_path=path,
        resource_sha256="a" * 64,
        excerpt=excerpt,
        start_line=1,
        end_line=3,
        kind=kind,
    )


def source(items: list[RetrievalCandidate]) -> InMemoryRetrievalSource:
    return InMemoryRetrievalSource(
        ProjectSnapshot(
            workspace_id="workspace-1",
            generation_id="generation-1",
            root_name="demo",
            indexed_resources=len(items),
            changed_resources=0,
            generated_at=datetime.now(UTC),
        ),
        items,
    )


def test_direct_reference_is_forced_ahead_of_higher_lexical_match() -> None:
    items = [
        candidate("direct", "src/payments/ledger.py", "class Ledger: pass"),
        candidate("other", "docs/payments.md", "ledger ledger ledger payment review"),
    ]
    intent = analyze_intent("Review src/payments/ledger.py payment behavior")
    retrieved = collect_candidates(
        source(items),
        workspace_id="workspace-1",
        query="Review src/payments/ledger.py payment behavior",
        terms=intent.keywords,
        paths=intent.explicit_paths,
        symbols=intent.symbols,
    )
    ranked = rank_candidates(retrieved, intent)
    assert ranked[0].candidate.relative_path == "src/payments/ledger.py"
    assert ranked[0].mandatory is True
    assert ranked[0].score.direct_reference == 1.0


def test_instruction_resources_are_mandatory_and_scores_are_explainable() -> None:
    items = [
        candidate("policy", "AGENTS.md", "Never expose secrets", kind=ResourceKind.INSTRUCTION),
        candidate("code", "src/app.py", "def expose(): pass"),
    ]
    intent = analyze_intent("review expose")
    retrieved = collect_candidates(
        source(items),
        workspace_id="workspace-1",
        query="review expose",
        terms=intent.keywords,
        paths=[],
        symbols=[],
    )
    ranked = rank_candidates(retrieved, intent)
    policy = next(item for item in ranked if item.candidate.relative_path == "AGENTS.md")
    assert policy.mandatory
    assert policy.score.authority == 1.0
    assert "mandatory_policy" in policy.ranking_reason


def test_mmr_order_is_deterministic() -> None:
    items = [
        candidate("a", "a.py", "alpha beta gamma"),
        candidate("b", "b.py", "alpha beta gamma"),
        candidate("c", "c.py", "alpha delta epsilon"),
    ]
    intent = analyze_intent("alpha")
    retrieved = collect_candidates(
        source(items),
        workspace_id="workspace-1",
        query="alpha",
        terms=intent.keywords,
        paths=[],
        symbols=[],
    )
    assert rank_candidates(retrieved, intent) == rank_candidates(retrieved, intent)
