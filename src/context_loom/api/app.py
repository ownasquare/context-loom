"""FastAPI application factory for the local workbench and versioned API."""

from __future__ import annotations

import logging
import re
import uuid
from importlib.resources import files
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from context_loom import __version__
from context_loom.api.backend import AppBackend
from context_loom.api.contracts import (
    ApiErrorDetail,
    ApiErrorResponse,
    ExportArtifact,
    ExportRequest,
    HydrationResponse,
    ProxyRequest,
    ReadinessStatus,
    ResourcePage,
    ResourceVersionContent,
    ThreadPage,
)
from context_loom.api.errors import ConflictError, ContextLoomError
from context_loom.domain.models import (
    AdapterCapability,
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
from context_loom.integrations.base import AdapterNotFoundError
from context_loom.integrations.proxy import (
    OpenAICompatibleProxy,
    ProxyDisabledError,
    ProxyResult,
    UnsupportedProxyRequestError,
)
from context_loom.integrations.renderers import AdapterRegistry

LOGGER = logging.getLogger("context_loom.api")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
WORKBENCH_ROUTES = frozenset({"hydrate", "resources", "threads", "integrations", "settings"})


def create_app(
    backend: AppBackend,
    *,
    proxy: OpenAICompatibleProxy | None = None,
    static_dir: Path | None = None,
    adapter_registry: AdapterRegistry | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Context Loom",
        version=__version__,
        description="Local source-preserving context compilation and token accounting",
        docs_url="/api/docs",
        redoc_url=None,
    )
    adapters = adapter_registry if adapter_registry is not None else AdapterRegistry()

    @app.middleware("http")
    async def request_identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        candidate = request.headers.get("x-request-id", "")
        request_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ContextLoomError)
    async def context_loom_error(request: Request, error: ContextLoomError) -> JSONResponse:
        payload = ApiErrorResponse(
            error=ApiErrorDetail(
                code=error.code,
                message=error.public_message,
                request_id=_request_id(request),
                details=error.details,
            )
        )
        return JSONResponse(status_code=error.status_code, content=payload.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        details = {
            "fields": [
                {"location": list(item["loc"]), "type": item["type"]} for item in error.errors()
            ]
        }
        payload = ApiErrorResponse(
            error=ApiErrorDetail(
                code="invalid_request",
                message="Request validation failed",
                request_id=_request_id(request),
                details=details,
            )
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled request failure request_id=%s", _request_id(request))
        payload = ApiErrorResponse(
            error=ApiErrorDetail(
                code="internal_error",
                message="The request could not be completed",
                request_id=_request_id(request),
            )
        )
        return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))

    @app.get("/healthz", response_model=HealthStatus)
    async def health() -> HealthStatus:
        return await backend.health()

    @app.get("/readyz", response_model=ReadinessStatus)
    async def readiness() -> ReadinessStatus:
        return await backend.readiness()

    @app.get("/api/v1/adapters", response_model=list[AdapterCapability])
    async def list_adapters() -> list[AdapterCapability]:
        return adapters.capabilities()

    @app.post("/api/v1/workspaces", response_model=WorkspaceRecord, status_code=201)
    async def create_workspace(request: WorkspaceCreate) -> WorkspaceRecord:
        return await backend.create_workspace(request)

    @app.get("/api/v1/workspaces", response_model=list[WorkspaceRecord])
    async def list_workspaces() -> list[WorkspaceRecord]:
        return await backend.list_workspaces()

    @app.get("/api/v1/workspaces/{workspace_id}/status", response_model=WorkspaceStatus)
    async def workspace_status(workspace_id: str) -> WorkspaceStatus:
        return await backend.workspace_status(workspace_id)

    @app.post("/api/v1/workspaces/{workspace_id}/sync", response_model=SyncReport)
    async def sync_workspace(workspace_id: str) -> SyncReport:
        return await backend.sync_workspace(workspace_id)

    @app.get("/api/v1/workspaces/{workspace_id}/resources", response_model=ResourcePage)
    async def list_resources(workspace_id: str) -> ResourcePage:
        items = await backend.list_resources(workspace_id)
        return ResourcePage(items=items, total=len(items))

    @app.get("/api/v1/resources", response_model=ResourcePage)
    async def list_resources_alias(workspace_id: str) -> ResourcePage:
        items = await backend.list_resources(workspace_id)
        return ResourcePage(items=items, total=len(items))

    @app.get(
        "/api/v1/resources/{resource_id}/versions/{version_id}",
        response_model=ResourceVersionContent,
    )
    async def resolve_resource_version(
        resource_id: str,
        version_id: str,
    ) -> ResourceVersionContent:
        return await backend.resolve_resource_version(resource_id, version_id)

    @app.post("/api/v1/hydrations", response_model=HydrationResponse, status_code=201)
    async def hydrate(request: HydrateRequest) -> HydrationResponse:
        try:
            adapters.get(request.adapter)
        except AdapterNotFoundError as error:
            raise ContextLoomError(
                "adapter_not_found",
                "The requested harness adapter is not supported",
                status_code=422,
                details={"adapter": request.adapter},
            ) from error
        envelope = await backend.hydrate(request)
        rendered = adapters.render(request.adapter, envelope)
        return HydrationResponse(envelope=envelope, rendered=rendered)

    @app.get("/api/v1/hydrations/{hydration_id}", response_model=PromptEnvelope)
    async def get_hydration(hydration_id: str) -> PromptEnvelope:
        return await backend.get_hydration(hydration_id)

    @app.get("/api/v1/hydrations/{hydration_id}/explanation")
    async def explain_hydration(hydration_id: str) -> dict[str, object]:
        return await backend.explain_hydration(hydration_id)

    @app.post("/api/v1/threads/{thread_id}/usage", response_model=ThreadTokenSummary)
    async def record_usage(thread_id: str, observation: UsageObservation) -> ThreadTokenSummary:
        if observation.thread_id != thread_id:
            raise ConflictError(
                "thread_mismatch",
                "Path thread identifier does not match the usage observation",
                details={"path_thread_id": thread_id},
            )
        return await backend.record_usage(observation)

    @app.get("/api/v1/threads/{thread_id}/stats", response_model=ThreadTokenSummary)
    async def thread_stats(thread_id: str) -> ThreadTokenSummary:
        return await backend.thread_stats(thread_id)

    @app.get("/api/v1/threads", response_model=ThreadPage)
    async def list_threads(workspace_id: str | None = None) -> ThreadPage:
        items = await backend.list_threads(workspace_id)
        return ThreadPage(items=items, total=len(items))

    @app.post("/api/v1/exports", response_model=ExportArtifact, status_code=201)
    async def create_export(request: ExportRequest) -> ExportArtifact:
        return await backend.create_export(request)

    @app.post("/api/v1/proxy", response_model=ProxyResult)
    async def forward_proxy(
        request: ProxyRequest,
        authorization: str | None = Header(default=None),
    ) -> ProxyResult:
        if proxy is None:
            raise ContextLoomError(
                "proxy_disabled", "The provider proxy is not configured", status_code=403
            )
        envelope = await backend.get_hydration(request.hydration_id)
        try:
            return await proxy.forward(
                endpoint=request.endpoint,
                original_payload=request.payload,
                envelope=envelope,
                authorization=authorization,
                idempotency_key=request.idempotency_key,
            )
        except ProxyDisabledError as error:
            raise ContextLoomError(
                "outbound_disabled",
                "Outbound provider forwarding is disabled",
                status_code=403,
            ) from error
        except UnsupportedProxyRequestError as error:
            raise ContextLoomError(
                "proxy_request_unsupported",
                str(error),
                status_code=422,
            ) from error
        except httpx.HTTPError as error:
            raise ContextLoomError(
                "provider_unavailable",
                "The configured provider could not complete the request",
                status_code=502,
            ) from error

    resolved_static = static_dir or Path(str(files("context_loom").joinpath("static")))
    index_file = resolved_static / "index.html"
    favicon_file = resolved_static / "favicon.svg"
    assets_dir = resolved_static / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def workbench_root():  # type: ignore[no-untyped-def]
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(
            {
                "name": "Context Loom",
                "status": "api_ready",
                "workbench": "not_built",
                "docs": "/api/docs",
            }
        )

    @app.get("/favicon.svg", include_in_schema=False)
    async def workbench_favicon():  # type: ignore[no-untyped-def]
        if favicon_file.is_file():
            return FileResponse(favicon_file, media_type="image/svg+xml")
        return JSONResponse(
            {"error": {"code": "not_found", "message": "Route was not found"}},
            status_code=404,
        )

    @app.get("/{workbench_route}", include_in_schema=False)
    async def workbench_client_route(workbench_route: str):  # type: ignore[no-untyped-def]
        if workbench_route not in WORKBENCH_ROUTES or not index_file.is_file():
            return JSONResponse(
                {"error": {"code": "not_found", "message": "Route was not found"}},
                status_code=404,
            )
        return FileResponse(index_file)

    return app


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else uuid.uuid4().hex
