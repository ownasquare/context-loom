from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from context_loom.compaction.protected_atoms import protected_texts
from context_loom.domain.models import ProjectSnapshot
from context_loom.hydration.intent import analyze_intent
from context_loom.hydration.retrieval import (
    InMemoryRetrievalSource,
    RetrievalCandidate,
    collect_candidates,
)
from context_loom.hydration.scoring import rank_candidates


def test_retrieval_golden_cases_meet_recall_and_protection_targets() -> None:
    fixture_path = Path(__file__).parents[3] / "evals" / "retrieval-cases.json"
    fixture = json.loads(fixture_path.read_text())
    explicit_hits = 0
    explicit_total = 0
    protected_hits = 0
    protected_total = 0

    for index, case in enumerate(fixture["cases"]):
        expected_paths = case.get("expected_paths", [])
        expected_symbols = case.get("expected_symbols", [])
        candidates = [
            RetrievalCandidate(
                resource_id=f"resource-{index}-{candidate_index}",
                version_id=f"version-{index}-{candidate_index}",
                chunk_id=f"chunk-{index}-{candidate_index}",
                relative_path=path,
                resource_sha256="a" * 64,
                excerpt=f"Relevant implementation for {' '.join(expected_symbols)}",
                start_line=1,
                end_line=1,
            )
            for candidate_index, path in enumerate(expected_paths or [f"src/case_{index}.py"])
        ]
        snapshot = ProjectSnapshot(
            workspace_id="workspace-1",
            generation_id="generation-1",
            root_name="eval",
            indexed_resources=len(candidates),
            changed_resources=0,
            generated_at=datetime.now(UTC),
        )
        source = InMemoryRetrievalSource(snapshot, candidates)
        intent = analyze_intent(case["message"])
        retrieved = collect_candidates(
            source,
            workspace_id="workspace-1",
            query=case["message"],
            terms=intent.keywords,
            paths=intent.explicit_paths,
            symbols=intent.symbols,
        )
        top_ten = rank_candidates(retrieved, intent)[:10]
        selected_paths = {item.candidate.relative_path for item in top_ten}
        selected_text = "\n".join(item.candidate.excerpt for item in top_ten)
        explicit_hits += sum(path in selected_paths for path in expected_paths)
        explicit_hits += sum(symbol in selected_text for symbol in expected_symbols)
        explicit_total += len(expected_paths) + len(expected_symbols)

        extracted = protected_texts(case["message"])
        for atom in case["protected_atoms"]:
            protected_hits += atom in case["message"] and atom in extracted
            protected_total += 1

    recall_at_ten = explicit_hits / explicit_total
    protected_coverage = protected_hits / protected_total
    assert recall_at_ten >= fixture["targets"]["recall_at_10"]
    assert recall_at_ten == fixture["targets"]["explicit_reference_recall"]
    assert protected_coverage == fixture["targets"]["protected_atom_coverage"]
