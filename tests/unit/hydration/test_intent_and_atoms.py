from __future__ import annotations

from context_loom.compaction.protected_atoms import (
    ProtectedAtomKind,
    extract_protected_atoms,
)
from context_loom.hydration.intent import analyze_intent


def test_message_does_not_route_to_email_tool_from_message_substring() -> None:
    profile = analyze_intent("compact this chat message")
    assert "email" not in profile.tool_routes


def test_email_routes_only_from_a_complete_word() -> None:
    assert "email" in analyze_intent("send this email after review").tool_routes
    assert "email" not in analyze_intent("the remailer module is broken").tool_routes


def test_extracts_protected_atoms_exactly() -> None:
    message = (
        "Review src/payments/ledger.py and TokenLedger.record_turn at "
        "https://localhost:8768/api. Run `uv run pytest tests/unit -q`; never lower >=95% "
        'or the LIMIT_P0 policy. Keep "database is locked" exact.'
    )
    atoms = extract_protected_atoms(message, policy_labels=["LIMIT_P0"])
    by_kind = {
        kind: [atom.text for atom in atoms if atom.kind is kind] for kind in ProtectedAtomKind
    }
    assert "src/payments/ledger.py" in by_kind[ProtectedAtomKind.PATH]
    assert "TokenLedger.record_turn" in by_kind[ProtectedAtomKind.SYMBOL]
    assert "https://localhost:8768/api" in by_kind[ProtectedAtomKind.URL]
    assert "uv run pytest tests/unit -q" in by_kind[ProtectedAtomKind.COMMAND]
    assert ">=95%" in by_kind[ProtectedAtomKind.THRESHOLD]
    assert any(
        guard.startswith("never lower") for guard in by_kind[ProtectedAtomKind.NEGATIVE_GUARD]
    )
    assert "LIMIT_P0" in by_kind[ProtectedAtomKind.POLICY_LABEL]
    assert "database is locked" in by_kind[ProtectedAtomKind.QUOTED_SIGNAL]


def test_protected_atom_extraction_is_deterministic() -> None:
    message = "Do not change src/app.py or threshold 80%."
    assert extract_protected_atoms(message) == extract_protected_atoms(message)


def test_url_segments_are_not_misclassified_as_explicit_paths() -> None:
    profile = analyze_intent("Inspect https://localhost:8768/api/v1/status")
    assert profile.explicit_paths == []


def test_bare_file_and_natural_language_threshold_are_protected() -> None:
    atoms = extract_protected_atoms("Review README.md with threshold 4000 tokens.")
    assert any(atom.kind is ProtectedAtomKind.PATH and atom.text == "README.md" for atom in atoms)
    assert any(
        atom.kind is ProtectedAtomKind.THRESHOLD and atom.text == "threshold 4000 tokens"
        for atom in atoms
    )
