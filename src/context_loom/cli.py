"""Typer command surface for local operators and harness wrappers."""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote, urlsplit

import typer
import uvicorn
from pydantic import BaseModel

from context_loom import __version__
from context_loom.api.app import create_app
from context_loom.config import Settings, load_settings
from context_loom.domain.models import (
    CompactionMode,
    CountingMethod,
    HydrateRequest,
    UsageObservation,
    WorkspaceCreate,
)
from context_loom.integrations.installer import build_installation_preview, write_preview
from context_loom.integrations.mcp_server import run_mcp_server
from context_loom.integrations.proxy import OpenAICompatibleProxy
from context_loom.integrations.renderers import AdapterRegistry
from context_loom.runtime import ContextLoomRuntime

app = typer.Typer(
    name="context-loom",
    help="Compile compact, cited local context before an AI chat request.",
    no_args_is_help=True,
)
workspace_app = typer.Typer(help="Register and synchronize project workspaces.")
thread_app = typer.Typer(help="Inspect per-thread token history and usage evidence.")
adapter_app = typer.Typer(help="Preview harness adapters without modifying their configuration.")
mcp_app = typer.Typer(help="Expose Context Loom through the Model Context Protocol.")
resource_app = typer.Typer(help="Resolve stable omission recovery references.")
app.add_typer(workspace_app, name="workspace")
app.add_typer(thread_app, name="thread")
app.add_typer(adapter_app, name="adapter")
app.add_typer(mcp_app, name="mcp")
app.add_typer(resource_app, name="resource")


class CliState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._runtime: ContextLoomRuntime | None = None

    @property
    def runtime(self) -> ContextLoomRuntime:
        if self._runtime is None:
            self._runtime = ContextLoomRuntime(self.settings)
        return self._runtime


def _state(context: typer.Context) -> CliState:
    state = context.find_root().obj
    if not isinstance(state, CliState):
        raise RuntimeError("CLI state was not initialized")
    return state


def _emit(value: Any) -> None:
    if isinstance(value, BaseModel):
        typer.echo(value.model_dump_json(indent=2))
        return
    typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))


def _context_loom_executable() -> str:
    command = shutil.which("context-loom")
    return str(Path(command).resolve()) if command else "context-loom"


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


@app.callback()
def main(
    context: typer.Context,
    home: Annotated[
        Path | None,
        typer.Option(
            "--home",
            help="Private Context Loom state directory.",
            envvar="CONTEXT_LOOM_HOME",
        ),
    ] = None,
    allow_outbound: Annotated[
        bool | None,
        typer.Option(
            "--allow-outbound/--deny-outbound",
            help="Allow explicitly requested Ollama or provider network calls.",
        ),
    ] = None,
    retain_message_content: Annotated[
        bool | None,
        typer.Option(
            "--retain-messages/--no-retain-messages",
            help="Persist exact messages and envelopes in the private local database.",
        ),
    ] = None,
) -> None:
    """Set process-wide privacy and storage policy before running one command."""

    overrides: dict[str, Any] = {}
    if home is not None:
        overrides["home"] = home
    if allow_outbound is not None:
        overrides["allow_outbound"] = allow_outbound
    if retain_message_content is not None:
        overrides["retain_message_content"] = retain_message_content
    context.obj = CliState(load_settings(**overrides))


@app.command("version")
def version() -> None:
    """Print the installed Context Loom version."""

    typer.echo(__version__)


@app.command("init")
def initialize(context: typer.Context) -> None:
    """Create the private state store and verify its schema."""

    state = _state(context)
    readiness = _run(state.runtime.readiness())
    _emit(
        {
            "status": readiness.status,
            "database": readiness.database,
            "migrations_current": readiness.migrations_current,
            "state_directory": str(state.settings.home),
            "raw_message_retention": state.settings.retain_message_content,
            "outbound_allowed": state.settings.allow_outbound,
        }
    )


@app.command("demo")
def demo(context: typer.Context) -> None:
    """Create, synchronize, and hydrate a private generated demo workspace."""

    state = _state(context)
    root = state.settings.home / "demo-workspace"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    readme = root / "README.md"
    source = root / "retries.py"
    if not readme.exists():
        readme.write_text(
            "# Demo service\n\nRetries use exponential backoff and stop after three attempts.\n",
            encoding="utf-8",
        )
    if not source.exists():
        source.write_text(
            "MAX_RETRIES = 3\n\ndef retry_delay(attempt: int) -> int:\n    return 2 ** attempt\n",
            encoding="utf-8",
        )
    references = root / "docs" / "reference"
    references.mkdir(parents=True, exist_ok=True)
    for index in range(24):
        reference = references / f"component-{index}.md"
        if not reference.exists():
            reference.write_text(
                f"# Component {index}\n\n"
                + ("Architecture, ownership, operations, and release background. " * 30)
                + "\n",
                encoding="utf-8",
            )
    runtime = state.runtime
    workspace = runtime.repository.get_workspace("demo-workspace")
    if workspace is None:
        workspace = runtime.repository.create_workspace(
            "Demo workspace",
            root,
            workspace_id="demo-workspace",
        )
    sync_report = _run(runtime.sync_workspace(workspace.id))
    envelope = _run(
        runtime.hydrate(
            HydrateRequest(
                workspace_id=workspace.id,
                thread_id="demo-thread",
                message="Where is retry behavior defined?",
                max_input_tokens=1_200,
                reserve_output_tokens=300,
            )
        )
    )
    _emit(
        {
            "workspace": workspace.model_dump(mode="json"),
            "sync": sync_report.model_dump(mode="json"),
            "hydration_id": envelope.hydration_id,
            "selected_resources": list(
                dict.fromkeys(item.citation.relative_path for item in envelope.context_items)
            ),
            "fidelity": envelope.fidelity.status,
            "token_plan": envelope.token_plan.model_dump(mode="json"),
        }
    )


@workspace_app.command("add")
def workspace_add(
    context: typer.Context,
    root_path: Annotated[Path, typer.Argument(help="Existing project directory to index.")],
    name: Annotated[str | None, typer.Option("--name", help="Display name.")] = None,
    workspace_id: Annotated[
        str | None, typer.Option("--id", help="Stable optional workspace identifier.")
    ] = None,
) -> None:
    """Register one explicit project root without scanning outside it."""

    runtime = _state(context).runtime
    display_name = name or root_path.resolve().name
    if workspace_id is None:
        result = _run(
            runtime.create_workspace(WorkspaceCreate(name=display_name, root_path=str(root_path)))
        )
    else:
        result = runtime.repository.create_workspace(
            display_name,
            root_path,
            workspace_id=workspace_id,
        )
    _emit(result)


@workspace_app.command("list")
def workspace_list(context: typer.Context) -> None:
    """List registered project roots."""

    _emit(
        [item.model_dump(mode="json") for item in _run(_state(context).runtime.list_workspaces())]
    )


@workspace_app.command("status")
def workspace_status(
    context: typer.Context,
    workspace_id: Annotated[str, typer.Argument(help="Workspace identifier.")],
) -> None:
    """Show current generation and freshness counts."""

    _emit(_run(_state(context).runtime.workspace_status(workspace_id)))


@workspace_app.command("sync")
def workspace_sync(
    context: typer.Context,
    workspace_id: Annotated[str, typer.Argument(help="Workspace identifier.")],
) -> None:
    """Publish one atomic incremental workspace generation."""

    _emit(_run(_state(context).runtime.sync_workspace(workspace_id)))


@workspace_app.command("watch")
def workspace_watch(
    context: typer.Context,
    workspace_id: Annotated[str, typer.Argument(help="Workspace identifier.")],
    interval: Annotated[
        float, typer.Option("--interval", min=0.5, help="Polling reconciliation interval.")
    ] = 2.0,
) -> None:
    """Continuously reconcile a workspace until interrupted."""

    runtime = _state(context).runtime
    try:
        while True:
            report = _run(runtime.sync_workspace(workspace_id))
            _emit(report)
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("Workspace watch stopped.", err=True)


def _parse_resource_reference(reference: str) -> tuple[str, str]:
    parsed = urlsplit(reference)
    if parsed.scheme != "context-loom" or parsed.query:
        raise typer.BadParameter("expected a Context Loom resource recovery URI")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    modern = parsed.netloc == "resources" and len(parts) == 3 and parts[1] == "versions"
    legacy = parsed.netloc == "resource" and len(parts) == 3 and parts[1] == "version"
    if not (modern or legacy) or not parts[0] or not parts[2]:
        raise typer.BadParameter("expected context-loom://resources/RESOURCE/versions/VERSION")
    return parts[0], parts[2]


@resource_app.command("resolve")
def resource_resolve(
    context: typer.Context,
    reference: Annotated[str, typer.Argument(help="Recovery URI from an omission manifest.")],
) -> None:
    """Read one immutable sanitized resource version from local storage."""

    resource_id, version_id = _parse_resource_reference(reference)
    _emit(_run(_state(context).runtime.resolve_resource_version(resource_id, version_id)))


@app.command("hydrate")
def hydrate(
    context: typer.Context,
    workspace_id: Annotated[str, typer.Argument(help="Workspace identifier.")],
    message: Annotated[
        str,
        typer.Argument(help="Exact user message, or '-' to read it byte-for-byte from stdin."),
    ],
    thread_id: Annotated[str | None, typer.Option("--thread-id")] = None,
    thread_label: Annotated[str | None, typer.Option("--thread-label")] = None,
    adapter: Annotated[str, typer.Option("--adapter")] = "generic_markdown",
    mode: Annotated[CompactionMode, typer.Option("--mode")] = CompactionMode.HYBRID_SAFE,
    max_input_tokens: Annotated[int, typer.Option("--max-input-tokens", min=256)] = 4_000,
    reserve_output_tokens: Annotated[int, typer.Option("--reserve-output-tokens", min=0)] = 800,
    use_local_model: Annotated[bool, typer.Option("--use-local-model")] = False,
    envelope_json: Annotated[
        bool, typer.Option("--envelope-json", help="Print the canonical envelope as JSON.")
    ] = False,
) -> None:
    """Compile selected current evidence around one exact chat message."""

    exact_message = sys.stdin.read() if message == "-" else message
    request = HydrateRequest(
        workspace_id=workspace_id,
        message=exact_message,
        thread_id=thread_id,
        thread_label=thread_label,
        adapter=adapter,
        mode=mode,
        max_input_tokens=max_input_tokens,
        reserve_output_tokens=reserve_output_tokens,
        use_local_model=use_local_model,
    )
    envelope = _run(_state(context).runtime.hydrate(request))
    if envelope_json:
        _emit(envelope)
        return
    rendered = AdapterRegistry().render(adapter, envelope)
    if isinstance(rendered.payload, str):
        typer.echo(rendered.payload)
    else:
        _emit(rendered.payload)


@app.command("explain")
def explain(
    context: typer.Context,
    hydration_id: Annotated[str, typer.Argument(help="Hydration identifier.")],
) -> None:
    """Explain selection scores, omissions, and fidelity gates."""

    _emit(_run(_state(context).runtime.explain_hydration(hydration_id)))


@thread_app.command("list")
def thread_list(
    context: typer.Context,
    workspace_id: Annotated[str | None, typer.Option("--workspace-id")] = None,
) -> None:
    """List lifetime summaries with per-turn history."""

    records = _run(_state(context).runtime.list_threads(workspace_id))
    _emit([item.model_dump(mode="json") for item in records])


@thread_app.command("stats")
def thread_stats(
    context: typer.Context,
    thread_id: Annotated[str, typer.Argument(help="Thread identifier.")],
) -> None:
    """Show projected, observed, and verified token totals separately."""

    _emit(_run(_state(context).runtime.thread_stats(thread_id)))


@thread_app.command("record-usage")
def thread_record_usage(
    context: typer.Context,
    thread_id: Annotated[str, typer.Argument(help="Thread identifier.")],
    provider: Annotated[str, typer.Option("--provider")],
    model: Annotated[str, typer.Option("--model")],
    idempotency_key: Annotated[
        str, typer.Option("--idempotency-key", help="Stable retry-safe event key.")
    ],
    hydration_id: Annotated[str | None, typer.Option("--hydration-id")] = None,
    input_tokens: Annotated[int | None, typer.Option("--input-tokens", min=0)] = None,
    output_tokens: Annotated[int | None, typer.Option("--output-tokens", min=0)] = None,
    cached_input_tokens: Annotated[int | None, typer.Option("--cached-input-tokens", min=0)] = None,
    reasoning_tokens: Annotated[int | None, typer.Option("--reasoning-tokens", min=0)] = None,
    billable_input_tokens: Annotated[
        int | None, typer.Option("--billable-input-tokens", min=0)
    ] = None,
    billable_output_tokens: Annotated[
        int | None, typer.Option("--billable-output-tokens", min=0)
    ] = None,
    verified_baseline_input_tokens: Annotated[
        int | None, typer.Option("--verified-baseline-input-tokens", min=0)
    ] = None,
) -> None:
    """Import one immutable provider usage observation."""

    summary = _run(
        _state(context).runtime.record_usage(
            UsageObservation(
                idempotency_key=idempotency_key,
                thread_id=thread_id,
                hydration_id=hydration_id,
                provider=provider,
                model=model,
                counting_method=CountingMethod.PROVIDER_OBSERVED,
                actual_input_tokens=input_tokens,
                actual_output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                reasoning_tokens=reasoning_tokens,
                billable_input_tokens=billable_input_tokens,
                billable_output_tokens=billable_output_tokens,
                verified_baseline_input_tokens=verified_baseline_input_tokens,
            )
        )
    )
    _emit(summary)


@thread_app.command("export")
def thread_export(
    context: typer.Context,
    thread_id: Annotated[str, typer.Argument(help="Thread identifier.")],
    export_format: Annotated[str, typer.Option("--format")] = "parquet",
    include_content: Annotated[bool, typer.Option("--include-content")] = False,
) -> None:
    """Write a private analytics export with raw content omitted by default."""

    if export_format not in {"jsonl", "parquet"}:
        raise typer.BadParameter("format must be jsonl or parquet", param_hint="--format")
    from context_loom.api.contracts import ExportRequest

    artifact = _run(
        _state(context).runtime.create_export(
            ExportRequest(
                thread_id=thread_id,
                format=export_format,
                include_content=include_content,
            )
        )
    )
    _emit(artifact)


@adapter_app.command("list")
def adapter_list() -> None:
    """List supported renderers and usage visibility."""

    _emit([item.model_dump(mode="json") for item in AdapterRegistry().capabilities()])


@adapter_app.command("preview")
def adapter_preview(
    harness: Annotated[str, typer.Argument(help="codex, claude, cursor, copilot, gemini, generic")],
    details: Annotated[
        bool,
        typer.Option("--details", help="Print snippet metadata as JSON."),
    ] = False,
) -> None:
    """Print a copyable MCP snippet without editing harness files."""

    preview = build_installation_preview(harness, command=_context_loom_executable())
    if details:
        _emit(preview)
        return
    typer.echo(preview.content, nl=False)


@adapter_app.command("install")
def adapter_install(
    harness: Annotated[str, typer.Argument(help="Harness name.")],
    target: Annotated[Path, typer.Option("--target", help="Standalone snippet destination.")],
    write: Annotated[
        bool,
        typer.Option("--write", help="Acknowledge the explicit standalone file write."),
    ] = False,
    overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
) -> None:
    """Write only a reviewed standalone snippet; never merge global configuration."""

    preview = build_installation_preview(harness, command=_context_loom_executable())
    if not write:
        typer.echo(preview.content, nl=False)
        typer.echo("Preview only; no file was written. Add --write to create the target.", err=True)
        raise typer.Exit(code=2)
    written = write_preview(preview, target, overwrite=overwrite)
    _emit({"written": str(written), "harness": harness})


@mcp_app.command("serve")
def mcp_serve(
    context: typer.Context,
    transport: Annotated[str, typer.Option("--transport")] = "stdio",
) -> None:
    """Start the MCP server over stdio, SSE, or streamable HTTP."""

    if transport not in {"stdio", "sse", "streamable-http"}:
        raise typer.BadParameter("unsupported MCP transport", param_hint="--transport")
    run_mcp_server(_state(context).runtime, transport=transport)  # type: ignore[arg-type]


@app.command("serve")
def serve(
    context: typer.Context,
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port", min=1, max=65535)] = None,
) -> None:
    """Serve the API and built workbench on the configured loopback address."""

    state = _state(context)
    effective_host = host or state.settings.host
    effective_port = port or state.settings.port
    # This fail-closed guard rejects an unacknowledged non-loopback bind.
    if (
        effective_host == "0.0.0.0"  # nosec B104 # noqa: S104
        and not state.settings.allow_non_loopback
    ):
        raise typer.BadParameter(
            "0.0.0.0 requires CONTEXT_LOOM_ALLOW_NON_LOOPBACK=true",
            param_hint="--host",
        )
    proxy = None
    if state.settings.proxy_upstream_url:

        async def record_proxy_usage(observation: UsageObservation) -> None:
            await state.runtime.record_usage(observation)

        proxy = OpenAICompatibleProxy(
            upstream_url=state.settings.proxy_upstream_url,
            allow_outbound=state.settings.allow_outbound,
            usage_sink=record_proxy_usage,
        )
    api = create_app(state.runtime, proxy=proxy)
    uvicorn.run(
        api, host=effective_host, port=effective_port, log_level=state.settings.log_level.lower()
    )


@app.command("doctor")
def doctor(context: typer.Context) -> None:
    """Verify the local runtime, schema, search extension, and privacy defaults."""

    state = _state(context)
    runtime = state.runtime
    readiness = _run(runtime.readiness())
    checks: list[dict[str, Any]] = [
        {"name": "python", "status": "pass", "detail": sys.version.split()[0]},
        {
            "name": "database",
            "status": "pass" if readiness.database == "ready" else "fail",
            "detail": readiness.database,
        },
        {
            "name": "migrations",
            "status": "pass" if readiness.migrations_current else "fail",
            "detail": "current" if readiness.migrations_current else "outdated",
        },
        {
            "name": "privacy",
            "status": "pass",
            "detail": (
                "raw message retention enabled by operator"
                if state.settings.retain_message_content
                else "raw messages are not persisted"
            ),
        },
        {
            "name": "outbound",
            "status": "pass",
            "detail": "allowed by operator" if state.settings.allow_outbound else "denied",
        },
        {
            "name": "local_model",
            "status": "pass" if readiness.local_model != "unavailable" else "optional",
            "detail": readiness.local_model,
        },
    ]
    try:
        runtime.database.scalar("SELECT COUNT(*) FROM chunk_fts")
    except sqlite3.Error:
        checks.append({"name": "fts5", "status": "fail", "detail": "unavailable"})
    else:
        checks.append({"name": "fts5", "status": "pass", "detail": "available"})
    _emit({"status": readiness.status, "checks": checks})
    if any(item["status"] == "fail" for item in checks):
        raise typer.Exit(code=1)


@app.command("benchmark")
def benchmark(context: typer.Context) -> None:
    """Run a deterministic credential-free indexing and hydration smoke benchmark."""

    state = _state(context)
    with tempfile.TemporaryDirectory(prefix="context-loom-benchmark-") as temporary:
        root = Path(temporary) / "workspace"
        root.mkdir()
        for index in range(12):
            (root / f"module_{index}.py").write_text(
                f"RETRY_LIMIT_{index} = {index + 1}\n\ndef backoff_{index}(attempt: int) -> int:\n"
                f"    return attempt * {index + 1}\n",
                encoding="utf-8",
            )
        runtime = ContextLoomRuntime(
            state.settings.model_copy(
                update={"home": Path(temporary) / "state", "retain_message_content": False}
            )
        )
        started = time.perf_counter()
        workspace = runtime.repository.create_workspace(
            "benchmark",
            root,
            workspace_id=f"benchmark-{uuid.uuid4()}",
        )
        sync_report = _run(runtime.sync_workspace(workspace.id))
        envelope = _run(
            runtime.hydrate(
                HydrateRequest(
                    workspace_id=workspace.id,
                    message="Find the retry limit and backoff in module_7.py",
                    max_input_tokens=1_200,
                )
            )
        )
        elapsed_ms = (time.perf_counter() - started) * 1_000
    _emit(
        {
            "status": "passed",
            "duration_ms": round(elapsed_ms, 2),
            "indexed_resources": sync_report.added,
            "selected_context_items": len(envelope.context_items),
            "fidelity": envelope.fidelity.status,
            "baseline_estimated_tokens": envelope.token_plan.baseline.tokens,
            "hydrated_estimated_tokens": envelope.token_plan.hydrated.tokens,
            "projected_input_tokens_saved": envelope.token_plan.projected_input_tokens_saved,
        }
    )


if __name__ == "__main__":  # pragma: no cover
    app()
