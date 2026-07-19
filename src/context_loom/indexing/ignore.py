"""Git-compatible ignore evaluation with immutable security exclusions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from pathspec import GitIgnoreSpec

HARD_DENIED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".context-loom",
        ".aws",
        ".gnupg",
        ".kube",
        ".ssh",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "target",
        "coverage",
        ".next",
        ".nuxt",
        ".cache",
        ".gradle",
        ".parcel-cache",
        ".pnpm-store",
        ".serverless",
        ".terraform",
        ".turbo",
        ".yarn",
        "bower_components",
        "pods",
        "site-packages",
    }
)

_SECRET_FILENAMES = frozenset(
    {
        ".env",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "service-account.json",
        "service_account.json",
        ".npmrc",
        ".pypirc",
        ".netrc",
    }
)
_SECRET_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".kdbx",
    ".tfvars",
    ".tfstate",
    ".tfstate.backup",
)


@dataclass(frozen=True, slots=True)
class ScopedIgnore:
    """One ignore file interpreted relative to its containing directory."""

    base: PurePosixPath
    spec: GitIgnoreSpec

    @classmethod
    def from_text(cls, base: PurePosixPath, text: str) -> ScopedIgnore:
        return cls(base=base, spec=GitIgnoreSpec.from_lines(text.splitlines()))

    def decision(self, path: PurePosixPath, *, is_directory: bool = False) -> bool | None:
        if self.base.parts and path.parts[: len(self.base.parts)] != self.base.parts:
            return None
        relative = PurePosixPath(*path.parts[len(self.base.parts) :])
        if not relative.parts:
            return None
        candidate = relative.as_posix() + ("/" if is_directory else "")
        return self.spec.check_file(candidate).include


def hard_deny_reason(relative_path: str, *, is_directory: bool = False) -> str | None:
    """Return an immutable exclusion reason, regardless of ignore negation."""

    path = PurePosixPath(relative_path)
    lowered_parts = tuple(part.casefold() for part in path.parts)
    if any(part in HARD_DENIED_DIRECTORIES for part in lowered_parts):
        return "hard_denied_directory"
    name = path.name.casefold()
    if name in _SECRET_FILENAMES or name.startswith(".env"):
        return "secret_file"
    secret_stem = name.rsplit(".", 1)[0]
    secret_prefixes = ("credentials.", "secrets.", "service-account.", "service_account.")
    if secret_stem in {
        "credentials",
        "secrets",
        "service-account",
        "service_account",
    } or name.startswith(secret_prefixes):
        return "secret_file"
    if name.endswith(_SECRET_SUFFIXES):
        return "private_key_or_keystore"
    if name.endswith((".sqlite", ".sqlite3", ".db", ".db-wal", ".db-shm")):
        return "local_database"
    if is_directory and name in HARD_DENIED_DIRECTORIES:
        return "hard_denied_directory"
    return None


def ignored_by_rules(
    path: PurePosixPath,
    rules: list[ScopedIgnore],
    *,
    is_directory: bool = False,
) -> bool:
    """Apply parent-to-child rule files, preserving last-match negation semantics."""

    ignored = False
    for rule in rules:
        decision = rule.decision(path, is_directory=is_directory)
        if decision is not None:
            ignored = decision
    return ignored
