"""Source-preserving deterministic and optional local-model compaction."""

from context_loom.compaction.deterministic import build_extractive_digest
from context_loom.compaction.protected_atoms import (
    ProtectedAtom,
    ProtectedAtomKind,
    extract_protected_atoms,
)

__all__ = [
    "ProtectedAtom",
    "ProtectedAtomKind",
    "build_extractive_digest",
    "extract_protected_atoms",
]
