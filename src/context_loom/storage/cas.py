"""Private, atomic content-addressed storage for sanitized source objects."""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from pathlib import Path


class InvalidDigest(ValueError):
    """Raised when an object address is not a canonical SHA-256 digest."""


class CorruptObject(OSError):
    """Raised when stored bytes no longer match their address."""


class ContentAddressedStore:
    """Store immutable sanitized bytes under their SHA-256 digest."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            os.chmod(self.root, 0o700)

    @staticmethod
    def _validate_digest(digest: str) -> None:
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise InvalidDigest("object address must be a lowercase SHA-256 digest")

    def object_path(self, digest: str) -> Path:
        """Resolve a validated digest beneath the store root."""

        self._validate_digest(digest)
        shard = self.root / digest[:2]
        if shard.is_symlink() or (shard.exists() and not shard.is_dir()):
            raise CorruptObject("content-addressed shard is not a private directory")
        target = shard / digest[2:]
        if target.is_symlink():
            raise CorruptObject("content-addressed object must not be a symlink")
        return target

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def put(self, content: bytes | str) -> str:
        """Atomically persist bytes and return their canonical digest."""

        data = content.encode("utf-8") if isinstance(content, str) else content
        digest = hashlib.sha256(data).hexdigest()
        target = self.object_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if stat.S_IMODE(target.parent.stat().st_mode) & 0o077:
            os.chmod(target.parent, 0o700)
        if target.exists():
            os.chmod(target, 0o600)
            self._verify(target, digest)
            return digest

        staging = target.parent / f".{digest}.{secrets.token_hex(8)}.tmp"
        descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            try:
                view = memoryview(data)
                while view:
                    written = os.write(descriptor, view)
                    view = view[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                os.link(staging, target)
            except FileExistsError:
                self._verify(target, digest)
            os.chmod(target, 0o600)
            self._fsync_directory(target.parent)
        finally:
            staging.unlink(missing_ok=True)
        return digest

    def _verify(self, path: Path, digest: str) -> None:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != digest:
            raise CorruptObject(f"content-addressed object failed integrity check: {digest}")

    def get(self, digest: str) -> bytes:
        """Read and integrity-check one object without accepting path fragments."""

        path = self.object_path(digest)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            blocks: list[bytes] = []
            while block := os.read(descriptor, 65_536):
                blocks.append(block)
            data = b"".join(blocks)
        finally:
            os.close(descriptor)
        if hashlib.sha256(data).hexdigest() != digest:
            raise CorruptObject(f"content-addressed object failed integrity check: {digest}")
        return data

    def get_text(self, digest: str) -> str:
        """Read one UTF-8 object."""

        return self.get(digest).decode("utf-8")

    def contains(self, digest: str) -> bool:
        """Return whether a validated object address exists."""

        path = self.object_path(digest)
        return path.exists() and path.is_file() and not path.is_symlink()
