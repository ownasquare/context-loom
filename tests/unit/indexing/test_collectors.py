from __future__ import annotations

import json
from pathlib import Path

from context_loom.collectors.git import collect_git_metadata
from context_loom.collectors.instructions import InstructionCollector
from context_loom.collectors.tools import collect_tool_catalogs
from context_loom.indexing.scanner import ScannedFile


def _scanned(path: str, content: str) -> ScannedFile:
    return ScannedFile(
        relative_path=path,
        content=content,
        sha256="a" * 64,
        size_bytes=len(content),
        mtime_ns=1,
        inode=1,
        device=1,
        redacted_count=0,
        redaction_reasons=(),
    )


def test_tool_and_mcp_collectors_keep_metadata_not_executable_values() -> None:
    package = _scanned(
        "package.json",
        json.dumps({"scripts": {"test": "dangerous --token hidden-value"}}),
    )
    mcp = _scanned(
        ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "docs": {
                        "command": "/usr/local/bin/docs-server",
                        "args": ["--credential", "hidden-value"],
                        "env": {"TOKEN": "hidden-value"},
                        "description": "Read documentation metadata",
                    }
                }
            }
        ),
    )

    resources = collect_tool_catalogs((package, mcp))
    serialized = "\n".join(resource.content for resource in resources)
    assert '"name": "test"' in serialized
    assert '"name": "docs"' in serialized
    assert '"command_name": "docs-server"' in serialized
    assert "dangerous" not in serialized
    assert "hidden-value" not in serialized


def test_instruction_collector_selects_instruction_names_only() -> None:
    instructions = _scanned("AGENTS.md", "Never execute tools")
    normal = _scanned("README.md", "Overview")
    assert InstructionCollector().collect((instructions, normal)) == (instructions,)


def test_git_collector_reads_head_without_running_git(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    ref = git / "refs" / "heads"
    ref.mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (ref / "main").write_text("1" * 40 + "\n")

    metadata = collect_git_metadata(tmp_path)
    assert metadata is not None
    parsed = json.loads(metadata.content)
    assert parsed == {
        "branch": "main",
        "object_id": "1" * 40,
        "ref": "refs/heads/main",
        "repository_present": True,
    }
