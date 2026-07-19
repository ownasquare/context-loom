from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from context_loom.domain.models import UsageObservation
from context_loom.storage import ContentAddressedStore, ContextRepository, Database
from context_loom.storage.repositories import (
    ChunkInput,
    HydrationNotFound,
    HydrationThreadMismatch,
    HydrationUsageConflict,
    IdempotencyConflict,
    ResourceInput,
    ThreadNotFound,
    ThreadWorkspaceConflict,
)


def _repository(tmp_path: Path) -> tuple[ContextRepository, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    return (
        ContextRepository(
            Database(state / "context-loom.db"),
            ContentAddressedStore(state / "objects"),
        ),
        workspace,
    )


def _resource(repository: ContextRepository, text: str = "retry gateway failure") -> ResourceInput:
    encoded = text.encode()
    digest = hashlib.sha256(encoded).hexdigest()
    vector = (1.0, 0.0)
    vector_digest = hashlib.sha256(b"[1.0,0.0]").hexdigest()
    return ResourceInput(
        relative_path="src/retry.py",
        kind="code",
        origin="file",
        sha256=digest,
        cas_digest=repository.cas.put(encoded),
        size_bytes=len(encoded),
        mtime_ns=1,
        inode=1,
        device=1,
        redacted_count=0,
        parser_fingerprint="test-parser",
        chunker_fingerprint="test-chunker",
        chunks=(
            ChunkInput(
                ordinal=0,
                text=text,
                content_sha256=digest,
                start_byte=0,
                end_byte=len(encoded),
                start_line=1,
                end_line=1,
                token_estimate=4,
                protected_atoms=(),
                embedding=vector,
                embedding_digest=vector_digest,
            ),
        ),
    )


def test_repository_workspace_publish_search_and_restart(tmp_path: Path) -> None:
    repository, workspace_root = _repository(tmp_path)
    workspace = repository.create_workspace("Demo", workspace_root, workspace_id="demo")
    resource = _resource(repository)
    published = repository.publish_generation(
        workspace.id,
        (resource,),
        (),
        source_fingerprint="1" * 64,
        duration_ms=1.5,
    )

    assert [item.id for item in repository.list_workspaces()] == ["demo"]
    assert repository.get_workspace("missing") is None
    assert repository.get_workspace_status("demo").indexed_resources == 1
    match = repository.search_chunks("demo", "gateway retry")[0]
    assert match["relative_path"] == "src/retry.py"
    assert match["resource_sha256"] == resource.sha256
    assert match["content"] == "retry gateway failure"
    assert repository.get_current_chunk(match["chunk_id"], version_id=match["version_id"])
    assert repository.get_resource_content("demo", "src/retry.py") == resource.chunks[0].text

    restarted = ContextRepository(repository.database, repository.cas)
    assert restarted.get_workspace_status("demo").active_generation_id == published.generation_id
    assert restarted.search_chunks("demo", "gateway")[0]["chunk_id"] == match["chunk_id"]


def test_repository_resolves_historical_sanitized_resource_versions(tmp_path: Path) -> None:
    repository, workspace_root = _repository(tmp_path)
    repository.create_workspace("Demo", workspace_root, workspace_id="demo")
    original = _resource(repository, "original retry policy")
    repository.publish_generation(
        "demo",
        (original,),
        (),
        source_fingerprint="1" * 64,
        duration_ms=1,
    )
    current = repository.get_resource("demo", "src/retry.py")
    assert current is not None
    resource_id = str(current["resource_id"])
    original_version = str(current["version_id"])

    updated = _resource(repository, "updated retry policy")
    repository.publish_generation(
        "demo",
        (updated,),
        (),
        source_fingerprint="2" * 64,
        duration_ms=1,
    )

    recovered = repository.get_resource_version(resource_id, original_version)
    assert recovered is not None
    assert recovered["content"] == "original retry policy"
    assert recovered["relative_path"] == "src/retry.py"
    assert recovered["current"] is False
    assert repository.get_resource_version(resource_id, "missing") is None


def test_repository_usage_is_idempotent_and_aggregate_friendly(tmp_path: Path) -> None:
    repository, workspace_root = _repository(tmp_path)
    repository.create_workspace("Demo", workspace_root, workspace_id="demo")
    repository.record_hydration_run(
        hydration_id="hydration-1",
        idempotency_key="hydrate-once",
        thread_id="thread-1",
        workspace_id="demo",
        request_sha256="a" * 64,
        adapter="generic",
        requested_mode="hybrid_safe",
        effective_mode="strict_extractive",
        status="passed",
        baseline_input_tokens=100,
        hydrated_input_tokens=40,
        result={"retained": "metadata only"},
    )
    event = UsageObservation(
        idempotency_key="usage-once",
        thread_id="thread-1",
        hydration_id="hydration-1",
        provider="test-provider",
        model="test-model",
        actual_input_tokens=44,
        actual_output_tokens=12,
    )

    assert repository.list_thread_hydration_rows("thread-1")[0]["usage_recorded"] == 0
    assert repository.record_usage_event(event)["inserted"] is True
    assert repository.record_usage_event(event)["inserted"] is False
    assert repository.count_usage_events("thread-1") == 1
    aggregate = repository.thread_aggregate_rows("thread-1")
    assert aggregate["hydrations"][0]["baseline_input_tokens"] == 100
    assert aggregate["hydrations"][0]["usage_recorded"] == 1
    assert aggregate["usage"][0]["actual_input_tokens"] == 44
    assert repository.get_hydration_run("hydration-1")["result"] == {"retained": "metadata only"}

    with pytest.raises(IdempotencyConflict):
        repository.record_usage_event(event.model_copy(update={"actual_input_tokens": 45}))


def test_repository_persists_thread_label_across_multiple_hydrations(tmp_path: Path) -> None:
    repository, workspace_root = _repository(tmp_path)
    repository.create_workspace("Demo", workspace_root, workspace_id="demo")

    for ordinal in range(2):
        repository.record_hydration_run(
            hydration_id=f"hydration-{ordinal}",
            thread_id="thread-1",
            thread_label="Retry policy review" if ordinal == 0 else None,
            workspace_id="demo",
            request_sha256=str(ordinal) * 64,
            adapter="generic",
            requested_mode="hybrid_safe",
            effective_mode="strict_extractive",
            status="passed",
            baseline_input_tokens=100,
            hydrated_input_tokens=40,
        )

    rows = repository.database.rows(
        "SELECT workspace_id, label FROM threads WHERE id = ?",
        ("thread-1",),
    )
    assert dict(rows[0]) == {"workspace_id": "demo", "label": "Retry policy review"}
    assert len(repository.list_thread_hydration_rows("thread-1")) == 2


def test_repository_rejects_cross_workspace_thread_reuse(tmp_path: Path) -> None:
    repository, first_root = _repository(tmp_path)
    second_root = tmp_path / "workspace-2"
    second_root.mkdir()
    repository.create_workspace("First", first_root, workspace_id="first")
    repository.create_workspace("Second", second_root, workspace_id="second")
    repository.record_hydration_run(
        hydration_id="hydration-first",
        thread_id="shared-thread",
        workspace_id="first",
        request_sha256="a" * 64,
        adapter="generic",
        requested_mode="hybrid_safe",
        effective_mode="strict_extractive",
        status="passed",
    )

    with pytest.raises(ThreadWorkspaceConflict):
        repository.record_hydration_run(
            hydration_id="hydration-second",
            thread_id="shared-thread",
            workspace_id="second",
            request_sha256="b" * 64,
            adapter="generic",
            requested_mode="hybrid_safe",
            effective_mode="strict_extractive",
            status="passed",
        )

    assert repository.get_hydration_run("hydration-second") is None


def test_repository_rejects_usage_without_valid_thread_and_hydration_ownership(
    tmp_path: Path,
) -> None:
    repository, workspace_root = _repository(tmp_path)
    repository.create_workspace("Demo", workspace_root, workspace_id="demo")
    for thread_id, hydration_id in (("thread-1", "hydration-1"), ("thread-2", "hydration-2")):
        repository.record_hydration_run(
            hydration_id=hydration_id,
            thread_id=thread_id,
            workspace_id="demo",
            request_sha256=hydration_id[-1] * 64,
            adapter="generic",
            requested_mode="hybrid_safe",
            effective_mode="strict_extractive",
            status="passed",
        )

    base = UsageObservation(
        idempotency_key="usage-1",
        thread_id="thread-1",
        hydration_id="hydration-1",
        provider="test",
        model="test-model",
        actual_input_tokens=40,
    )
    with pytest.raises(ThreadNotFound):
        repository.record_usage_event(
            base.model_copy(
                update={
                    "idempotency_key": "unknown-thread",
                    "thread_id": "missing-thread",
                    "hydration_id": None,
                }
            )
        )
    with pytest.raises(HydrationNotFound):
        repository.record_usage_event(
            base.model_copy(
                update={"idempotency_key": "unknown-hydration", "hydration_id": "missing"}
            )
        )
    with pytest.raises(HydrationThreadMismatch):
        repository.record_usage_event(
            base.model_copy(
                update={
                    "idempotency_key": "wrong-thread",
                    "thread_id": "thread-2",
                }
            )
        )

    assert repository.record_usage_event(base)["inserted"] is True
    with pytest.raises(HydrationUsageConflict):
        repository.record_usage_event(
            base.model_copy(update={"idempotency_key": "usage-2", "actual_input_tokens": 41})
        )

    assert repository.count_usage_events() == 1
    assert (
        repository.database.scalar("SELECT COUNT(*) FROM threads WHERE id = ?", ("missing-thread",))
        == 0
    )
