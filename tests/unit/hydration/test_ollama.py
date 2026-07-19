from __future__ import annotations

import hashlib

import httpx
import pytest

from context_loom.compaction.ollama import OllamaCompactionError, OllamaCompactor
from context_loom.domain.models import ContextItem, ResourceCitation, ResourceKind, ScoreBreakdown


def item() -> ContextItem:
    excerpt = "MAX_RETRIES = 3"
    return ContextItem(
        citation=ResourceCitation(
            resource_id="resource-1",
            version_id="version-1",
            chunk_id="chunk-1",
            relative_path="src/retry.py",
            sha256="a" * 64,
            excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
            start_line=1,
            end_line=1,
        ),
        kind=ResourceKind.CODE,
        excerpt=excerpt,
        score=ScoreBreakdown(total=1.0),
        selection_reason="direct_reference",
    )


def test_ollama_requires_outbound_opt_in() -> None:
    with pytest.raises(OllamaCompactionError, match="disabled"):
        OllamaCompactor(
            allow_outbound=False,
            base_url="http://127.0.0.1:11434",
            model="test",
        )


def test_ollama_rejects_non_loopback_url() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaCompactor(
            allow_outbound=True,
            base_url="https://example.com",
            model="test",
        )


def test_ollama_accepts_only_selected_current_citations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": (
                    '{"claims":[{"text":"Retries are bounded.","citations":'
                    '[{"version_id":"version-1","chunk_id":"chunk-1"}]}]}'
                ),
                "prompt_eval_count": 14,
                "eval_count": 9,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OllamaCompactor(
        allow_outbound=True,
        base_url="http://127.0.0.1:11434",
        model="test",
        client=client,
    ).compact([item()])
    assert result.digest is not None
    assert "src/retry.py@version-1:L1-L1" in result.digest
    assert result.input_tokens == 14
    assert result.output_tokens == 9
    client.close()


def test_ollama_contract_failure_preserves_observed_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={"response": "not-json", "prompt_eval_count": 23, "eval_count": 7},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(OllamaCompactionError) as failure:
        OllamaCompactor(
            allow_outbound=True,
            base_url="http://127.0.0.1:11434",
            model="test",
            client=client,
        ).compact([item()])
    assert failure.value.input_tokens == 23
    assert failure.value.output_tokens == 7
    client.close()
