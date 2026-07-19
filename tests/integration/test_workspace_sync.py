from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest

from context_loom.indexing.sync import WorkspaceSynchronizer
from context_loom.storage import ContentAddressedStore, ContextRepository, Database


def _services(tmp_path: Path) -> tuple[Path, ContextRepository, WorkspaceSynchronizer]:
    root = tmp_path / "workspace"
    root.mkdir()
    state = tmp_path / "state"
    repository = ContextRepository(
        Database(state / "context-loom.db"),
        ContentAddressedStore(state / "objects"),
    )
    repository.create_workspace("Demo", root, workspace_id="demo")
    return root, repository, WorkspaceSynchronizer(repository, chunk_target_tokens=64)


def test_sync_add_change_delete_rename_reuse_and_restart(tmp_path: Path) -> None:
    root, repository, synchronizer = _services(tmp_path)
    retry = root / "retry.py"
    retry.write_text(
        "MAX_RETRIES = 3\n\ndef should_retry(code: int) -> bool:\n    return code == 503\n"
    )
    (root / "README.md").write_text("# Retry\nRetry gateway failures only.\n")
    (root / "notes.md").write_text("API_KEY=demo-value-that-must-not-persist\n")
    (root / ".env").write_text("REAL_SECRET=excluded\n")

    first = synchronizer.sync("demo")
    assert (first.added, first.modified, first.deleted, first.renamed) == (3, 0, 0, 0)
    assert first.redacted == 1
    assert repository.get_resource("demo", ".env") is None
    assert "demo-value-that-must-not-persist" not in (
        repository.get_resource_content("demo", "notes.md") or ""
    )
    before = repository.get_resource("demo", "retry.py")
    assert before is not None
    before_chunks = repository.search_chunks("demo", "MAX_RETRIES")

    unchanged = synchronizer.sync("demo")
    assert unchanged.unchanged == 3
    assert unchanged.added == unchanged.modified == unchanged.deleted == 0

    (root / "README.md").write_text("# Retry\nRetry 429 and gateway failures only.\n")
    modified = synchronizer.sync("demo")
    assert modified.modified == 1
    assert modified.unchanged == 2

    renamed_path = root / "policy.py"
    retry.rename(renamed_path)
    renamed = synchronizer.sync("demo")
    assert renamed.renamed == 1
    assert renamed.added == renamed.deleted == 0
    after = repository.get_resource("demo", "policy.py")
    assert after is not None
    assert repository.get_resource("demo", "retry.py") is None
    assert after["resource_id"] == before["resource_id"]
    assert after["version_id"] == before["version_id"]
    after_chunks = repository.search_chunks("demo", "MAX_RETRIES")
    assert {item["chunk_id"] for item in after_chunks} == {
        item["chunk_id"] for item in before_chunks
    }
    assert {item["relative_path"] for item in after_chunks} == {"policy.py"}

    (root / "README.md").unlink()
    deleted = synchronizer.sync("demo")
    assert deleted.deleted == 1
    assert repository.get_resource_content("demo", "README.md") is None
    assert repository.get_workspace_status("demo").stale_resources == 1

    restarted = ContextRepository(repository.database, repository.cas)
    restarted_sync = WorkspaceSynchronizer(restarted, chunk_target_tokens=64)
    assert restarted.get_workspace_status("demo").active_generation_id == deleted.generation_id
    assert restarted_sync.sync("demo").unchanged == 2


def test_failed_generation_does_not_replace_published_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repository, synchronizer = _services(tmp_path)
    source = root / "app.py"
    source.write_text("VALUE = 1\n")
    first = synchronizer.sync("demo")
    source.write_text("VALUE = 2\n")

    def fail_chunk_insert(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("injected chunk failure")

    monkeypatch.setattr(repository, "_insert_chunks", fail_chunk_insert)
    with pytest.raises(RuntimeError, match="injected chunk failure"):
        synchronizer.sync("demo")

    status = repository.get_workspace_status("demo")
    assert status.active_generation_id == first.generation_id
    assert repository.get_resource_content("demo", "app.py") == "VALUE = 1\n"
    assert repository.database.scalar("SELECT COUNT(*) FROM index_generations") == 1


def test_readding_a_tombstoned_path_reuses_its_resource_and_version(tmp_path: Path) -> None:
    root, repository, synchronizer = _services(tmp_path)
    source = root / "app.py"
    source.write_text("VALUE = 1\n")
    synchronizer.sync("demo")
    original = repository.get_resource("demo", "app.py")
    assert original is not None

    source.unlink()
    assert synchronizer.sync("demo").deleted == 1
    source.write_text("VALUE = 1\n")
    readded = synchronizer.sync("demo")
    current = repository.get_resource("demo", "app.py")

    assert readded.added == 1
    assert current is not None
    assert current["resource_id"] == original["resource_id"]
    assert current["version_id"] == original["version_id"]
    assert repository.get_workspace_status("demo").stale_resources == 0
