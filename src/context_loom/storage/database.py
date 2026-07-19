"""Private SQLite/WAL database lifecycle and transaction helpers."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock

from context_loom.storage.migrations import MIGRATIONS, latest_version


class MigrationError(RuntimeError):
    """Raised when on-disk schema history cannot be advanced safely."""


class Database:
    """Own a SQLite database with WAL, foreign keys, and forward-only migrations."""

    def __init__(self, path: Path | str, *, busy_timeout_ms: int = 5_000) -> None:
        self.path = Path(path).expanduser().resolve()
        self.busy_timeout_ms = busy_timeout_ms
        self._lock_path = self.path.with_suffix(f"{self.path.suffix}.migrate.lock")

    def _prepare_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        current_mode = self.path.parent.stat().st_mode & 0o777
        if current_mode & 0o077:
            os.chmod(self.path.parent, 0o700)

    def _connect(self) -> sqlite3.Connection:
        self._prepare_parent()
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1_000,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA temp_store = MEMORY")
        return connection

    @staticmethod
    def _sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def initialize(self) -> None:
        """Create or advance the schema exactly once under a process-safe lock."""

        self._prepare_parent()
        with FileLock(self._lock_path, timeout=30):
            os.chmod(self._lock_path, 0o600)
            connection = self._connect()
            try:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA wal_autocheckpoint = 1000")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    ) STRICT
                    """
                )
                rows = connection.execute(
                    "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
                applied = {int(row["version"]): row for row in rows}
                if applied and max(applied) > latest_version():
                    raise MigrationError(
                        "database schema is newer than this Context Loom installation"
                    )
                expected_prefix = list(range(1, max(applied, default=0) + 1))
                if sorted(applied) != expected_prefix:
                    raise MigrationError("database migration history is not contiguous")

                for migration in MIGRATIONS:
                    existing = applied.get(migration.version)
                    if existing is not None:
                        if (
                            existing["name"] != migration.name
                            or existing["checksum"] != migration.checksum
                        ):
                            raise MigrationError(
                                f"migration {migration.version} differs from applied history"
                            )
                        continue
                    # Values below are immutable bundled migration metadata, never user input.
                    record = (
                        "INSERT INTO schema_migrations(version, name, checksum, applied_at) "  # nosec B608 # noqa: S608
                        f"VALUES ({migration.version}, {self._sql_literal(migration.name)}, "
                        f"{self._sql_literal(migration.checksum)}, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));"
                    )
                    script = f"BEGIN IMMEDIATE;\n{migration.sql}\n{record}\nCOMMIT;"
                    try:
                        connection.executescript(script)
                    except sqlite3.Error as exc:
                        if connection.in_transaction:
                            connection.rollback()
                        raise MigrationError(
                            f"failed to apply migration {migration.version}: {migration.name}"
                        ) from exc
            finally:
                connection.close()
                self._harden_database_files()

    def _harden_database_files(self) -> None:
        related_paths = (
            self.path,
            self.path.with_name(f"{self.path.name}-wal"),
            self.path.with_name(f"{self.path.name}-shm"),
        )
        for path in related_paths:
            if path.exists():
                os.chmod(path, 0o600)

    @contextmanager
    def connection(self, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection; callers own no global connection state."""

        connection = self._connect()
        if readonly:
            connection.execute("PRAGMA query_only = ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        """Yield an explicit transaction and commit or roll it back atomically."""

        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
                self._harden_database_files()

    def scalar(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        """Return the first column from one read-only query row."""

        with self.connection(readonly=True) as connection:
            row = connection.execute(sql, parameters).fetchone()
        return None if row is None else row[0]

    def rows(self, sql: str, parameters: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """Return all rows from a parameterized read-only query."""

        with self.connection(readonly=True) as connection:
            return list(connection.execute(sql, parameters).fetchall())

    def checkpoint(self, *, truncate: bool = False) -> tuple[int, int, int]:
        """Checkpoint WAL pages and return SQLite's status tuple."""

        mode = "TRUNCATE" if truncate else "PASSIVE"
        with self.connection() as connection:
            row = connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        if row is None:
            return (0, 0, 0)
        return (int(row[0]), int(row[1]), int(row[2]))
