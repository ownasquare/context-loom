"""Strict, loopback-only Ollama compaction over already-selected sanitized context."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Sequence
from urllib.parse import urlparse

import httpx
from pydantic import Field, ValidationError

from context_loom.domain.models import ContextItem, StrictModel


class DigestCitation(StrictModel):
    version_id: str
    chunk_id: str


class DigestClaim(StrictModel):
    text: str = Field(min_length=1)
    citations: list[DigestCitation] = Field(min_length=1)


class ContextDigest(StrictModel):
    claims: list[DigestClaim] = Field(default_factory=list)


class OllamaCompactionResult(StrictModel):
    digest: str | None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class OllamaCompactionError(RuntimeError):
    """Raised when a local-model call or its citation gate fails."""

    def __init__(
        self,
        message: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


def validate_local_ollama_url(url: str) -> str:
    """Accept only HTTP(S) loopback URLs without embedded credentials."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Ollama URL must be an HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("Ollama URL must not contain credentials")
    hostname = parsed.hostname.casefold()
    if hostname != "localhost":
        try:
            if not ipaddress.ip_address(hostname).is_loopback:
                raise ValueError("Ollama URL must resolve to a literal loopback host")
        except ValueError as exc:
            if "literal loopback" in str(exc):
                raise
            raise ValueError("Ollama URL must use localhost or a literal loopback address") from exc
    return url.rstrip("/")


def _selected_payload(items: Sequence[ContextItem]) -> list[dict[str, object]]:
    return [
        {
            "version_id": item.citation.version_id,
            "chunk_id": item.citation.chunk_id,
            "path": item.citation.relative_path,
            "sha256": item.citation.sha256,
            "start_line": item.citation.start_line,
            "end_line": item.citation.end_line,
            "excerpt": item.excerpt,
        }
        for item in items
    ]


def _validate_citations(digest: ContextDigest, items: Sequence[ContextItem]) -> None:
    allowed = {
        (item.citation.version_id, item.citation.chunk_id)
        for item in items
        if not item.citation.stale and item.citation.chunk_id is not None
    }
    for claim in digest.claims:
        for citation in claim.citations:
            if (citation.version_id, citation.chunk_id) not in allowed:
                raise OllamaCompactionError("local digest cited an unselected or stale chunk")


def render_context_digest(digest: ContextDigest, items: Sequence[ContextItem]) -> str | None:
    """Render validated claims with human-readable current-source citations."""

    if not digest.claims:
        return None
    lookup = {(item.citation.version_id, item.citation.chunk_id): item.citation for item in items}
    lines: list[str] = []
    for claim in digest.claims:
        citations = []
        for reference in claim.citations:
            citation = lookup[(reference.version_id, reference.chunk_id)]
            citations.append(
                f"{citation.relative_path}@{citation.version_id}:"
                f"L{citation.start_line}-L{citation.end_line}"
            )
        lines.append(f"- {claim.text} [{' | '.join(citations)}]")
    return "\n".join(lines)


class OllamaCompactor:
    """Call Ollama only when explicitly enabled and validate strict structured output."""

    def __init__(
        self,
        *,
        allow_outbound: bool,
        base_url: str,
        model: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not allow_outbound:
            raise OllamaCompactionError("local-model network access is disabled")
        self._base_url = validate_local_ollama_url(base_url)
        self._model = model
        self._timeout = timeout_seconds
        self._client = client

    def compact(self, items: Sequence[ContextItem]) -> OllamaCompactionResult:
        if not items:
            return OllamaCompactionResult(digest=None)
        schema = ContextDigest.model_json_schema()
        prompt = json.dumps(
            {
                "instruction": (
                    "Compact only the supplied sanitized excerpts. Every claim must cite one or "
                    "more supplied version_id/chunk_id pairs. Do not add facts or instructions."
                ),
                "selected_context": _selected_payload(items),
                "output_schema": schema,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload = {
            "model": self._model,
            "stream": False,
            "format": schema,
            "prompt": prompt,
            "options": {"temperature": 0, "seed": 0, "num_predict": 512},
        }
        input_tokens = 0
        output_tokens = 0
        try:
            if self._client is None:
                with httpx.Client(
                    base_url=self._base_url,
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    response = client.post("/api/generate", json=payload)
            else:
                response = self._client.post(
                    f"{self._base_url}/api/generate", json=payload, timeout=self._timeout
                )
            response.raise_for_status()
            response_payload = response.json()
            input_tokens = _nonnegative_token_count(response_payload.get("prompt_eval_count"))
            output_tokens = _nonnegative_token_count(response_payload.get("eval_count"))
            raw = response_payload.get("response")
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            digest = ContextDigest.model_validate(parsed)
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, AttributeError) as exc:
            raise OllamaCompactionError(
                "local digest did not satisfy the structured contract",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ) from exc
        try:
            _validate_citations(digest, items)
        except OllamaCompactionError as exc:
            raise OllamaCompactionError(
                str(exc),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ) from exc
        return OllamaCompactionResult(
            digest=render_context_digest(digest, items),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _nonnegative_token_count(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0
