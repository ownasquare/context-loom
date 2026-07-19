from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from context_loom.storage import database as database_module
from context_loom.storage.database import Database, MigrationError
from context_loom.storage.migrations import MIGRATIONS


def test_database_migrates_once_and_uses_wal(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "context-loom.db")
    database.initialize()
    database.initialize()

    assert str(database.scalar("PRAGMA journal_mode")).casefold() == "wal"
    assert database.scalar("SELECT MAX(version) FROM schema_migrations") == 3
    assert database.scalar("SELECT COUNT(*) FROM schema_migrations") == 3
    thread_columns = {str(row["name"]) for row in database.rows("PRAGMA table_info(threads)")}
    assert "label" in thread_columns
    assert stat.S_IMODE(database.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(database.path.parent.stat().st_mode) == 0o700


def test_database_rejects_changed_forward_history(tmp_path: Path) -> None:
    database = Database(tmp_path / "context-loom.db")
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = 1",
            ("0" * 64,),
        )

    with pytest.raises(MigrationError, match="differs from applied history"):
        database.initialize()


def test_database_advances_existing_v2_catalog_to_thread_label_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "context-loom.db")
    with monkeypatch.context() as older_release:
        older_release.setattr(database_module, "MIGRATIONS", MIGRATIONS[:2])
        older_release.setattr(database_module, "latest_version", lambda: 2)
        database.initialize()

    assert database.scalar("SELECT MAX(version) FROM schema_migrations") == 2
    database.initialize()

    assert database.scalar("SELECT MAX(version) FROM schema_migrations") == 3
    assert "label" in {str(row["name"]) for row in database.rows("PRAGMA table_info(threads)")}
    assert (
        database.scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = ? AND name = ?",
            ("trigger", "usage_events_one_observation_per_hydration"),
        )
        == 1
    )


def test_wal_allows_concurrent_readers_during_write_transaction(tmp_path: Path) -> None:
    database = Database(tmp_path / "context-loom.db")
    database.initialize()
    with database.transaction() as writer:
        writer.execute(
            """
            INSERT INTO workspaces(id, name, root_path, created_at, updated_at)
            VALUES ('pending', 'pending', '/pending', 'now', 'now')
            """
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            observed = list(
                pool.map(
                    lambda _: database.scalar("SELECT COUNT(*) FROM workspaces"),
                    range(2),
                )
            )
        assert observed == [0, 0]

    assert database.scalar("SELECT COUNT(*) FROM workspaces") == 1
    assert os.access(database.path, os.R_OK | os.W_OK)
