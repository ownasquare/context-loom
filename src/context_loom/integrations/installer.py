"""Preview-first harness integration snippets with atomic explicit writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class InstallationPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    harness: str
    format: str
    content: str
    suggested_target: str
    command_argv: list[str]
    notes: list[str] = Field(default_factory=list)


JSON_MCP_HARNESSES = {"claude", "cursor", "copilot", "gemini"}
SUPPORTED_HARNESSES = JSON_MCP_HARNESSES | {"codex", "generic"}


def build_installation_preview(
    harness: str,
    *,
    command: str = "context-loom",
) -> InstallationPreview:
    """Return a copyable snippet without mutating a harness configuration."""

    normalized = harness.strip().lower()
    if normalized not in SUPPORTED_HARNESSES:
        raise ValueError(f"unsupported harness: {harness}")
    command = command.strip()
    if not command:
        raise ValueError("command must not be empty")
    argv = [command, "mcp", "serve"]
    if normalized == "codex":
        content = (
            "[mcp_servers.context_loom]\n"
            f"command = {json.dumps(command)}\n"
            'args = ["mcp", "serve"]\n'
        )
        return InstallationPreview(
            harness=normalized,
            format="toml",
            content=content,
            suggested_target="Codex MCP configuration",
            command_argv=argv,
            notes=[
                "Review against the installed Codex configuration schema before merging.",
                "Context Loom uses stdio and performs no outbound calls by default.",
            ],
        )
    payload = {
        "mcpServers": {
            "context-loom": {
                "command": command,
                "args": ["mcp", "serve"],
            }
        }
    }
    return InstallationPreview(
        harness=normalized,
        format="json",
        content=json.dumps(payload, indent=2, sort_keys=True) + "\n",
        suggested_target=(
            "Harness MCP configuration"
            if normalized != "generic"
            else "Any MCP client configuration"
        ),
        command_argv=argv,
        notes=[
            "Merge this snippet with existing MCP servers; do not replace unrelated settings.",
            "Review the target harness's current MCP schema before applying.",
        ],
    )


def write_preview(preview: InstallationPreview, target: Path, *, overwrite: bool = False) -> Path:
    """Write one standalone snippet atomically after an explicit caller decision."""

    target = target.expanduser().resolve(strict=False)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(preview.content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target
