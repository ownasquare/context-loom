from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from context_loom.api.contracts import ResourceVersionContent
from context_loom.domain.models import (
    CompactionMode,
    CountingMethod,
    FidelityReport,
    FidelityStatus,
    HydrateRequest,
    IntentProfile,
    ProjectSnapshot,
    PromptEnvelope,
    ThreadTokenSummary,
    TokenEstimate,
    TokenPlan,
    UsageObservation,
    WorkspaceRecord,
    WorkspaceStatus,
)
from context_loom.integrations.mcp_server import create_mcp_server


class FakeBackend:
    def __init__(self) -> None:
        self.requests: list[HydrateRequest] = []
        self.usage: list[UsageObservation] = []

    async def hydrate(self, request: HydrateRequest) -> PromptEnvelope:
        self.requests.append(request)
        return build_envelope(request.message)

    async def get_hydration(self, hydration_id: str) -> PromptEnvelope:
        assert hydration_id == "hydration-1"
        return build_envelope("exact")

    async def explain_hydration(self, hydration_id: str) -> dict[str, Any]:
        return {"hydration_id": hydration_id, "selected": [], "omitted": []}

    async def record_usage(self, observation: UsageObservation) -> ThreadTokenSummary:
        self.usage.append(observation)
        return build_summary(observation.thread_id, actual_input=observation.actual_input_tokens)

    async def thread_stats(self, thread_id: str) -> ThreadTokenSummary:
        return build_summary(thread_id)

    async def workspace_status(self, workspace_id: str) -> WorkspaceStatus:
        now = datetime.now(UTC)
        return WorkspaceStatus(
            workspace=WorkspaceRecord(
                id=workspace_id,
                name="Demo",
                root_path="demo",
                created_at=now,
                updated_at=now,
            ),
            active_generation_id="generation-1",
            indexed_resources=1,
            indexed_chunks=2,
            stale_resources=0,
            excluded_resources=0,
        )

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


def build_envelope(message: str) -> PromptEnvelope:
    return PromptEnvelope(
        hydration_id="hydration-1",
        workspace_id="workspace-1",
        thread_id="thread-1",
        adapter="generic_json",
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
            replay_hash="d" * 64,
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


def build_summary(thread_id: str, actual_input: int | None = None) -> ThreadTokenSummary:
    return ThreadTokenSummary(
        thread_id=thread_id,
        turns=1,
        estimated_baseline_input_tokens=100,
        estimated_hydrated_input_tokens=50,
        projected_input_tokens_saved=50,
        actual_input_tokens=actual_input,
        actual_usage_completeness=1 if actual_input is not None else 0,
    )


@pytest.mark.asyncio
async def test_mcp_exposes_expected_tool_catalog() -> None:
    server = create_mcp_server(FakeBackend())
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "hydrate_message",
        "get_context",
        "explain_selection",
        "record_usage",
        "thread_stats",
        "workspace_status",
        "resolve_resource_version",
    }


@pytest.mark.asyncio
async def test_resolve_resource_version_tool_returns_sanitized_content() -> None:
    server = create_mcp_server(FakeBackend())
    _content, structured = await server.call_tool(
        "resolve_resource_version",
        {"resource_id": "resource-1", "version_id": "version-1"},
    )
    assert structured is not None
    assert structured["content"] == "# Demo\n"


@pytest.mark.asyncio
async def test_hydrate_tool_preserves_exact_message() -> None:
    backend = FakeBackend()
    server = create_mcp_server(backend)
    message = "  exact MCP request\n"
    _content, structured = await server.call_tool(
        "hydrate_message",
        {
            "workspace_id": "workspace-1",
            "message": message,
            "thread_label": "Retry policy review",
            "adapter": "generic_json",
        },
    )
    assert backend.requests[0].message.encode() == message.encode()
    assert backend.requests[0].thread_label == "Retry policy review"
    assert structured is not None
    assert structured["message_exact"].encode() == message.encode()


@pytest.mark.asyncio
async def test_record_usage_tool_keeps_missing_output_unknown() -> None:
    backend = FakeBackend()
    server = create_mcp_server(backend)
    _content, structured = await server.call_tool(
        "record_usage",
        {
            "idempotency_key": "turn-1",
            "thread_id": "thread-1",
            "provider": "test",
            "model": "test-model",
            "actual_input_tokens": 42,
        },
    )
    assert backend.usage[0].actual_output_tokens is None
    assert structured is not None
    assert structured["actual_input_tokens"] == 42
