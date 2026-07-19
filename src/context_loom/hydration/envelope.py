"""Canonical conversion and rendering helpers for prompt envelopes."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from context_loom.compaction.protected_atoms import protected_texts
from context_loom.domain.models import ContextItem, ResourceCitation
from context_loom.hydration.scoring import RankedCandidate


def context_item_from_ranked(item: RankedCandidate) -> ContextItem:
    """Convert one ranked sanitized chunk into a fully cited public context item."""

    candidate = item.candidate
    return ContextItem(
        citation=ResourceCitation(
            resource_id=candidate.resource_id,
            version_id=candidate.version_id,
            chunk_id=candidate.chunk_id,
            relative_path=candidate.relative_path,
            sha256=candidate.resource_sha256,
            excerpt_sha256=hashlib.sha256(candidate.excerpt.encode("utf-8")).hexdigest(),
            start_line=candidate.start_line,
            end_line=candidate.end_line,
            stale=candidate.stale,
        ),
        kind=candidate.kind,
        excerpt=candidate.excerpt,
        score=item.score,
        selection_reason=item.ranking_reason,
        protected_atoms=protected_texts(candidate.excerpt),
    )


def context_items_from_ranked(items: Sequence[RankedCandidate]) -> list[ContextItem]:
    return [context_item_from_ranked(item) for item in items]


def render_compiled_prompt(context_digest: str | None, message_exact: str) -> str:
    """Render context around, never instead of, the byte-identical user message."""

    if context_digest:
        return (
            "<context_loom_context>\n"
            f"{context_digest}\n"
            "</context_loom_context>\n"
            "<user_message_exact>\n"
            f"{message_exact}"
            "\n</user_message_exact>"
        )
    return message_exact
