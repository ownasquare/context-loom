#!/usr/bin/env python3
"""Remove only explicit reproducible build outputs from this repository."""

from __future__ import annotations

import shutil
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    targets = (
        root / ".coverage",
        root / ".pytest_cache",
        root / ".ruff_cache",
        root / ".mypy_cache",
        root / "htmlcov",
        root / "frontend" / "coverage",
        root / "frontend" / "playwright-report",
        root / "frontend" / "test-results",
    )
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
