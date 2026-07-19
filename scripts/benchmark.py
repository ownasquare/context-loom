#!/usr/bin/env python3
"""Credential-free retrieval, fidelity, latency, and token benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from context_loom.config import Settings
from context_loom.domain.models import HydrateRequest
from context_loom.runtime import ContextLoomRuntime
from context_loom.tokenization.estimators import TokenEstimator

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "demo-workspace"
EVAL_SUITE = Path(__file__).resolve().parents[1] / "evals" / "retrieval-cases.json"


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(round((len(ordered) - 1) * percentile), len(ordered) - 1)
    return ordered[index]


async def run_benchmark(iterations: int) -> dict[str, Any]:
    suite = json.loads(EVAL_SUITE.read_text(encoding="utf-8"))
    cases = suite["cases"]
    targets = suite["targets"]
    incremental_sync_latencies: list[float] = []
    hydration_latencies: list[float] = []
    reductions: list[float] = []
    recalled = 0
    evaluated = 0
    explicit_recalled = 0
    explicit_evaluated = 0
    protected_coverages: list[float] = []
    citation_checks: list[bool] = []
    replay_checks: list[bool] = []
    initial_sync_latency = 0.0
    indexed_resources = 0
    indexed_chunks = 0
    with tempfile.TemporaryDirectory(prefix="context-loom-benchmark-") as temporary:
        temporary_root = Path(temporary)
        workspace_root = temporary_root / "workspace"
        shutil.copytree(FIXTURE, workspace_root)
        noise = workspace_root / "docs" / "reference"
        noise.mkdir(parents=True)
        for index in range(40):
            (noise / f"component-{index}.md").write_text(
                f"# Component {index}\n\n"
                + ("Background architecture, operations, ownership, and release notes. " * 45)
                + "\n",
                encoding="utf-8",
            )
        runtime = ContextLoomRuntime(Settings(home=temporary_root / "state"))
        workspace = runtime.repository.create_workspace(
            "benchmark",
            workspace_root,
            workspace_id="benchmark",
        )
        sync_started = time.perf_counter()
        await runtime.sync_workspace(workspace.id)
        initial_sync_latency = (time.perf_counter() - sync_started) * 1_000
        change_file = workspace_root / "docs" / "benchmark-change.md"
        for iteration in range(iterations):
            change_file.write_text(
                f"# Incremental benchmark change\n\nIteration {iteration}.\n",
                encoding="utf-8",
            )
            sync_started = time.perf_counter()
            await runtime.sync_workspace(workspace.id)
            incremental_sync_latencies.append((time.perf_counter() - sync_started) * 1_000)
            for case in cases:
                message = str(case["message"])
                request = HydrateRequest(
                    workspace_id=workspace.id,
                    thread_id=f"benchmark-{case['id']}-{iteration}",
                    message=message,
                    max_input_tokens=1_600,
                    reserve_output_tokens=300,
                )
                hydrate_started = time.perf_counter()
                envelope = await runtime.hydrate(request)
                hydration_latencies.append((time.perf_counter() - hydrate_started) * 1_000)
                replay = await runtime.hydrate(request)
                replay_checks.append(envelope.fidelity.replay_hash == replay.fidelity.replay_hash)
                selected_items = envelope.context_items[:10]
                selected_paths = {item.citation.relative_path for item in selected_items}
                selected_text = "\n".join(item.excerpt for item in selected_items)
                expected_paths = {str(path) for path in case.get("expected_paths", [])}
                expected_symbols = {str(symbol) for symbol in case.get("expected_symbols", [])}
                recalled += expected_paths <= selected_paths and all(
                    symbol in selected_text for symbol in expected_symbols
                )
                evaluated += 1
                for expected_path in expected_paths:
                    if expected_path in message:
                        explicit_evaluated += 1
                        explicit_recalled += expected_path in selected_paths
                protected_coverages.append(envelope.fidelity.protected_atom_coverage)
                citation_checks.append(envelope.fidelity.citations_valid)
                reductions.append(envelope.token_plan.projected_reduction_percent)
        status = await runtime.workspace_status(workspace.id)
        indexed_resources = status.indexed_resources
        indexed_chunks = status.indexed_chunks
    tokenizer = TokenEstimator().profile
    return {
        "schema_version": "context-loom-benchmark-v2",
        "iterations": iterations,
        "cases": evaluated,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
            "fixture": "examples/demo-workspace",
            "eval_suite": "evals/retrieval-cases.json",
            "indexed_resources": indexed_resources,
            "indexed_chunks": indexed_chunks,
            "noise_files": 40,
            "tokenizer": tokenizer.tokenizer,
            "tokenizer_version": tokenizer.tokenizer_version,
            "tokenizer_fingerprint": tokenizer.fingerprint,
            "cache_state": "warm after initial sync",
            "requested_mode": "hybrid_safe",
            "local_model": False,
        },
        "targets": targets,
        "initial_sync_latency_ms": round(initial_sync_latency, 3),
        "incremental_sync_latency_ms": {
            "p50": round(statistics.median(incremental_sync_latencies), 3),
            "p95": round(_percentile(incremental_sync_latencies, 0.95), 3),
        },
        "hydration_latency_ms": {
            "p50": round(statistics.median(hydration_latencies), 3),
            "p95": round(_percentile(hydration_latencies, 0.95), 3),
        },
        "recall_at_10": round(recalled / evaluated if evaluated else 0.0, 4),
        "explicit_reference_recall": round(
            explicit_recalled / explicit_evaluated if explicit_evaluated else 1.0,
            4,
        ),
        "protected_atom_coverage": round(min(protected_coverages, default=0.0), 4),
        "citation_coverage": round(
            sum(citation_checks) / len(citation_checks) if citation_checks else 0.0,
            4,
        ),
        "median_projected_input_reduction_percent": round(
            statistics.median(reductions) if reductions else 0.0,
            2,
        ),
        "deterministic_replay_rate": round(
            sum(replay_checks) / len(replay_checks) if replay_checks else 0.0,
            4,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json-out", type=Path)
    arguments = parser.parse_args()
    if arguments.iterations < 1:
        parser.error("--iterations must be at least 1")
    result = asyncio.run(run_benchmark(arguments.iterations))
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.json_out:
        arguments.json_out.parent.mkdir(parents=True, exist_ok=True)
        arguments.json_out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    targets = result["targets"]
    if arguments.check and (
        result["recall_at_10"] < targets["recall_at_10"]
        or result["explicit_reference_recall"] < targets["explicit_reference_recall"]
        or result["protected_atom_coverage"] < targets["protected_atom_coverage"]
        or result["citation_coverage"] < targets["citation_coverage"]
        or result["deterministic_replay_rate"] < targets["deterministic_replay_rate"]
        or result["median_projected_input_reduction_percent"]
        < targets["median_projected_input_reduction_percent"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
