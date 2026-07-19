"""Model-aware token estimates with stable counting-method fingerprints."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

import tiktoken
from pydantic import ConfigDict, Field, computed_field

from context_loom.domain.models import CountingMethod, StrictModel, TokenEstimate


class TokenizerProfile(StrictModel):
    """Immutable description of how a token number was produced."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    provider: str | None = None
    model: str | None = None
    method: CountingMethod
    tokenizer: str
    tokenizer_version: str | None = None
    characters_per_token: float | None = Field(default=None, gt=0)
    confidence: float = Field(ge=0, le=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


@lru_cache(maxsize=64)
def profile_for(provider: str | None = None, model: str | None = None) -> TokenizerProfile:
    """Resolve an exact local profile when available, otherwise a named estimate tier."""

    normalized_provider = (provider or "").casefold()
    normalized_model = (model or "").casefold()
    openai_compatible = normalized_provider in {"openai", "azure_openai", "azure-openai"} or (
        normalized_model.startswith(("gpt-", "o1", "o3", "o4", "codex"))
    )
    if openai_compatible:
        encoding_name = "o200k_base"
        if normalized_model.startswith(("gpt-3.5", "gpt-4-", "text-embedding-ada")):
            encoding_name = "cl100k_base"
        return TokenizerProfile(
            name=f"tiktoken-{encoding_name}",
            provider=provider,
            model=model,
            method=CountingMethod.EXACT_LOCAL,
            tokenizer=encoding_name,
            tokenizer_version=_package_version("tiktoken"),
            confidence=1.0,
        )
    if normalized_provider in {"anthropic", "claude"} or normalized_model.startswith("claude"):
        return TokenizerProfile(
            name="anthropic-calibrated-characters",
            provider=provider,
            model=model,
            method=CountingMethod.CALIBRATED_ESTIMATE,
            tokenizer="utf8-chars-div-3.5",
            tokenizer_version="context-loom-v1",
            characters_per_token=3.5,
            confidence=0.72,
        )
    if normalized_provider in {"google", "gemini"} or normalized_model.startswith("gemini"):
        return TokenizerProfile(
            name="gemini-calibrated-characters",
            provider=provider,
            model=model,
            method=CountingMethod.CALIBRATED_ESTIMATE,
            tokenizer="utf8-chars-div-3.8",
            tokenizer_version="context-loom-v1",
            characters_per_token=3.8,
            confidence=0.68,
        )
    return TokenizerProfile(
        name="provider-neutral-rough-characters",
        provider=provider,
        model=model,
        method=CountingMethod.ROUGH_ESTIMATE,
        tokenizer="utf8-chars-div-3.5",
        tokenizer_version="context-loom-v1",
        characters_per_token=3.5,
        confidence=0.5,
    )


@lru_cache(maxsize=8)
def _encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


class TokenEstimator:
    """Reusable estimator bound to a provider/model profile."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        *,
        profile: TokenizerProfile | None = None,
    ) -> None:
        self.profile = profile or profile_for(provider, model)

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self.profile.method is CountingMethod.EXACT_LOCAL:
            return len(_encoding(self.profile.tokenizer).encode(text, disallowed_special=()))
        ratio = self.profile.characters_per_token or 3.5
        return max(1, math.ceil(len(text.encode("utf-8")) / ratio))

    def estimate(self, text: str) -> TokenEstimate:
        return TokenEstimate(
            tokens=self.count(text),
            method=self.profile.method,
            tokenizer=f"{self.profile.tokenizer}:{self.profile.fingerprint}",
            tokenizer_version=self.profile.tokenizer_version,
            provider=self.profile.provider,
            model=self.profile.model,
            confidence=self.profile.confidence,
        )


def estimate_tokens(
    text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    profile: TokenizerProfile | None = None,
) -> TokenEstimate:
    """One-shot helper that retains all method and tokenizer provenance."""

    return TokenEstimator(provider, model, profile=profile).estimate(text)
