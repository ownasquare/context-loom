"""Token-budget allocation that never truncates the user's message."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from urllib.parse import quote

from pydantic import Field

from context_loom.domain.models import OmittedContext, StrictModel
from context_loom.hydration.scoring import RankedCandidate


class BudgetSelection(StrictModel):
    """Selected and recoverable omitted context with explicit budget evidence."""

    selected: list[RankedCandidate]
    omitted: list[OmittedContext]
    message_tokens: int = Field(ge=0)
    framing_tokens: int = Field(ge=0)
    reserved_output_tokens: int = Field(ge=0)
    available_context_tokens: int = Field(ge=0)
    selected_context_tokens: int = Field(ge=0)
    input_budget_overflow: int = Field(default=0, ge=0)


def rough_token_count(text: str) -> int:
    """Conservative credential-free fallback used before a model profile is selected."""

    if not text:
        return 0
    return max(1, math.ceil(len(text.encode("utf-8")) / 3.5))


def allocate_budget(
    ranked: Sequence[RankedCandidate],
    *,
    message_exact: str,
    max_input_tokens: int,
    reserve_output_tokens: int,
    adapter_framing_tokens: int = 64,
    count_tokens: Callable[[str], int] = rough_token_count,
) -> BudgetSelection:
    """Allocate context after reserving the exact message, adapter framing, and answer space."""

    if max_input_tokens < 0 or reserve_output_tokens < 0 or adapter_framing_tokens < 0:
        raise ValueError("token budgets must be non-negative")
    message_tokens = count_tokens(message_exact)
    fixed = message_tokens + reserve_output_tokens + adapter_framing_tokens
    available = max(max_input_tokens - fixed, 0)
    overflow = max(fixed - max_input_tokens, 0)
    selected: list[RankedCandidate] = []
    omitted: list[OmittedContext] = []
    consumed = 0

    for item in ranked:
        candidate = item.candidate
        estimated = candidate.estimated_tokens or count_tokens(candidate.excerpt)
        if candidate.stale:
            reason = "stale_current_generation_gate"
        elif consumed + estimated <= available:
            selected.append(item)
            consumed += estimated
            continue
        elif item.mandatory:
            reason = "mandatory_reference_exceeds_reserved_budget"
        else:
            reason = "lower_ranked_than_reserved_budget"
        omitted.append(
            OmittedContext(
                relative_path=candidate.relative_path,
                version_id=candidate.version_id,
                reason=reason,
                recoverable_uri=(
                    "context-loom://resources/"
                    f"{quote(candidate.resource_id, safe='')}/versions/"
                    f"{quote(candidate.version_id, safe='')}#chunk="
                    f"{quote(candidate.chunk_id, safe='')}"
                ),
                estimated_tokens=estimated,
            )
        )

    return BudgetSelection(
        selected=selected,
        omitted=omitted,
        message_tokens=message_tokens,
        framing_tokens=adapter_framing_tokens,
        reserved_output_tokens=reserve_output_tokens,
        available_context_tokens=available,
        selected_context_tokens=consumed,
        input_budget_overflow=overflow,
    )
