from __future__ import annotations

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

from context_loom.cli import app
from context_loom.config import load_settings
from context_loom.runtime import ContextLoomRuntime

runner = CliRunner()


def test_init_and_doctor_are_credential_free(tmp_path: Path) -> None:
    home = tmp_path / "state"
    initialized = runner.invoke(app, ["--home", str(home), "init"])
    assert initialized.exit_code == 0, initialized.output
    assert json.loads(initialized.stdout)["database"] == "ready"

    checked = runner.invoke(app, ["--home", str(home), "doctor"])
    assert checked.exit_code == 0, checked.output
    body = json.loads(checked.stdout)
    assert body["status"] == "ready"
    assert {item["name"] for item in body["checks"]} >= {"database", "fts5", "privacy"}


def test_workspace_sync_hydrate_and_thread_history(tmp_path: Path) -> None:
    home = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "retry.py").write_text("MAX_RETRIES = 3\n", encoding="utf-8")

    added = runner.invoke(
        app,
        [
            "--home",
            str(home),
            "workspace",
            "add",
            str(workspace),
            "--name",
            "Demo",
            "--id",
            "demo",
        ],
    )
    assert added.exit_code == 0, added.output
    assert json.loads(added.stdout)["id"] == "demo"

    synced = runner.invoke(app, ["--home", str(home), "workspace", "sync", "demo"])
    assert synced.exit_code == 0, synced.output
    assert json.loads(synced.stdout)["added"] >= 1

    hydrated = runner.invoke(
        app,
        [
            "--home",
            str(home),
            "hydrate",
            "demo",
            "Where is MAX_RETRIES?",
            "--thread-id",
            "thread-1",
            "--thread-label",
            "Retry policy review",
            "--envelope-json",
        ],
    )
    assert hydrated.exit_code == 0, hydrated.output
    envelope = json.loads(hydrated.stdout)
    assert envelope["message_exact"] == "Where is MAX_RETRIES?"

    threads = runner.invoke(
        app,
        ["--home", str(home), "thread", "list", "--workspace-id", "demo"],
    )
    assert threads.exit_code == 0, threads.output
    history = json.loads(threads.stdout)
    assert history[0]["thread_id"] == "thread-1"
    assert history[0]["label"] == "Retry policy review"
    assert history[0]["history"][0]["hydration_id"] == envelope["hydration_id"]

    resource = asyncio.run(ContextLoomRuntime(load_settings(home=home)).list_resources("demo"))[0]
    reference = f"context-loom://resources/{resource.resource_id}/versions/{resource.version_id}"
    resolved = runner.invoke(
        app,
        ["--home", str(home), "resource", "resolve", reference],
    )
    assert resolved.exit_code == 0, resolved.output
    recovered = json.loads(resolved.stdout)
    assert recovered["content"] == "MAX_RETRIES = 3\n"
    assert recovered["current"] is True


def test_adapter_install_is_preview_first(tmp_path: Path) -> None:
    target = tmp_path / "context-loom.toml"
    preview = runner.invoke(app, ["adapter", "install", "codex", "--target", str(target)])
    assert preview.exit_code == 2
    assert not target.exists()
    assert "mcp_servers.context_loom" in preview.stdout

    written = runner.invoke(
        app,
        ["adapter", "install", "codex", "--target", str(target), "--write"],
    )
    assert written.exit_code == 0, written.output
    assert target.stat().st_mode & 0o777 == 0o600


def test_adapter_preview_prints_the_bare_copyable_snippet_by_default() -> None:
    preview = runner.invoke(app, ["adapter", "preview", "codex"])

    assert preview.exit_code == 0, preview.output
    assert preview.stdout.startswith("[mcp_servers.context_loom]")
    assert '"content"' not in preview.stdout

    details = runner.invoke(app, ["adapter", "preview", "codex", "--details"])
    assert details.exit_code == 0, details.output
    assert json.loads(details.stdout)["format"] == "toml"


def test_demo_reports_a_positive_projected_reduction(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--home", str(tmp_path / "state"), "demo"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["token_plan"]["projected_input_tokens_saved"] > 0
