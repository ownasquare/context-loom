"""Containment-safe, bounded, race-aware text workspace scanner."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from context_loom.indexing.ignore import (
    ScopedIgnore,
    hard_deny_reason,
    ignored_by_rules,
)
from context_loom.indexing.redaction import redact_secrets


class UnsafePathError(OSError):
    """Raised when a read would follow a link or leave the allowlisted root."""


class FileChangedError(OSError):
    """Raised when a file changes during both bounded read attempts."""


class FileTooLargeError(OSError):
    """Raised before an oversized file body is accepted into memory."""


@dataclass(frozen=True, slots=True)
class BoundedRead:
    data: bytes
    size_bytes: int
    mtime_ns: int
    inode: int
    device: int


@dataclass(frozen=True, slots=True)
class ScannedFile:
    relative_path: str
    content: str
    sha256: str
    size_bytes: int
    mtime_ns: int
    inode: int
    device: int
    redacted_count: int
    redaction_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScanExclusion:
    relative_path: str
    reason: str
    preserve_existing: bool = False


@dataclass(frozen=True, slots=True)
class ScanBatch:
    files: tuple[ScannedFile, ...]
    exclusions: tuple[ScanExclusion, ...]


def _open_beneath(root: Path, relative: PurePosixPath) -> int:
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise UnsafePathError("invalid workspace-relative path")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    current = os.open(root, directory_flags | nofollow)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, directory_flags | nofollow, dir_fd=current)
            os.close(current)
            current = child
        return os.open(relative.parts[-1], os.O_RDONLY | nofollow, dir_fd=current)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise UnsafePathError("workspace read refused a symlinked component") from exc
        raise
    finally:
        os.close(current)


def bounded_read(
    root: Path | str,
    relative_path: str,
    *,
    max_bytes: int,
    retries: int = 1,
) -> BoundedRead:
    """Read with openat containment, O_NOFOLLOW, a hard bound, and stat comparison."""

    root_path = Path(root).expanduser()
    if root_path.is_symlink() or not root_path.is_dir():
        raise UnsafePathError("workspace root must be a real directory")
    resolved_root = root_path.resolve(strict=True)
    relative = PurePosixPath(relative_path)
    for attempt in range(retries + 1):
        descriptor = _open_beneath(resolved_root, relative)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise UnsafePathError("workspace reads accept regular files only")
            if before.st_size > max_bytes:
                raise FileTooLargeError("file exceeds configured indexing limit")
            blocks: list[bytes] = []
            total = 0
            while True:
                block = os.read(descriptor, min(65_536, max_bytes + 1 - total))
                if not block:
                    break
                blocks.append(block)
                total += len(block)
                if total > max_bytes:
                    raise FileTooLargeError("file grew beyond configured indexing limit")
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before == identity_after:
            return BoundedRead(
                data=b"".join(blocks),
                size_bytes=after.st_size,
                mtime_ns=after.st_mtime_ns,
                inode=after.st_ino,
                device=after.st_dev,
            )
        if attempt >= retries:
            break
    raise FileChangedError("file changed during bounded read")


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:8_192]:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


class WorkspaceScanner:
    """Traverse only an allowlisted root without following links or project code."""

    def __init__(
        self,
        root: Path | str,
        *,
        max_file_bytes: int = 2_000_000,
        max_files: int = 50_000,
    ) -> None:
        original = Path(root).expanduser()
        if original.is_symlink() or not original.is_dir():
            raise UnsafePathError("workspace root must be an existing non-symlinked directory")
        self.root = original.resolve(strict=True)
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    def _load_ignore(self, base: PurePosixPath, filename: str) -> ScopedIgnore | None:
        relative = (base / filename).as_posix() if base.parts else filename
        candidate = self.root.joinpath(*PurePosixPath(relative).parts)
        if not candidate.exists() or candidate.is_symlink() or not candidate.is_file():
            return None
        try:
            content = bounded_read(
                self.root,
                relative,
                max_bytes=min(self.max_file_bytes, 256_000),
            ).data.decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None
        return ScopedIgnore.from_text(base, content)

    def scan(self) -> ScanBatch:
        files: list[ScannedFile] = []
        exclusions: list[ScanExclusion] = []
        seen_files = 0

        def walk(directory: Path, base: PurePosixPath, inherited: list[ScopedIgnore]) -> None:
            nonlocal seen_files
            local_rules = list(inherited)
            for filename in (".gitignore", ".contextloomignore"):
                rule = self._load_ignore(base, filename)
                if rule is not None:
                    local_rules.append(rule)
            try:
                entries = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
            except OSError:
                exclusions.append(
                    ScanExclusion(base.as_posix() or ".", "directory_unreadable", True)
                )
                return
            for entry in entries:
                relative = base / entry.name if base.parts else PurePosixPath(entry.name)
                relative_text = relative.as_posix()
                try:
                    is_link = entry.is_symlink()
                except OSError:
                    is_link = True
                if is_link:
                    exclusions.append(ScanExclusion(relative_text, "symlink"))
                    continue
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                except OSError:
                    exclusions.append(ScanExclusion(relative_text, "stat_failed", True))
                    continue
                hard_reason = hard_deny_reason(relative_text, is_directory=is_directory)
                if hard_reason is not None:
                    exclusions.append(ScanExclusion(relative_text, hard_reason))
                    continue
                if ignored_by_rules(relative, local_rules, is_directory=is_directory):
                    exclusions.append(ScanExclusion(relative_text, "ignored"))
                    continue
                if is_directory:
                    walk(Path(entry.path), relative, local_rules)
                    continue
                try:
                    is_file = entry.is_file(follow_symlinks=False)
                except OSError:
                    is_file = False
                if not is_file:
                    exclusions.append(ScanExclusion(relative_text, "not_regular_file"))
                    continue
                seen_files += 1
                if seen_files > self.max_files:
                    exclusions.append(ScanExclusion(relative_text, "workspace_file_limit", True))
                    continue
                try:
                    raw = bounded_read(
                        self.root,
                        relative_text,
                        max_bytes=self.max_file_bytes,
                        retries=1,
                    )
                except FileTooLargeError:
                    exclusions.append(ScanExclusion(relative_text, "file_too_large"))
                    continue
                except FileChangedError:
                    exclusions.append(ScanExclusion(relative_text, "changed_during_read", True))
                    continue
                except OSError:
                    exclusions.append(ScanExclusion(relative_text, "read_failed", True))
                    continue
                decoded = _decode_text(raw.data)
                if decoded is None:
                    exclusions.append(ScanExclusion(relative_text, "binary_or_unsupported_text"))
                    continue
                redacted = redact_secrets(decoded)
                digest = hashlib.sha256(redacted.text.encode("utf-8")).hexdigest()
                files.append(
                    ScannedFile(
                        relative_path=relative_text,
                        content=redacted.text,
                        sha256=digest,
                        size_bytes=len(redacted.text.encode("utf-8")),
                        mtime_ns=raw.mtime_ns,
                        inode=raw.inode,
                        device=raw.device,
                        redacted_count=redacted.count,
                        redaction_reasons=redacted.reasons,
                    )
                )

        walk(self.root, PurePosixPath(), [])
        return ScanBatch(
            files=tuple(sorted(files, key=lambda item: item.relative_path)),
            exclusions=tuple(
                sorted(exclusions, key=lambda item: (item.relative_path, item.reason))
            ),
        )


def scan_workspace(
    root: Path | str,
    *,
    max_file_bytes: int = 2_000_000,
    max_files: int = 50_000,
) -> list[ScannedFile]:
    """Convenience API returning only eligible files for small integrations/tests."""

    return list(
        WorkspaceScanner(root, max_file_bytes=max_file_bytes, max_files=max_files).scan().files
    )
