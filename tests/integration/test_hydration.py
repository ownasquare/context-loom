from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from context_loom.domain.models import HydrateRequest, ProjectSnapshot, ResourceKind
from context_loom.hydration.retrieval import (
    InMemoryRetrievalSource,
    RepositoryRetrievalSource,
    RetrievalCandidate,
)
from context_loom.hydration.service import HydrationService, RepositoryHydrationRunSink
from context_loom.indexing.sync import WorkspaceSynchronizer
from context_loom.storage.cas import ContentAddressedStore
from context_loom.storage.database import Database
from context_loom.storage.repositories import ContextRepository


def service() -> HydrationService:
    candidates = [
        RetrievalCandidate(
            resource_id="resource-ledger",
            version_id="version-ledger",
            chunk_id="chunk-ledger",
            relative_path="src/payments/ledger.py",
            resource_sha256="a" * 64,
            excerpt="class TokenLedger:\n    MAX_SAVINGS = 95",
            start_line=1,
            end_line=2,
            kind=ResourceKind.CODE,
            estimated_tokens=12,
        ),
        RetrievalCandidate(
            resource_id="resource-policy",
            version_id="version-policy",
            chunk_id="chunk-policy",
            relative_path="AGENTS.md",
            resource_sha256="b" * 64,
            excerpt="Never expose raw prompts or credentials.",
            start_line=1,
            end_line=1,
            kind=ResourceKind.INSTRUCTION,
            estimated_tokens=8,
        ),
    ]
    snapshot = ProjectSnapshot(
        workspace_id="workspace-1",
        generation_id="generation-1",
        root_name="demo",
        indexed_resources=2,
        changed_resources=0,
        generated_at=datetime.now(UTC),
    )
    return HydrationService(InMemoryRetrievalSource(snapshot, candidates))


def test_explicit_path_is_selected_and_message_is_byte_exact() -> None:
    message = "  Review src/payments/ledger.py; never lower MAX_SAVINGS below 95.\n"
    envelope = service().hydrate(
        HydrateRequest(
            workspace_id="workspace-1",
            thread_id="thread-1",
            message=message,
            max_input_tokens=1_000,
            reserve_output_tokens=100,
        )
    )
    assert envelope.message_exact.encode() == message.encode()
    assert "src/payments/ledger.py" in {
        item.citation.relative_path for item in envelope.context_items
    }
    assert envelope.fidelity.protected_atom_coverage == 1.0
    assert envelope.fidelity.explicit_reference_coverage == 1.0
    assert all(item.citation.version_id for item in envelope.context_items)


def test_hydration_replay_hash_is_stable_for_same_snapshot_and_request() -> None:
    request = HydrateRequest(
        workspace_id="workspace-1",
        thread_id="thread-1",
        message="Review src/payments/ledger.py",
    )
    hydration_service = service()
    assert (
        hydration_service.hydrate(request).fidelity.replay_hash
        == hydration_service.hydrate(request).fidelity.replay_hash
    )


def test_budget_omissions_have_recovery_manifest() -> None:
    envelope = service().hydrate(
        HydrateRequest(
            workspace_id="workspace-1",
            message="Review src/payments/ledger.py",
            max_input_tokens=256,
            reserve_output_tokens=220,
        )
    )
    assert envelope.omitted_context
    assert envelope.recovery_manifest == [
        omitted.recoverable_uri for omitted in envelope.omitted_context
    ]
    assert all(
        reference.startswith("context-loom://resources/")
        for reference in envelope.recovery_manifest
    )


def test_repository_sink_persists_metadata_but_not_raw_message_or_excerpts() -> None:
    class RecordingRepository:
        def __init__(self) -> None:
            self.payload: dict[str, object] = {}

        def record_hydration_run(self, **kwargs: object) -> dict[str, object]:
            self.payload = kwargs
            return kwargs

    repository = RecordingRepository()
    message = "Review src/payments/ledger.py and keep this private"
    hydration_service = service()
    hydration_service._sink = RepositoryHydrationRunSink(repository)
    hydration_service.hydrate(
        HydrateRequest(workspace_id="workspace-1", thread_id="thread-1", message=message)
    )
    serialized = str(repository.payload)
    assert message not in serialized
    assert "class TokenLedger" not in serialized
    assert repository.payload["request_sha256"]
    assert repository.payload["items"]


def test_canonical_repository_adapters_hydrate_and_persist_sanitized_metadata(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    source_dir = workspace_root / "src" / "payments"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("ledger.py").write_text(
        "class TokenLedger:\n    MAX_SAVINGS = 95\n", encoding="utf-8"
    )
    repository = ContextRepository(
        Database(tmp_path / "state" / "context-loom.db"),
        ContentAddressedStore(tmp_path / "state" / "objects"),
    )
    workspace = repository.create_workspace("demo", workspace_root)
    WorkspaceSynchronizer(repository).sync(workspace.id)
    hydration_service = HydrationService(
        RepositoryRetrievalSource(repository),
        sink=RepositoryHydrationRunSink(repository),
    )
    message = "Review src/payments/ledger.py without lowering MAX_SAVINGS below 95."
    envelope = hydration_service.hydrate(
        HydrateRequest(
            workspace_id=workspace.id,
            thread_id="thread-1",
            message=message,
            max_input_tokens=1_000,
            reserve_output_tokens=100,
        )
    )
    assert "src/payments/ledger.py" in {
        item.citation.relative_path for item in envelope.context_items
    }
    persisted = repository.get_hydration_run(envelope.hydration_id)
    assert persisted is not None
    serialized = json.dumps(persisted, default=str)
    assert message not in serialized
    assert "class TokenLedger" not in serialized
    assert persisted["baseline_input_tokens"] == envelope.token_plan.baseline.tokens
    assert persisted["fidelity"]["replay_hash"] == envelope.fidelity.replay_hash
