from __future__ import annotations

from pathlib import Path

from context_loom.application.thread_service import ThreadService
from context_loom.domain.models import HydrateRequest
from context_loom.hydration.retrieval import RepositoryRetrievalSource
from context_loom.hydration.service import HydrationService, RepositoryHydrationRunSink
from context_loom.indexing.sync import WorkspaceSynchronizer
from context_loom.storage.cas import ContentAddressedStore
from context_loom.storage.database import Database
from context_loom.storage.repositories import ContextRepository
from context_loom.tokenization.ledger import (
    InMemoryUsageStore,
    RepositoryUsageStore,
    TokenLedger,
    estimated_turn,
)
from context_loom.tokenization.usage import NormalizedUsage


def test_thread_service_persists_idempotent_turn_and_returns_lifetime_summary() -> None:
    service = ThreadService(TokenLedger(InMemoryUsageStore()))
    first = estimated_turn(idempotency_key="turn-1", baseline=1_000, hydrated=400)
    second = estimated_turn(idempotency_key="turn-2", baseline=800, hydrated=300)
    service.record_turn(first)
    service.record_turn(second)
    service.record_turn(second)
    summary = service.get_summary("thread-1")
    assert summary.turns == 2
    assert summary.estimated_baseline_input_tokens == 1_800
    assert summary.estimated_hydrated_input_tokens == 700
    assert summary.projected_input_tokens_saved == 1_100
    assert summary.actual_input_tokens is None
    assert summary.actual_usage_completeness == 0.0


def test_repository_usage_store_survives_restart_and_joins_later_usage(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    workspace_root.joinpath("app.py").write_text("MAX_INPUT = 4000\n", encoding="utf-8")
    repository = ContextRepository(
        Database(tmp_path / "state" / "context-loom.db"),
        ContentAddressedStore(tmp_path / "state" / "objects"),
    )
    workspace = repository.create_workspace("demo", workspace_root)
    WorkspaceSynchronizer(repository).sync(workspace.id)
    hydration = HydrationService(
        RepositoryRetrievalSource(repository),
        sink=RepositoryHydrationRunSink(repository),
    ).hydrate(
        HydrateRequest(
            workspace_id=workspace.id,
            thread_id="thread-persisted",
            message="Review app.py and keep MAX_INPUT at 4000",
        )
    )
    initial_service = ThreadService(TokenLedger(RepositoryUsageStore(repository)))
    initial_service.record_hydration(hydration)
    initial_service.record_usage(
        NormalizedUsage(
            idempotency_key="usage-1",
            thread_id="thread-persisted",
            hydration_id=hydration.hydration_id,
            provider="openai",
            model="gpt-4o",
            input_tokens=hydration.token_plan.hydrated.tokens + 2,
            output_tokens=40,
            billable_input_tokens=hydration.token_plan.hydrated.tokens,
            billable_output_tokens=35,
        )
    )

    restarted_service = ThreadService(TokenLedger(RepositoryUsageStore(repository)))
    summary = restarted_service.get_summary("thread-persisted")
    assert summary.turns == 1
    assert summary.estimated_baseline_input_tokens == hydration.token_plan.baseline.tokens
    assert summary.estimated_hydrated_input_tokens == hydration.token_plan.hydrated.tokens
    assert summary.actual_input_tokens == hydration.token_plan.hydrated.tokens + 2
    assert summary.actual_output_tokens == 40
    assert summary.actual_usage_completeness == 1.0
    report = restarted_service.get_report("thread-persisted")
    assert report.billable_input_tokens == hydration.token_plan.hydrated.tokens
    assert report.billable_output_tokens == 35
