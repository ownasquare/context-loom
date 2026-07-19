"""Shared immutable collector records."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VirtualResource:
    """Sanitized derived metadata with no executable behavior."""

    relative_path: str
    content: str
    kind: str
    origin: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()
