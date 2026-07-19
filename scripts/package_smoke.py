#!/usr/bin/env python3
"""Install wheel and sdist artifacts in isolation and exercise their public surfaces."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

HTTP_SMOKE = """\
import asyncio
import re

import httpx

from context_loom.container import create_application


async def main() -> None:
    transport = httpx.ASGITransport(app=create_application())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["retain_message_content"] is False
        assert (await client.get("/readyz")).json()["status"] == "ready"
        root = await client.get("/")
        assert root.status_code == 200
        assert root.headers["content-type"].startswith("text/html")
        assert "Context Loom" in root.text

        for route in ("/hydrate", "/resources", "/threads", "/integrations", "/settings"):
            response = await client.get(route)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")
            assert response.text == root.text

        references = set(re.findall(r'(?:src|href)="(/[^"]+)"', root.text))
        assert any(
            reference.startswith("/assets/") and reference.endswith(".js")
            for reference in references
        )
        assert any(
            reference.startswith("/assets/") and reference.endswith(".css")
            for reference in references
        )
        assert "/favicon.svg" in references
        for reference in references:
            response = await client.get(reference)
            assert response.status_code == 200
            assert response.content


asyncio.run(main())
"""


def run(
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
    working_directory: Path | None = None,
) -> None:
    subprocess.run(arguments, check=True, env=environment, cwd=working_directory)


def environment_executables(
    environment_path: Path,
    *,
    os_name: str = os.name,
) -> tuple[Path, Path]:
    scripts = environment_path / ("Scripts" if os_name == "nt" else "bin")
    python = scripts / ("python.exe" if os_name == "nt" else "python")
    command = scripts / ("context-loom.exe" if os_name == "nt" else "context-loom")
    return python, command


def smoke_artifact(artifact: Path, *, artifact_kind: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f"context-loom-{artifact_kind}-") as temporary:
        base = Path(temporary)
        environment_path = base / "venv"
        state = base / "state"
        run(["uv", "venv", "--python", "3.12", str(environment_path)], working_directory=base)
        python, command = environment_executables(environment_path)
        run(
            ["uv", "pip", "install", "--python", str(python), str(artifact)],
            working_directory=base,
        )
        environment = dict(os.environ)
        environment["CONTEXT_LOOM_HOME"] = str(state)
        environment["CONTEXT_LOOM_ALLOW_OUTBOUND"] = "false"
        environment["CONTEXT_LOOM_RETAIN_MESSAGE_CONTENT"] = "false"
        environment.pop("CONTEXT_LOOM_PROXY_UPSTREAM_URL", None)
        run([str(command), "version"], environment=environment, working_directory=base)
        run([str(command), "init"], environment=environment, working_directory=base)
        run([str(command), "doctor"], environment=environment, working_directory=base)
        run([str(command), "demo"], environment=environment, working_directory=base)
        run(
            [str(python), "-c", HTTP_SMOKE],
            environment=environment,
            working_directory=base,
        )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    wheels = sorted((root / "dist").glob("context_loom-*.whl"))
    sdists = sorted((root / "dist").glob("context_loom-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("expected exactly one Context Loom wheel and one sdist under dist/")
    smoke_artifact(wheels[0].resolve(), artifact_kind="wheel")
    smoke_artifact(sdists[0].resolve(), artifact_kind="sdist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
