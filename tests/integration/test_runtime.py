from __future__ import annotations

from pathlib import Path

import pytest

from context_loom.api.errors import ContextLoomError
from context_loom.config import Settings
from context_loom.domain.models import (
    CountingMethod,
    HydrateRequest,
    UsageObservation,
    WorkspaceCreate,
)
from context_loom.runtime import ContextLoomRuntime


@pytest.fixture
def runtime(tmp_path: Path) -> ContextLoomRuntime:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "retry.py").write_text(
        "MAX_RETRIES = 3\n\ndef retry_delay(attempt: int) -> int:\n    return attempt * 2\n",
        encoding="utf-8",
    )
    return ContextLoomRuntime(Settings(home=tmp_path / "state"))


@pytest.mark.integration
async def test_runtime_hydrates_and_accounts_without_persisting_raw_message(
    runtime: ContextLoomRuntime, tmp_path: Path
) -> None:
    assert (await runtime.health()).retain_message_content is False
    workspace = await runtime.create_workspace(
        WorkspaceCreate(name="demo", root_path=str(tmp_path / "workspace"))
    )
    report = await runtime.sync_workspace(workspace.id)
    assert report.added >= 1

    envelope = await runtime.hydrate(
        HydrateRequest(
            workspace_id=workspace.id,
            thread_id="thread-1",
            message="Where is MAX_RETRIES used?",
        )
    )
    assert envelope.message_exact == "Where is MAX_RETRIES used?"
    assert envelope.context_items
    persisted = runtime.repository.get_hydration_run(envelope.hydration_id)
    assert persisted is not None
    assert persisted["result"]["token_plan"]["baseline"]["tokens"] >= 0
    assert "message_exact" not in persisted["result"]

    summary = await runtime.record_usage(
        UsageObservation(
            idempotency_key="usage-1",
            thread_id="thread-1",
            hydration_id=envelope.hydration_id,
            provider="test",
            model="test-model",
            counting_method=CountingMethod.PROVIDER_OBSERVED,
            actual_input_tokens=23,
            actual_output_tokens=5,
            verified_baseline_input_tokens=40,
        )
    )
    assert summary.turns == 1
    assert summary.actual_input_tokens == 23
    assert summary.verified_counterfactual_tokens_saved == 17
    assert summary.actual_usage_completeness == 1.0


@pytest.mark.integration
async def test_runtime_reloads_retained_hydration(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Retry policy\nUse three retries.\n")
    settings = Settings(home=tmp_path / "state", retain_message_content=True)
    first = ContextLoomRuntime(settings)
    assert (await first.health()).retain_message_content is True
    workspace = await first.create_workspace(
        WorkspaceCreate(name="demo", root_path=str(workspace_root))
    )
    await first.sync_workspace(workspace.id)
    envelope = await first.hydrate(
        HydrateRequest(workspace_id=workspace.id, message="Explain retry policy")
    )

    reloaded = ContextLoomRuntime(settings)
    restored = await reloaded.get_hydration(envelope.hydration_id)
    assert restored == envelope


@pytest.mark.integration
async def test_runtime_degraded_health_still_discloses_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = ContextLoomRuntime(Settings(home=tmp_path / "state", retain_message_content=True))

    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise OSError("database unavailable")

    monkeypatch.setattr(runtime.database, "scalar", unavailable)
    health = await runtime.health()

    assert health.status == "degraded"
    assert health.database == "unavailable"
    assert health.retain_message_content is True


@pytest.mark.integration
async def test_runtime_bounds_ephemeral_raw_hydration_cache(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Retry policy\nUse three retries.\n")
    runtime = ContextLoomRuntime(
        Settings(
            home=tmp_path / "state",
            retain_message_content=False,
            hydration_cache_max_entries=1,
        )
    )
    workspace = await runtime.create_workspace(
        WorkspaceCreate(name="demo", root_path=str(workspace_root))
    )
    await runtime.sync_workspace(workspace.id)
    first = await runtime.hydrate(
        HydrateRequest(workspace_id=workspace.id, message="First exact message")
    )
    second = await runtime.hydrate(
        HydrateRequest(workspace_id=workspace.id, message="Second exact message")
    )

    with pytest.raises(ContextLoomError) as evicted:
        await runtime.get_hydration(first.hydration_id)
    assert evicted.value.code == "hydration_content_not_retained"
    assert await runtime.get_hydration(second.hydration_id) == second


@pytest.mark.integration
async def test_runtime_requires_sync_before_hydration(
    runtime: ContextLoomRuntime, tmp_path: Path
) -> None:
    workspace = await runtime.create_workspace(
        WorkspaceCreate(name="demo", root_path=str(tmp_path / "workspace"))
    )
    with pytest.raises(ContextLoomError) as captured:
        await runtime.hydrate(HydrateRequest(workspace_id=workspace.id, message="Explain it"))
    assert captured.value.code == "workspace_not_synced"


@pytest.mark.integration
async def test_runtime_aggregates_two_hydrations_under_one_durable_thread_label(
    runtime: ContextLoomRuntime, tmp_path: Path
) -> None:
    workspace = await runtime.create_workspace(
        WorkspaceCreate(name="demo", root_path=str(tmp_path / "workspace"))
    )
    await runtime.sync_workspace(workspace.id)

    first = await runtime.hydrate(
        HydrateRequest(
            workspace_id=workspace.id,
            thread_id="thread-1",
            thread_label="Retry policy review",
            message="Where is MAX_RETRIES used?",
        )
    )
    second = await runtime.hydrate(
        HydrateRequest(
            workspace_id=workspace.id,
            thread_id="thread-1",
            message="How is the retry delay computed?",
        )
    )

    assert first.metadata["thread_label"] == "Retry policy review"
    assert "thread_label" not in second.metadata
    threads = await runtime.list_threads(workspace.id)
    assert len(threads) == 1
    assert threads[0].thread_id == "thread-1"
    assert threads[0].label == "Retry policy review"
    assert threads[0].turns == 2
    assert [turn.hydration_id for turn in threads[0].history] == [
        first.hydration_id,
        second.hydration_id,
    ]
    assert [turn.usage_recorded for turn in threads[0].history] == [False, False]

    await runtime.record_usage(
        UsageObservation(
            idempotency_key="usage-output-only",
            thread_id="thread-1",
            hydration_id=second.hydration_id,
            provider="test",
            model="test-model",
            actual_output_tokens=9,
        )
    )
    threads = await runtime.list_threads(workspace.id)
    assert [turn.usage_recorded for turn in threads[0].history] == [False, True]
    assert threads[0].history[1].actual_input_tokens is None
    restarted_threads = await ContextLoomRuntime(runtime.settings).list_threads(workspace.id)
    assert restarted_threads[0].label == "Retry policy review"
    assert restarted_threads[0].turns == 2
    assert [turn.usage_recorded for turn in restarted_threads[0].history] == [False, True]


@pytest.mark.integration
async def test_runtime_keeps_thread_ids_isolated_to_their_first_workspace(tmp_path: Path) -> None:
    runtime = ContextLoomRuntime(Settings(home=tmp_path / "state"))
    roots = [tmp_path / "first", tmp_path / "second"]
    for ordinal, root in enumerate(roots):
        root.mkdir()
        (root / "README.md").write_text(f"# Workspace {ordinal}\n", encoding="utf-8")
    first = await runtime.create_workspace(WorkspaceCreate(name="First", root_path=str(roots[0])))
    second = await runtime.create_workspace(WorkspaceCreate(name="Second", root_path=str(roots[1])))
    await runtime.sync_workspace(first.id)
    await runtime.sync_workspace(second.id)
    await runtime.hydrate(
        HydrateRequest(
            workspace_id=first.id,
            thread_id="shared-thread",
            message="Summarize the first workspace",
        )
    )

    with pytest.raises(ContextLoomError) as captured:
        await runtime.hydrate(
            HydrateRequest(
                workspace_id=second.id,
                thread_id="shared-thread",
                message="Summarize the second workspace",
            )
        )

    assert captured.value.code == "thread_workspace_conflict"
    assert captured.value.status_code == 409
    assert len(await runtime.list_threads(first.id)) == 1
    assert await runtime.list_threads(second.id) == []


@pytest.mark.integration
async def test_runtime_rejects_usage_ownership_errors_without_creating_ghost_threads(
    runtime: ContextLoomRuntime, tmp_path: Path
) -> None:
    workspace = await runtime.create_workspace(
        WorkspaceCreate(name="demo", root_path=str(tmp_path / "workspace"))
    )
    await runtime.sync_workspace(workspace.id)
    first = await runtime.hydrate(
        HydrateRequest(
            workspace_id=workspace.id,
            thread_id="thread-1",
            message="Where is MAX_RETRIES used?",
        )
    )
    await runtime.hydrate(
        HydrateRequest(
            workspace_id=workspace.id,
            thread_id="thread-2",
            message="Explain the retry delay",
        )
    )

    unknown_thread = UsageObservation(
        idempotency_key="unknown-thread",
        thread_id="missing-thread",
        provider="test",
        model="test-model",
        actual_input_tokens=10,
    )
    with pytest.raises(ContextLoomError) as missing_thread:
        await runtime.record_usage(unknown_thread)
    assert missing_thread.value.code == "not_found"
    assert missing_thread.value.status_code == 404

    with pytest.raises(ContextLoomError) as missing_hydration:
        await runtime.record_usage(
            unknown_thread.model_copy(
                update={
                    "idempotency_key": "unknown-hydration",
                    "thread_id": "thread-1",
                    "hydration_id": "missing-hydration",
                }
            )
        )
    assert missing_hydration.value.code == "not_found"
    assert missing_hydration.value.status_code == 404

    with pytest.raises(ContextLoomError) as wrong_thread:
        await runtime.record_usage(
            unknown_thread.model_copy(
                update={
                    "idempotency_key": "wrong-thread",
                    "thread_id": "thread-2",
                    "hydration_id": first.hydration_id,
                }
            )
        )
    assert wrong_thread.value.code == "hydration_thread_mismatch"
    assert wrong_thread.value.status_code == 409

    valid = unknown_thread.model_copy(
        update={
            "idempotency_key": "usage-1",
            "thread_id": "thread-1",
            "hydration_id": first.hydration_id,
        }
    )
    await runtime.record_usage(valid)
    with pytest.raises(ContextLoomError) as duplicate_hydration:
        await runtime.record_usage(
            valid.model_copy(update={"idempotency_key": "usage-2", "actual_input_tokens": 11})
        )
    assert duplicate_hydration.value.code == "hydration_usage_conflict"
    assert duplicate_hydration.value.status_code == 409
    assert runtime.repository.count_usage_events() == 1
    assert (
        runtime.database.scalar("SELECT COUNT(*) FROM threads WHERE id = ?", ("missing-thread",))
        == 0
    )
