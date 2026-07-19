from __future__ import annotations

import json
import stat
from pathlib import Path

import pyarrow.parquet as pq

from context_loom.exports import ExportPolicy, export_jsonl, export_parquet


def analytics_record() -> dict[str, object]:
    return {
        "thread_id": "thread-1",
        "hydration_id": "hydration-1",
        "message_exact": "private user message",
        "context_items": [
            {
                "excerpt": "private source body",
                "citation": {"version_id": "version-1", "sha256": "a" * 64},
                "score": {"lexical": 0.8, "dense": 0.5, "total": 0.7},
            }
        ],
        "fidelity": {"status": "passed", "protected_atom_coverage": 1.0},
        "token_plan": {
            "baseline": {"tokens": 1_200, "method": "rough_estimate"},
            "hydrated": {"tokens": 400, "method": "rough_estimate"},
        },
        "feedback": {"rating": 1, "category": "relevant"},
        "annotation": "password=do-not-export-this-value",
        "api_key": "must-never-export",
        "client_secret": "also-must-never-export",
    }


def assert_private_file(path: Path) -> None:
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_jsonl_export_is_sanitized_by_default(tmp_path: Path) -> None:
    destination = tmp_path / "analytics.jsonl"
    result = export_jsonl([analytics_record()], destination)
    payload = destination.read_text()
    record = json.loads(payload)
    assert result.rows == 1
    assert "private user message" not in payload
    assert "private source body" not in payload
    assert "must-never-export" not in payload
    assert "also-must-never-export" not in payload
    assert "do-not-export-this-value" not in payload
    assert record["annotation"] == "[REDACTED]"
    assert record["context_items"][0]["citation"]["version_id"] == "version-1"
    assert record["context_items"][0]["score"]["lexical"] == 0.8
    assert record["feedback"]["category"] == "relevant"
    assert_private_file(destination)


def test_raw_export_requires_explicit_consent_but_still_omits_credentials(tmp_path: Path) -> None:
    destination = tmp_path / "consented.jsonl"
    export_jsonl(
        [analytics_record()],
        destination,
        policy=ExportPolicy(include_raw_content=True),
    )
    payload = destination.read_text()
    assert "private user message" in payload
    assert "private source body" in payload
    assert "must-never-export" not in payload


def test_parquet_export_round_trips_sanitized_analytics(tmp_path: Path) -> None:
    destination = tmp_path / "analytics.parquet"
    result = export_parquet([analytics_record()], destination)
    table = pq.read_table(destination)
    payload = json.dumps(table.to_pylist())
    assert result.rows == 1
    assert "private user message" not in payload
    assert "private source body" not in payload
    assert "must-never-export" not in payload
    assert table.schema.metadata is not None
    assert table.schema.metadata[b"context_loom_export"] == b"sanitized-v1"
    assert_private_file(destination)
