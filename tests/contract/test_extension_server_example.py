from pathlib import Path

from examples.extensions.custom_server import create_custom_app
from fastapi.testclient import TestClient

from context_loom.extensions import Settings


def test_custom_server_factory_exposes_the_example_adapter(tmp_path: Path) -> None:
    client = TestClient(create_custom_app(Settings(home=tmp_path / "state")))

    response = client.get("/api/v1/adapters")

    assert response.status_code == 200
    assert "checklist" in {item["id"] for item in response.json()}
