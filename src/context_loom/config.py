"""Context Loom settings and private local-state initialization."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from platformdirs import user_data_path
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings with local-first and fail-closed defaults."""

    model_config = SettingsConfigDict(
        env_prefix="CONTEXT_LOOM_",
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    home: Path = Field(default_factory=lambda: user_data_path("context-loom", "ownasquare"))
    host: str = "127.0.0.1"
    allow_non_loopback: bool = False
    port: int = Field(default=8768, ge=1, le=65535)
    log_level: str = "INFO"
    allow_outbound: bool = False
    proxy_upstream_url: str | None = None
    retain_message_content: bool = False
    hydration_cache_max_entries: int = Field(default=128, ge=1, le=10_000)
    hydration_cache_ttl_seconds: float = Field(default=900.0, gt=0, le=86_400)
    max_file_bytes: int = Field(default=2_000_000, ge=1_024)
    max_workspace_files: int = Field(default=50_000, ge=1)
    chunk_target_tokens: int = Field(default=320, ge=64, le=4_096)
    chunk_overlap_tokens: int = Field(default=40, ge=0, le=1_024)
    stale_after_hours: float = Field(default=168.0, ge=0)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    local_model_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        # This validates, but does not bind, the explicit container-only value.
        if value not in {
            "127.0.0.1",
            "localhost",
            "::1",
            "0.0.0.0",  # nosec B104 # noqa: S104
        }:
            raise ValueError("host must be a loopback address or explicit 0.0.0.0")
        return value

    @model_validator(mode="after")
    def require_non_loopback_acknowledgement(self) -> Settings:
        # This fail-closed guard rejects an unacknowledged non-loopback bind.
        if (
            self.host == "0.0.0.0"  # nosec B104 # noqa: S104
            and not self.allow_non_loopback
        ):
            raise ValueError("0.0.0.0 requires CONTEXT_LOOM_ALLOW_NON_LOOPBACK=true")
        return self

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return normalized

    @property
    def database_path(self) -> Path:
        return self.home / "context-loom.db"

    @property
    def objects_dir(self) -> Path:
        return self.home / "objects"

    @property
    def exports_dir(self) -> Path:
        return self.home / "exports"

    def prepare(self) -> None:
        """Create private runtime directories without weakening existing permissions."""

        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.objects_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.exports_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for directory in (self.home, self.objects_dir, self.exports_dir):
            current_mode = stat.S_IMODE(directory.stat().st_mode)
            if current_mode & 0o077:
                os.chmod(directory, 0o700)


def load_settings(**overrides: Any) -> Settings:
    """Construct settings for the CLI/API or an isolated test."""

    return Settings(**overrides)
