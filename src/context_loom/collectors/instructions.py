"""Instruction-resource selection from already sanitized files."""

from __future__ import annotations

from context_loom.indexing.classifier import classify_resource
from context_loom.indexing.scanner import ScannedFile


class InstructionCollector:
    """Select instruction files as untrusted source data, never executable policy."""

    def collect(self, files: tuple[ScannedFile, ...]) -> tuple[ScannedFile, ...]:
        return tuple(
            file for file in files if classify_resource(file.relative_path) == "instruction"
        )
