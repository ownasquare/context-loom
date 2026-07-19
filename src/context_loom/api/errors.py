"""Stable API failures that never expose prompt or source content."""

from __future__ import annotations

from typing import Any


class ContextLoomError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(ContextLoomError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            "not_found",
            f"{resource} was not found",
            status_code=404,
            details={"resource": resource, "identifier": identifier},
        )


class ConflictError(ContextLoomError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, status_code=409, details=details)
