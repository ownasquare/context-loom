"""Run a custom Context Loom renderer against a temporary local project.

Usage: uv run python examples/extensions/custom_adapter.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from context_loom.extensions import (
    AdapterCapability,
    AdapterRegistry,
    PromptEnvelope,
    RenderedPrompt,
    Settings,
    create_application,
)


class ChecklistAdapter:
    """Render selected source locations as a compact plain-text checklist."""

    capability = AdapterCapability(
        id="checklist",
        display_name="Checklist",
        injection="manual",
        usage_visibility="manual",
        formats=["text"],
        install_supported=False,
        description="A credential-free custom plain-text renderer.",
    )

    def render(self, envelope: PromptEnvelope) -> RenderedPrompt:
        sources = [
            f"- {item.citation.relative_path}:{item.citation.start_line}-{item.citation.end_line}"
            for item in envelope.context_items
        ]
        source_block = "\n".join(sources) if sources else "- No project excerpts selected"
        payload = f"Relevant project sources:\n{source_block}\n\nRequest:\n{envelope.message_exact}"
        return RenderedPrompt(
            adapter=self.capability.id,
            media_type="text/plain",
            payload=payload,
            exact_message=envelope.message_exact,
            instructions=["Copy the complete text into the destination chat."],
        )


async def run_example() -> None:
    registry = AdapterRegistry(extra_adapters=[ChecklistAdapter()])
    with TemporaryDirectory(prefix="context-loom-extension-") as temporary:
        root = Path(temporary)
        project = root / "project"
        project.mkdir()
        (project / "README.md").write_text(
            "# Retry service\n\nRetries stop after three attempts.\n",
            encoding="utf-8",
        )

        application = create_application(
            Settings(home=root / "state"),
            adapter_registry=registry,
        )
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://context-loom.local"
        ) as client:
            workspace = await client.post(
                "/api/v1/workspaces",
                json={"name": "Extension example", "root_path": str(project)},
            )
            workspace.raise_for_status()
            workspace_id = workspace.json()["id"]

            sync = await client.post(f"/api/v1/workspaces/{workspace_id}/sync")
            sync.raise_for_status()

            hydration = await client.post(
                "/api/v1/hydrations",
                json={
                    "workspace_id": workspace_id,
                    "message": "Where is the retry limit documented?",
                    "adapter": "checklist",
                },
            )
            hydration.raise_for_status()
            print(hydration.json()["rendered"]["payload"])


def main() -> None:
    asyncio.run(run_example())


if __name__ == "__main__":
    main()
