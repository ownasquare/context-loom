"""Deterministic source-preserving context rendering."""

from __future__ import annotations

from collections.abc import Sequence

from context_loom.domain.models import ContextItem


def build_extractive_digest(items: Sequence[ContextItem]) -> str | None:
    """Render exact excerpts with version, hash, and line provenance.

    Excerpts are copied without normalization. Delimiters are metadata owned by Context Loom and do
    not alter the cited source bytes inside each ``excerpt`` field.
    """

    if not items:
        return None
    blocks: list[str] = []
    for index, item in enumerate(items, start=1):
        citation = item.citation
        blocks.append(
            "\n".join(
                (
                    f"[context:{index}]",
                    f"source={citation.relative_path}",
                    f"resource_id={citation.resource_id}",
                    f"version_id={citation.version_id}",
                    f"chunk_id={citation.chunk_id or ''}",
                    f"sha256={citation.sha256}",
                    f"lines={citation.start_line}-{citation.end_line}",
                    "excerpt:",
                    item.excerpt,
                    f"[/context:{index}]",
                )
            )
        )
    return "\n\n".join(blocks)
