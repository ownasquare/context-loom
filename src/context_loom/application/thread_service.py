"""Harness-neutral thread accounting application service."""

from __future__ import annotations

from collections.abc import Sequence

from context_loom.domain.models import PromptEnvelope, ThreadTokenSummary
from context_loom.tokenization.ledger import (
    ThreadLedgerReport,
    TokenLedger,
    TurnTokenRecord,
    turn_from_envelope,
)
from context_loom.tokenization.usage import NormalizedUsage


class ThreadService:
    """One stable orchestration surface for all adapters and APIs."""

    def __init__(self, ledger: TokenLedger) -> None:
        self._ledger = ledger

    def record_turn(self, record: TurnTokenRecord) -> TurnTokenRecord:
        return self._ledger.record_turn(record)

    def record_hydration(
        self, envelope: PromptEnvelope, *, idempotency_key: str | None = None
    ) -> TurnTokenRecord:
        return self.record_turn(turn_from_envelope(envelope, idempotency_key=idempotency_key))

    def list_turns(self, thread_id: str) -> Sequence[TurnTokenRecord]:
        return self._ledger.list_turns(thread_id)

    def record_usage(self, usage: NormalizedUsage) -> NormalizedUsage:
        return self._ledger.record_usage(usage)

    def get_summary(self, thread_id: str) -> ThreadTokenSummary:
        return self._ledger.thread_summary(thread_id)

    def get_report(self, thread_id: str) -> ThreadLedgerReport:
        return self._ledger.thread_report(thread_id)
