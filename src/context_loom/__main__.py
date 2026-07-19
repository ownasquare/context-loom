"""Allow ``python -m context_loom`` to invoke the CLI."""

from __future__ import annotations

from context_loom.cli import app

if __name__ == "__main__":  # pragma: no cover
    app()
