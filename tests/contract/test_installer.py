from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from context_loom.integrations.installer import build_installation_preview, write_preview


def test_codex_preview_is_toml_and_preview_only() -> None:
    preview = build_installation_preview("codex")
    assert preview.format == "toml"
    assert "[mcp_servers.context_loom]" in preview.content
    assert preview.command_argv == ["context-loom", "mcp", "serve"]


def test_preview_can_embed_a_resolved_executable_path() -> None:
    command = "/opt/context-loom/bin/context-loom"
    preview = build_installation_preview("codex", command=command)

    assert f'command = "{command}"' in preview.content
    assert preview.command_argv == [command, "mcp", "serve"]


@pytest.mark.parametrize("harness", ["claude", "cursor", "copilot", "gemini", "generic"])
def test_json_harness_preview_is_valid(harness: str) -> None:
    preview = build_installation_preview(harness)
    payload = json.loads(preview.content)
    assert payload["mcpServers"]["context-loom"]["args"] == ["mcp", "serve"]


def test_unknown_harness_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported harness"):
        build_installation_preview("mystery")


def test_explicit_write_is_atomic_private_and_non_overwriting(tmp_path: Path) -> None:
    target = tmp_path / "context-loom-mcp.json"
    preview = build_installation_preview("generic")
    assert write_preview(preview, target) == target
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_preview(preview, target)
    write_preview(preview, target, overwrite=True)
    assert json.loads(target.read_text())["mcpServers"]
