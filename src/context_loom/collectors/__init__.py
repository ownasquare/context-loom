"""Metadata-only workspace collectors; collectors never execute project code or tools."""

from context_loom.collectors.files import FileCollector
from context_loom.collectors.git import collect_git_metadata
from context_loom.collectors.instructions import InstructionCollector
from context_loom.collectors.tools import collect_tool_catalogs

__all__ = [
    "FileCollector",
    "InstructionCollector",
    "collect_git_metadata",
    "collect_tool_catalogs",
]
