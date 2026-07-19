"""Privacy-preserving JSONL and Parquet analytics exports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

from context_loom.domain.models import StrictModel

_ALWAYS_PRIVATE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "password",
        "private_key",
        "secret",
        "access_token",
        "refresh_token",
    }
)
_RAW_CONTENT_KEYS = frozenset(
    {
        "body",
        "content",
        "context_digest",
        "excerpt",
        "message",
        "message_exact",
        "prompt",
        "raw_message",
        "raw_request",
        "raw_response",
        "source_body",
        "system_prompt",
    }
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(?:ghp|github_pat|sk|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+\S+"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|secret)\s*[:=]\s*\S+"),
)


def _is_private_key(key: str) -> bool:
    return key in _ALWAYS_PRIVATE_KEYS or key.endswith(
        ("_api_key", "_credential", "_password", "_private_key", "_secret", "_token")
    )


def _is_raw_content_key(key: str) -> bool:
    return (
        key in _RAW_CONTENT_KEYS
        or key.startswith("raw_")
        or key.endswith(
            ("_body", "_excerpt", "_message", "_prompt", "_source_text", "_source_content")
        )
    )


class ExportPolicy(StrictModel):
    """Explicit consent boundary for raw message and source content."""

    include_raw_content: bool = False


class ExportResult(StrictModel):
    """Stable metadata returned after a completed atomic export."""

    path: str
    format: Literal["jsonl", "parquet"]
    rows: int = Field(ge=0)
    bytes_written: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple | set | frozenset):
        return list(value)
    return value


def sanitize_record(record: BaseModel | Mapping[str, Any], policy: ExportPolicy) -> dict[str, Any]:
    """Recursively omit secrets and raw content while retaining analytics evidence."""

    raw = _json_value(record)
    if not isinstance(raw, Mapping):
        raise TypeError("export records must be Pydantic models or mappings")

    def sanitize(value: Any) -> Any:
        value = _json_value(value)
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for key, nested in value.items():
                key_text = str(key)
                normalized = key_text.casefold()
                if _is_private_key(normalized):
                    continue
                if not policy.include_raw_content and _is_raw_content_key(normalized):
                    continue
                sanitized[key_text] = sanitize(nested)
            return sanitized
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            return [sanitize(item) for item in value]
        if isinstance(value, str) and any(
            pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS
        ):
            return "[REDACTED]"
        return value

    sanitized_record = sanitize(raw)
    if not isinstance(sanitized_record, dict):
        raise TypeError("sanitized export record must remain a mapping")
    return sanitized_record


def _atomic_target(path: Path) -> tuple[int, Path]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.chmod(temporary, 0o600)
    return descriptor, Path(temporary)


def _result(path: Path, export_format: Literal["jsonl", "parquet"], rows: int) -> ExportResult:
    payload = path.read_bytes()
    return ExportResult(
        path=str(path),
        format=export_format,
        rows=rows,
        bytes_written=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def export_jsonl(
    records: Iterable[BaseModel | Mapping[str, Any]],
    destination: Path,
    *,
    policy: ExportPolicy | None = None,
) -> ExportResult:
    """Write sanitized one-record-per-line JSON atomically with private permissions."""

    active_policy = policy or ExportPolicy()
    sanitized = [sanitize_record(record, active_policy) for record in records]
    descriptor, temporary = _atomic_target(destination)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for record in sanitized:
                handle.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                )
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return _result(destination, "jsonl", len(sanitized))


def export_parquet(
    records: Iterable[BaseModel | Mapping[str, Any]],
    destination: Path,
    *,
    policy: ExportPolicy | None = None,
) -> ExportResult:
    """Write sanitized derived analytics as an atomic Parquet file."""

    active_policy = policy or ExportPolicy()
    sanitized = [sanitize_record(record, active_policy) for record in records]
    if sanitized:
        table = pa.Table.from_pylist(sanitized)
    else:
        table = pa.table({"exported_at": pa.array([], type=pa.timestamp("us", tz="UTC"))})
    metadata = dict(table.schema.metadata or {})
    metadata[b"context_loom_export"] = b"sanitized-v1"
    metadata[b"raw_content_included"] = str(active_policy.include_raw_content).lower().encode()
    metadata[b"generated_at"] = datetime.now(UTC).isoformat().encode()
    table = table.replace_schema_metadata(metadata)

    descriptor, temporary = _atomic_target(destination)
    os.close(descriptor)
    try:
        pq.write_table(table, temporary, compression="zstd")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return _result(destination, "parquet", len(sanitized))
