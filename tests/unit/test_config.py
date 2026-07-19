from __future__ import annotations

import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from context_loom.config import Settings


def test_settings_prepare_private_state_directories(tmp_path: Path) -> None:
    home = tmp_path / "state"
    settings = Settings(home=home)
    settings.prepare()
    assert settings.database_path == home / "context-loom.db"
    assert settings.objects_dir.is_dir()
    assert stat.S_IMODE(home.stat().st_mode) == 0o700


def test_settings_are_offline_and_loopback_by_default(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path)
    assert settings.host == "127.0.0.1"
    assert settings.allow_outbound is False
    assert settings.retain_message_content is False


def test_settings_reject_unknown_network_bind_address(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(home=tmp_path, host="192.0.2.5")


def test_settings_require_acknowledgement_for_all_interfaces(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(home=tmp_path, host="0.0.0.0")
    assert Settings(home=tmp_path, host="0.0.0.0", allow_non_loopback=True).allow_non_loopback
