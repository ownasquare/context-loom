from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from context_loom.container import create_runtime
from context_loom.extensions import (
    AdapterCapability,
    AdapterRegistry,
    PromptEnvelope,
    RenderedPrompt,
    Settings,
    create_application,
)


class ContainerAdapter:
    capability = AdapterCapability(
        id="container_custom",
        display_name="Container custom",
        injection="manual",
        usage_visibility="manual",
        formats=["text"],
        install_supported=False,
    )

    def render(self, source: PromptEnvelope) -> RenderedPrompt:
        return RenderedPrompt(
            adapter=self.capability.id,
            media_type="text/plain",
            payload=source.message_exact,
            exact_message=source.message_exact,
        )


def test_container_builds_shared_runtime_and_application(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "state")
    runtime = create_runtime(settings)
    assert runtime.settings.home == settings.home

    client = TestClient(create_application(settings))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["database"] == "ready"


def test_application_factory_accepts_an_adapter_registry(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "state")
    adapters = AdapterRegistry(extra_adapters=[ContainerAdapter()])

    client = TestClient(create_application(settings, adapter_registry=adapters))

    assert "container_custom" in {item["id"] for item in client.get("/api/v1/adapters").json()}
