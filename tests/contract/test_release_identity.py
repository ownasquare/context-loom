from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from context_loom import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_release_version_is_consistent_across_public_surfaces() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    frontend_lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_project = next(item for item in lock["package"] if item["name"] == "context-loom")
    demo_source = (ROOT / "frontend/src/api/demoData.ts").read_text(encoding="utf-8")
    demo_version = re.search(r'version: "([^"]+)-demo"', demo_source)
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert project["project"]["version"] == __version__
    assert frontend["version"] == __version__
    assert frontend_lock["version"] == __version__
    assert frontend_lock["packages"][""]["version"] == __version__
    assert locked_project["version"] == __version__
    assert demo_version is not None and demo_version.group(1) == __version__
    assert f"## [{__version__}]" in changelog
