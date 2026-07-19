from __future__ import annotations

from context_loom.indexing.chunker import (
    chunk_text,
    hashed_lexical_embedding,
)


def test_chunks_are_deterministic_line_aware_and_byte_located() -> None:
    content = (
        "# Retry policy\n"
        "Use `MAX_RETRIES = 3` in src/retry.py.\n"
        "## Authentication\n"
        "Never retry HTTP 401 or 403.\n"
    )
    first = chunk_text(content, "README.md", target_tokens=12, overlap_tokens=2)
    second = chunk_text(content, "README.md", target_tokens=12, overlap_tokens=2)

    assert first == second
    assert len(first) >= 2
    encoded = content.encode()
    for chunk in first:
        assert encoded[chunk.start_byte : chunk.end_byte].decode() == chunk.text
        assert chunk.start_line <= chunk.end_line
        assert len(chunk.embedding) == 64
        assert len(chunk.embedding_digest) == 64
    atoms = {atom for chunk in first for atom in chunk.protected_atoms}
    assert {"`MAX_RETRIES = 3`", "src/retry.py", "401", "403"} <= atoms
    assert "Never retry HTTP 401 or 403." in atoms


def test_hashed_embedding_is_stable_and_lexically_sensitive() -> None:
    retry = hashed_lexical_embedding("retry gateway gateway")
    same = hashed_lexical_embedding("retry gateway gateway")
    unrelated = hashed_lexical_embedding("database migration")
    assert retry == same
    assert retry != unrelated


def test_minified_lines_are_bounded_without_breaking_utf8() -> None:
    content = "const value = 'é';" * 100
    chunks = chunk_text(content, "bundle.js", target_tokens=16, overlap_tokens=2)

    assert len(chunks) > 1
    assert all(chunk.token_estimate <= 16 for chunk in chunks)
    encoded = content.encode()
    assert all(
        encoded[chunk.start_byte : chunk.end_byte].decode() == chunk.text for chunk in chunks
    )
