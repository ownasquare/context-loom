from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import check_public_repo

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_public_repo.py"


def _run_check(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- test controls the checked script and arguments.
        [sys.executable, str(SCRIPT), "--root", str(root), *arguments],
        capture_output=True,
        check=False,
        text=True,
    )


def _git(root: Path, *arguments: str) -> None:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("git is required for public-boundary contract tests")
    subprocess.run(  # noqa: S603 -- test controls the temporary repository arguments.
        [git_executable, *arguments],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    )


def _initialize_public_repo(root: Path, *, omit: set[str] | None = None) -> None:
    omitted = omit or set()
    for relative in check_public_repo.REQUIRED_PATHS - omitted:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Boundary Test")
    _git(root, "config", "user.email", "boundary@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "public fixture")


def test_release_mode_rejects_a_required_file_that_exists_only_untracked(tmp_path: Path) -> None:
    relative = "docs/getting-started.md"
    _initialize_public_repo(tmp_path, omit={relative})
    untracked = tmp_path / relative
    untracked.parent.mkdir(parents=True, exist_ok=True)
    untracked.write_text("untracked guide\n", encoding="utf-8")

    result = _run_check(tmp_path, "--release")

    assert result.returncode == 1
    assert "dirty_release_tree" in result.stdout


def test_release_mode_rejects_a_required_file_that_exists_only_ignored(tmp_path: Path) -> None:
    relative = "docs/getting-started.md"
    _initialize_public_repo(tmp_path, omit={relative})
    (tmp_path / ".gitignore").write_text(relative + "\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "-qm", "ignore missing guide")
    ignored = tmp_path / relative
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text("ignored guide\n", encoding="utf-8")

    result = _run_check(tmp_path, "--release")

    assert result.returncode == 1
    assert "release_untracked_required docs/getting-started.md" in result.stdout


def test_release_mode_rejects_a_tracked_file_deleted_from_the_worktree(tmp_path: Path) -> None:
    _initialize_public_repo(tmp_path)
    (tmp_path / "README.md").unlink()

    result = _run_check(tmp_path, "--release")

    assert result.returncode == 1
    assert "dirty_release_tree" in result.stdout
    assert "missing_required README.md" in result.stdout


@pytest.mark.parametrize("relative", [".env.example", "Dockerfile", "frontend/check.mjs"])
def test_nonbinary_public_files_are_scanned_regardless_of_suffix(
    tmp_path: Path,
    relative: str,
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("/" + "Users" + "/example/private-project\n", encoding="utf-8")

    findings = check_public_repo.inspect_path(tmp_path, path)

    assert any(item.code == "machine_path" for item in findings)


@pytest.mark.parametrize(
    ("target", "is_directory"),
    [("missing-target", False), ("docs", True)],
)
def test_candidate_scan_rejects_broken_and_directory_symlinks(
    tmp_path: Path,
    target: str,
    is_directory: bool,
) -> None:
    _initialize_public_repo(tmp_path)
    link = tmp_path / "public-link"
    link.symlink_to(target, target_is_directory=is_directory)
    _git(tmp_path, "add", "public-link")

    result = _run_check(tmp_path)

    assert result.returncode == 1
    assert "tracked_symlink public-link" in result.stdout


def test_deleted_historical_env_file_is_rejected(tmp_path: Path) -> None:
    _initialize_public_repo(tmp_path)
    secret_file = tmp_path / ".env.private"
    secret_file.write_text("PLACEHOLDER=true\n", encoding="utf-8")
    _git(tmp_path, "add", ".env.private")
    _git(tmp_path, "commit", "-qm", "add forbidden fixture")
    secret_file.unlink()
    _git(tmp_path, "add", "-u")
    _git(tmp_path, "commit", "-qm", "remove forbidden fixture")

    result = _run_check(tmp_path, "--history")

    assert result.returncode == 1
    assert "history_forbidden_file .env.private" in result.stdout


def test_oversized_historical_env_file_is_still_rejected(tmp_path: Path) -> None:
    _initialize_public_repo(tmp_path)
    secret_file = tmp_path / ".env.private"
    secret_file.write_bytes(b"A" * 5_000_001)
    _git(tmp_path, "add", ".env.private")
    _git(tmp_path, "commit", "-qm", "add oversized forbidden fixture")
    secret_file.unlink()
    _git(tmp_path, "add", "-u")
    _git(tmp_path, "commit", "-qm", "remove oversized forbidden fixture")

    result = _run_check(tmp_path, "--history")

    assert result.returncode == 1
    assert "history_forbidden_file .env.private" in result.stdout
    assert "history_oversized_file .env.private" in result.stdout


def test_invalid_history_revision_fails_without_echoing_the_input(tmp_path: Path) -> None:
    _initialize_public_repo(tmp_path)

    result = _run_check(tmp_path, "--history", "--revision=--private-invalid-revision")

    assert result.returncode == 1
    assert "history_unavailable .git: could not resolve git revision" in result.stdout
    assert "--private-invalid-revision" not in result.stdout
