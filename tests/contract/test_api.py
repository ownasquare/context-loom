from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from context_loom.api.app import create_app
from context_loom.api.contracts import (
    ExportArtifact,
    ExportRequest,
    ReadinessStatus,
    ResourceSummary,
    ResourceVersionContent,
    ThreadSummary,
    TurnSummary,
)
from context_loom.api.errors import ConflictError, NotFoundError
from context_loom.domain.models import (
    CompactionMode,
    CountingMethod,
    FidelityReport,
    FidelityStatus,
    HealthStatus,
    HydrateRequest,
    IntentProfile,
    ProjectSnapshot,
    PromptEnvelope,
    SyncReport,
    ThreadTokenSummary,
    TokenEstimate,
    TokenPlan,
    UsageObservation,
    WorkspaceCreate,
    WorkspaceRecord,
    WorkspaceStatus,
)
from context_loom.extensions import AdapterCapability, AdapterRegistry, RenderedPrompt


class FakeBackend:
    def __init__(self) -> None:
        self.hydrate_requests: list[HydrateRequest] = []
        self.usage: list[UsageObservation] = []
        self.workspace = workspace_record()

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="ok",
            version="0.1.0",
            database="ready",
            local_model="disabled",
            outbound_allowed=False,
            retain_message_content=False,
        )

    async def readiness(self) -> ReadinessStatus:
        return ReadinessStatus(
            status="ready", database="ready", local_model="disabled", migrations_current=True
        )

    async def create_workspace(self, request: WorkspaceCreate) -> WorkspaceRecord:
        return self.workspace.model_copy(
            update={"name": request.name, "root_path": request.root_path}
        )

    async def list_workspaces(self) -> list[WorkspaceRecord]:
        return [self.workspace]

    async def workspace_status(self, workspace_id: str) -> WorkspaceStatus:
        return WorkspaceStatus(
            workspace=self.workspace,
            active_generation_id="generation-1",
            indexed_resources=1,
            indexed_chunks=1,
            stale_resources=0,
            excluded_resources=0,
        )

    async def sync_workspace(self, workspace_id: str) -> SyncReport:
        return SyncReport(
            workspace_id=workspace_id,
            generation_id="generation-2",
            added=1,
            modified=0,
            deleted=0,
            unchanged=0,
            excluded=0,
            redacted=0,
            duration_ms=1,
        )

    async def list_resources(self, workspace_id: str) -> list[ResourceSummary]:
        return [
            ResourceSummary(
                resource_id="resource-1",
                version_id="version-1",
                relative_path="README.md",
                kind="documentation",
                sha256="a" * 64,
                estimated_tokens=20,
                chunks=1,
                changed_at=datetime.now(UTC),
                change_type="added",
                status="changed",
            )
        ]

    async def resolve_resource_version(
        self, resource_id: str, version_id: str
    ) -> ResourceVersionContent:
        return ResourceVersionContent(
            resource_id=resource_id,
            version_id=version_id,
            workspace_id="workspace-1",
            relative_path="README.md",
            kind="documentation",
            sha256="a" * 64,
            content="# Demo\n",
            current=True,
            redacted_count=0,
            created_at=datetime.now(UTC),
        )

    async def hydrate(self, request: HydrateRequest) -> PromptEnvelope:
        self.hydrate_requests.append(request)
        return envelope(request.message, adapter=request.adapter)

    async def get_hydration(self, hydration_id: str) -> PromptEnvelope:
        return envelope("exact", adapter="generic_json")

    async def explain_hydration(self, hydration_id: str) -> dict[str, Any]:
        return {"hydration_id": hydration_id, "selected": [], "omitted": []}

    async def record_usage(self, observation: UsageObservation) -> ThreadTokenSummary:
        if observation.hydration_id == "missing-hydration":
            raise NotFoundError("hydration", observation.hydration_id)
        if observation.hydration_id == "wrong-thread":
            raise ConflictError(
                "hydration_thread_mismatch",
                "Hydration does not belong to the usage thread",
            )
        self.usage.append(observation)
        return thread_summary(observation.thread_id, observation.actual_input_tokens)

    async def thread_stats(self, thread_id: str) -> ThreadTokenSummary:
        return thread_summary(thread_id)

    async def list_threads(self, workspace_id: str | None = None) -> list[ThreadSummary]:
        assert workspace_id in {None, "workspace-1"}
        summary = thread_summary("thread-1")
        now = datetime.now(UTC)
        return [
            ThreadSummary(
                **summary.model_dump(),
                label="thread-1",
                updated_at=now,
                history=[
                    TurnSummary(
                        hydration_id="hydration-1",
                        created_at=now,
                        adapter="generic_markdown",
                        effective_mode=CompactionMode.STRICT_EXTRACTIVE,
                        projected_input_tokens_saved=50,
                        usage_recorded=False,
                        fidelity_status=FidelityStatus.PASSED,
                    )
                ],
            )
        ]

    async def create_export(self, request: ExportRequest) -> ExportArtifact:
        return ExportArtifact(
            id="export-1",
            format=request.format,
            path="exports/export-1." + request.format,
            sha256="a" * 64,
            rows=1,
            includes_content=request.include_content,
        )


class CustomApiAdapter:
    capability = AdapterCapability(
        id="custom_api",
        display_name="Custom API",
        injection="manual",
        usage_visibility="manual",
        formats=["text"],
        install_supported=False,
    )

    def render(self, source: PromptEnvelope) -> RenderedPrompt:
        return RenderedPrompt(
            adapter=self.capability.id,
            media_type="text/plain",
            payload=f"API CUSTOM: {source.message_exact}",
            exact_message=source.message_exact,
        )


def workspace_record() -> WorkspaceRecord:
    now = datetime.now(UTC)
    return WorkspaceRecord(
        id="workspace-1",
        name="Demo",
        root_path="demo",
        created_at=now,
        updated_at=now,
    )


def envelope(message: str, *, adapter: str) -> PromptEnvelope:
    return PromptEnvelope(
        hydration_id="hydration-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        adapter=adapter,
        message_exact=message,
        intent=IntentProfile(),
        snapshot=ProjectSnapshot(
            workspace_id="workspace-1",
            generation_id="generation-1",
            root_name="demo",
            indexed_resources=1,
            changed_resources=0,
            generated_at=datetime.now(UTC),
        ),
        fidelity=FidelityReport(
            status=FidelityStatus.PASSED,
            requested_mode=CompactionMode.HYBRID_SAFE,
            effective_mode=CompactionMode.STRICT_EXTRACTIVE,
            exact_message_preserved=True,
            citations_valid=True,
            freshness_valid=True,
            protected_atom_coverage=1,
            explicit_reference_coverage=1,
            replay_hash="b" * 64,
        ),
        token_plan=TokenPlan(
            baseline=TokenEstimate(
                tokens=100,
                method=CountingMethod.EXACT_LOCAL,
                tokenizer="test",
                confidence=1,
            ),
            hydrated=TokenEstimate(
                tokens=50,
                method=CountingMethod.EXACT_LOCAL,
                tokenizer="test",
                confidence=1,
            ),
            reserved_output_tokens=10,
        ),
    )


def thread_summary(thread_id: str, actual_input: int | None = None) -> ThreadTokenSummary:
    return ThreadTokenSummary(
        thread_id=thread_id,
        turns=1,
        estimated_baseline_input_tokens=100,
        estimated_hydrated_input_tokens=50,
        projected_input_tokens_saved=50,
        actual_input_tokens=actual_input,
        actual_usage_completeness=1 if actual_input is not None else 0,
    )


def client(tmp_path: Path) -> tuple[TestClient, FakeBackend]:
    backend = FakeBackend()
    return TestClient(create_app(backend, static_dir=tmp_path)), backend


def test_health_readiness_and_security_headers(tmp_path: Path) -> None:
    browser, _backend = client(tmp_path)
    response = browser.get("/healthz")
    assert response.status_code == 200
    assert response.json()["database"] == "ready"
    assert response.json()["retain_message_content"] is False
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert browser.get("/readyz").json()["status"] == "ready"


def test_hydration_preserves_exact_message_in_envelope_and_renderer(tmp_path: Path) -> None:
    browser, backend = client(tmp_path)
    message = "  exact HTTP request\n"
    response = browser.post(
        "/api/v1/hydrations",
        json={
            "workspace_id": "workspace-1",
            "message": message,
            "adapter": "openai_chat",
            "thread_label": "Retry policy review",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["envelope"]["message_exact"].encode() == message.encode()
    assert body["rendered"]["exact_message"].encode() == message.encode()
    assert backend.hydrate_requests[0].message.encode() == message.encode()
    assert backend.hydrate_requests[0].thread_label == "Retry policy review"


def test_injected_adapter_is_listed_and_renders_hydrations(tmp_path: Path) -> None:
    backend = FakeBackend()
    adapters = AdapterRegistry(extra_adapters=[CustomApiAdapter()])
    browser = TestClient(create_app(backend, static_dir=tmp_path, adapter_registry=adapters))

    capabilities = browser.get("/api/v1/adapters")
    assert capabilities.status_code == 200
    assert "custom_api" in {item["id"] for item in capabilities.json()}

    response = browser.post(
        "/api/v1/hydrations",
        json={"workspace_id": "workspace-1", "message": "exact custom", "adapter": "custom_api"},
    )
    assert response.status_code == 201
    assert response.json()["rendered"] == {
        "adapter": "custom_api",
        "media_type": "text/plain",
        "payload": "API CUSTOM: exact custom",
        "exact_message": "exact custom",
        "instructions": [],
    }


def test_invalid_request_uses_stable_redacted_error_shape(tmp_path: Path) -> None:
    browser, _backend = client(tmp_path)
    response = browser.post("/api/v1/hydrations", json={"message": "missing workspace"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["request_id"]
    assert "missing workspace" not in response.text


def test_unknown_adapter_is_rejected_before_hydration(tmp_path: Path) -> None:
    browser, backend = client(tmp_path)
    response = browser.post(
        "/api/v1/hydrations",
        json={"workspace_id": "workspace-1", "message": "exact", "adapter": "unknown"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "adapter_not_found"
    assert backend.hydrate_requests == []


def test_usage_path_mismatch_is_rejected_without_recording(tmp_path: Path) -> None:
    browser, backend = client(tmp_path)
    response = browser.post(
        "/api/v1/threads/path-thread/usage",
        json={
            "idempotency_key": "turn-1",
            "thread_id": "body-thread",
            "provider": "test",
            "model": "test",
            "actual_input_tokens": 42,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "thread_mismatch"
    assert backend.usage == []


def test_usage_requires_identity_and_at_least_one_token_field(tmp_path: Path) -> None:
    browser, backend = client(tmp_path)
    response = browser.post(
        "/api/v1/threads/thread-1/usage",
        json={
            "idempotency_key": " ",
            "thread_id": "thread-1",
            "provider": "test",
            "model": "test",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert backend.usage == []


def test_usage_ownership_errors_keep_stable_public_status_and_code(tmp_path: Path) -> None:
    browser, backend = client(tmp_path)
    payload = {
        "idempotency_key": "usage-1",
        "thread_id": "thread-1",
        "provider": "test",
        "model": "test",
        "actual_input_tokens": 42,
    }
    missing = browser.post(
        "/api/v1/threads/thread-1/usage",
        json={**payload, "hydration_id": "missing-hydration"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    mismatch = browser.post(
        "/api/v1/threads/thread-1/usage",
        json={**payload, "idempotency_key": "usage-2", "hydration_id": "wrong-thread"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "hydration_thread_mismatch"
    assert backend.usage == []


def test_workspace_resource_thread_and_adapter_routes(tmp_path: Path) -> None:
    browser, _backend = client(tmp_path)
    assert browser.get("/api/v1/workspaces").json()[0]["id"] == "workspace-1"
    assert browser.get("/api/v1/workspaces/workspace-1/resources").json()["total"] == 1
    assert browser.get("/api/v1/resources?workspace_id=workspace-1").json()["total"] == 1
    thread_page = browser.get("/api/v1/threads?workspace_id=workspace-1").json()
    assert thread_page["total"] == 1
    assert thread_page["items"][0]["history"][0]["usage_recorded"] is False
    adapter_ids = {item["id"] for item in browser.get("/api/v1/adapters").json()}
    assert {"codex", "claude", "cursor", "copilot"} <= adapter_ids
    recovered = browser.get("/api/v1/resources/resource-1/versions/version-1")
    assert recovered.status_code == 200
    assert recovered.json()["content"] == "# Demo\n"


def test_root_reports_missing_workbench_without_shadowing_api(tmp_path: Path) -> None:
    browser, _backend = client(tmp_path)
    assert browser.get("/").json()["workbench"] == "not_built"
    assert browser.get("/healthz").status_code == 200


def test_packaged_workbench_routes_survive_direct_reload(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>packaged workbench</title>", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    browser, _backend = client(tmp_path)
    response = browser.get("/settings")
    assert response.status_code == 200
    assert "packaged workbench" in response.text
    assert browser.get("/favicon.svg").headers["content-type"].startswith("image/svg+xml")
    assert browser.get("/unknown-route").status_code == 404
