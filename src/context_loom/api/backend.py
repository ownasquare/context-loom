"""Application protocol consumed by both HTTP and MCP boundaries."""

from __future__ import annotations

from typing import Any, Protocol

from context_loom.api.contracts import (
    ExportArtifact,
    ExportRequest,
    ReadinessStatus,
    ResourceSummary,
    ResourceVersionContent,
    ThreadSummary,
)
from context_loom.domain.models import (
    HealthStatus,
    HydrateRequest,
    PromptEnvelope,
    SyncReport,
    ThreadTokenSummary,
    UsageObservation,
    WorkspaceCreate,
    WorkspaceRecord,
    WorkspaceStatus,
)


class AppBackend(Protocol):
    async def health(self) -> HealthStatus: ...

    async def readiness(self) -> ReadinessStatus: ...

    async def create_workspace(self, request: WorkspaceCreate) -> WorkspaceRecord: ...

    async def list_workspaces(self) -> list[WorkspaceRecord]: ...

    async def workspace_status(self, workspace_id: str) -> WorkspaceStatus: ...

    async def sync_workspace(self, workspace_id: str) -> SyncReport: ...

    async def list_resources(self, workspace_id: str) -> list[ResourceSummary]: ...

    async def resolve_resource_version(
        self, resource_id: str, version_id: str
    ) -> ResourceVersionContent: ...

    async def hydrate(self, request: HydrateRequest) -> PromptEnvelope: ...

    async def get_hydration(self, hydration_id: str) -> PromptEnvelope: ...

    async def explain_hydration(self, hydration_id: str) -> dict[str, Any]: ...

    async def record_usage(self, observation: UsageObservation) -> ThreadTokenSummary: ...

    async def thread_stats(self, thread_id: str) -> ThreadTokenSummary: ...

    async def list_threads(self, workspace_id: str | None = None) -> list[ThreadSummary]: ...

    async def create_export(self, request: ExportRequest) -> ExportArtifact: ...
