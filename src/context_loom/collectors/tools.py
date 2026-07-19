"""Static tool and MCP catalog metadata extraction."""

from __future__ import annotations

import json
import tomllib
from pathlib import PurePath, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from context_loom.collectors.base import VirtualResource
from context_loom.indexing.scanner import ScannedFile


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse(file: ScannedFile) -> dict[str, Any]:
    suffix = PurePosixPath(file.relative_path).suffix.casefold()
    try:
        if suffix == ".json":
            parsed = json.loads(file.content)
        elif suffix == ".toml":
            parsed = tomllib.loads(file.content)
        else:
            return {}
    except (json.JSONDecodeError, tomllib.TOMLDecodeError):
        return {}
    return _mapping(parsed)


def _safe_origin(raw_url: object) -> str | None:
    if not isinstance(raw_url, str):
        return None
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.hostname:
        return None
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def collect_tool_catalogs(files: tuple[ScannedFile, ...]) -> tuple[VirtualResource, ...]:
    """Extract names/descriptions/transports only; never retain env values or run commands."""

    tools: list[dict[str, str]] = []
    mcp_servers: list[dict[str, str]] = []
    for file in files:
        name = PurePosixPath(file.relative_path).name.casefold()
        parsed = _parse(file)
        if name == "pyproject.toml":
            scripts = _mapping(_mapping(parsed.get("project")).get("scripts"))
            tools.extend(
                {"name": str(script_name), "source": file.relative_path, "type": "python_entry"}
                for script_name in sorted(scripts)
            )
        elif name == "package.json":
            scripts = _mapping(parsed.get("scripts"))
            tools.extend(
                {"name": str(script_name), "source": file.relative_path, "type": "package_script"}
                for script_name in sorted(scripts)
            )

        if "mcp" not in file.relative_path.casefold() or not parsed:
            continue
        candidates = _mapping(parsed.get("mcpServers")) or _mapping(parsed.get("servers"))
        for server_name, raw_config in sorted(candidates.items(), key=lambda item: str(item[0])):
            config = _mapping(raw_config)
            record = {"name": str(server_name), "source": file.relative_path}
            origin = _safe_origin(config.get("url"))
            if origin is not None:
                record["transport"] = "remote"
                record["origin"] = origin
            elif isinstance(config.get("command"), str):
                record["transport"] = "stdio"
                record["command_name"] = PurePath(str(config["command"])).name
            else:
                record["transport"] = str(config.get("type", "unknown"))
            description = config.get("description")
            if isinstance(description, str):
                record["description"] = description[:500]
            mcp_servers.append(record)

    resources: list[VirtualResource] = []
    if tools:
        resources.append(
            VirtualResource(
                relative_path=".context-loom/metadata/tools.json",
                content=json.dumps({"tools": tools}, sort_keys=True, indent=2) + "\n",
                kind="tool_catalog",
                origin="tool_metadata",
            )
        )
    if mcp_servers:
        resources.append(
            VirtualResource(
                relative_path=".context-loom/metadata/mcp-catalog.json",
                content=json.dumps({"servers": mcp_servers}, sort_keys=True, indent=2) + "\n",
                kind="mcp_catalog",
                origin="mcp_metadata",
            )
        )
    return tuple(resources)
