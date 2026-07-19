from __future__ import annotations

import os
from pathlib import Path

import pytest

from context_loom.indexing.scanner import WorkspaceScanner, bounded_read, scan_workspace


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".envrc",
        "id_rsa",
        "private.pem",
        "credentials.json",
        "credentials.prod.json",
    ],
)
def test_sensitive_paths_are_never_indexed(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("SECRET=value")
    (tmp_path / ".contextloomignore").write_text(f"!{name}\n")

    assert name not in {item.relative_path for item in scan_workspace(tmp_path)}


def test_git_and_contextloom_ignore_rules_include_negation(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored/\n*.tmp\n!keep.tmp\n")
    (tmp_path / ".contextloomignore").write_text("private.md\n")
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "inside.py").write_text("print('not indexed')\n")
    (tmp_path / "drop.tmp").write_text("drop\n")
    (tmp_path / "keep.tmp").write_text("keep\n")
    (tmp_path / "private.md").write_text("private\n")
    (tmp_path / "public.md").write_text("public\n")

    batch = WorkspaceScanner(tmp_path).scan()
    paths = {item.relative_path for item in batch.files}
    assert "ignored/inside.py" not in paths
    assert "drop.tmp" not in paths
    assert "private.md" not in paths
    assert {"keep.tmp", "public.md"} <= paths


def test_scanner_never_follows_symlinks_or_binary_files(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside secret")
    os.symlink(outside, tmp_path / "linked.txt")
    (tmp_path / "binary.dat").write_bytes(b"text\x00binary")
    (tmp_path / "safe.txt").write_text("safe")

    batch = WorkspaceScanner(tmp_path).scan()
    paths = {item.relative_path for item in batch.files}
    reasons = {item.relative_path: item.reason for item in batch.exclusions}
    assert paths == {"safe.txt"}
    assert reasons["linked.txt"] == "symlink"
    assert reasons["binary.dat"] == "binary_or_unsupported_text"


def test_scanner_redacts_values_before_hashing_or_returning(tmp_path: Path) -> None:
    source = tmp_path / "settings.md"
    source.write_text(
        "API_KEY=super-secret-token\n"
        "OPENAI_API_KEY='provider-secret-value'\n"
        "AWS_SECRET_ACCESS_KEY: cloud-secret-value\n"
        "password: hunter2\n"
        "normal=value\n"
    )

    scanned = scan_workspace(tmp_path)[0]
    assert "super-secret-token" not in scanned.content
    assert "provider-secret-value" not in scanned.content
    assert "cloud-secret-value" not in scanned.content
    assert "hunter2" not in scanned.content
    assert scanned.content.count("<REDACTED>") == 4
    assert scanned.redacted_count == 4


def test_bounded_read_rejects_oversized_content(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("x" * 32)
    batch = WorkspaceScanner(tmp_path, max_file_bytes=16).scan()
    assert not batch.files
    assert batch.exclusions[0].reason == "file_too_large"
    with pytest.raises(OSError, match="exceeds"):
        bounded_read(tmp_path, "large.txt", max_bytes=16)
