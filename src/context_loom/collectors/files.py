"""Plain-file collector backed by the containment-safe scanner."""

from __future__ import annotations

from pathlib import Path

from context_loom.indexing.scanner import ScanBatch, WorkspaceScanner


class FileCollector:
    """Collect eligible text without hooks, imports, or subprocesses."""

    def __init__(
        self,
        root: Path | str,
        *,
        max_file_bytes: int = 2_000_000,
        max_files: int = 50_000,
    ) -> None:
        self.scanner = WorkspaceScanner(
            root,
            max_file_bytes=max_file_bytes,
            max_files=max_files,
        )

    def collect(self) -> ScanBatch:
        return self.scanner.scan()
