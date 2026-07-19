"""Fail closed on common public-release and secret-boundary mistakes."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REQUIRED_PATHS = {
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "docs/architecture.md",
    "docs/extending.md",
    "docs/fidelity-contract.md",
    "docs/getting-started.md",
    "docs/token-accounting.md",
    "docs/security.md",
    "docs/troubleshooting.md",
}
SKIP_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "test-results",
    "playwright-report",
}
FORBIDDEN_TRACKED_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json"}
FORBIDDEN_TRACKED_SUFFIXES = {".db", ".db-shm", ".db-wal", ".key", ".parquet", ".pem"}
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "provider_token": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}
ABSOLUTE_HOME = re.compile(r"(?:/" + "Users" + r"/[^/\s]+|[A-Za-z]:\\" + "Users" + r"\\[^\\\s]+)")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
LOCAL_ONLY_PREFIXES = ("docs/handoffs/", "docs/superpowers/plans/", "docs/context-loom/")


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--history",
        action="store_true",
        help="also inspect every historical text blob; use on the clean publication branch",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="require a clean tracked and untracked tree before auditing the release candidate",
    )
    parser.add_argument(
        "--revision",
        default="HEAD",
        help="git revision whose reachable history is inspected with --history (default: HEAD)",
    )
    return parser.parse_args()


def candidate_files(root: Path) -> list[Path]:
    public_candidates = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        capture_output=True,
        check=False,
    )
    if public_candidates.returncode == 0 and public_candidates.stdout:
        names = public_candidates.stdout.decode("utf-8", errors="replace").split("\0")
        candidates = [root / name for name in names if name]
        return [path for path in candidates if path.is_symlink() or path.is_file()]
    return sorted(
        path
        for path in root.rglob("*")
        if (path.is_symlink() or path.is_file())
        and not any(part in SKIP_PARTS for part in path.relative_to(root).parts)
    )


def inspect_path(root: Path, path: Path) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    if path.is_symlink():
        return [Finding("tracked_symlink", relative, "public files must not be symbolic links")]
    if path.name in FORBIDDEN_TRACKED_NAMES or (
        path.name.startswith(".env") and path.name != ".env.example"
    ):
        findings.append(
            Finding("forbidden_file", relative, "credential surface must not be public")
        )
    if any(relative.endswith(suffix) for suffix in FORBIDDEN_TRACKED_SUFFIXES):
        findings.append(
            Finding("forbidden_artifact", relative, "runtime/private artifact is tracked")
        )
    if path.stat().st_size > 5_000_000:
        findings.append(Finding("oversized_file", relative, "file exceeds 5 MB public boundary"))
        return findings
    content = path.read_bytes()
    if b"\0" in content[:8192]:
        return findings
    text = content.decode("utf-8", errors="replace")
    for code, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            findings.append(Finding(code, relative, "credential-like value detected"))
    if relative.startswith(LOCAL_ONLY_PREFIXES):
        findings.append(
            Finding("local_only_file", relative, "private continuity record is in public scope")
        )
    if ABSOLUTE_HOME.search(text):
        findings.append(Finding("machine_path", relative, "machine-local home path detected"))
    if path.suffix.lower() in {".md", ".mdc"}:
        for target in MARKDOWN_LINK.findall(text):
            clean = target.split("#", maxsplit=1)[0].strip().strip("<>")
            if clean and not (path.parent / clean).resolve().exists():
                findings.append(Finding("broken_link", relative, clean))
    return findings


def inspect_history(root: Path, revision: str) -> list[Finding]:
    """Inspect historical non-binary blobs without printing their contents."""

    resolved = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{revision}^{{commit}}",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    commit = resolved.stdout.strip()
    if resolved.returncode != 0 or re.fullmatch(r"[0-9a-fA-F]{40,64}", commit) is None:
        return [Finding("history_unavailable", ".git", "could not resolve git revision")]

    objects = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--objects", commit],
        capture_output=True,
        check=False,
        text=True,
    )
    if objects.returncode != 0:
        return [Finding("history_unavailable", ".git", "could not enumerate git history")]

    blobs: dict[str, set[str]] = {}
    for line in objects.stdout.splitlines():
        object_id, separator, relative = line.partition(" ")
        if not separator or not relative:
            continue
        blobs.setdefault(object_id, set()).add(relative)

    findings: list[Finding] = []
    process = subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        return [Finding("history_unavailable", ".git", "could not open git object reader")]

    try:
        for object_id, relatives in blobs.items():
            process.stdin.write(f"{object_id}\n".encode())
            process.stdin.flush()
            header = process.stdout.readline().decode("utf-8", errors="replace").strip()
            parts = header.split()
            if len(parts) != 3:
                continue
            try:
                size = int(parts[2])
            except ValueError:
                continue
            content = process.stdout.read(size)
            process.stdout.read(1)
            if parts[1] != "blob":
                continue
            for relative in sorted(relatives):
                path = Path(relative)
                if path.name in FORBIDDEN_TRACKED_NAMES or (
                    path.name.startswith(".env") and path.name != ".env.example"
                ):
                    findings.append(
                        Finding(
                            "history_forbidden_file",
                            relative,
                            f"credential surface exists in historical blob {object_id[:12]}",
                        )
                    )
                if any(relative.endswith(suffix) for suffix in FORBIDDEN_TRACKED_SUFFIXES):
                    findings.append(
                        Finding(
                            "history_forbidden_artifact",
                            relative,
                            f"runtime/private artifact exists in historical blob {object_id[:12]}",
                        )
                    )
                if relative.startswith(LOCAL_ONLY_PREFIXES):
                    findings.append(
                        Finding(
                            "history_local_only_file",
                            relative,
                            f"private continuity record exists in historical blob {object_id[:12]}",
                        )
                    )
            if size > 5_000_000:
                findings.append(
                    Finding(
                        "history_oversized_file",
                        sorted(relatives)[0],
                        f"historical blob {object_id[:12]} exceeds 5 MB",
                    )
                )
                continue
            if b"\0" in content[:8192]:
                continue
            text = content.decode("utf-8", errors="replace")
            relative = sorted(relatives)[0]
            if ABSOLUTE_HOME.search(text):
                findings.append(
                    Finding(
                        "history_machine_path",
                        relative,
                        f"machine-local path exists in historical blob {object_id[:12]}",
                    )
                )
            for code, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    findings.append(
                        Finding(
                            f"history_{code}",
                            relative,
                            f"credential-like value exists in historical blob {object_id[:12]}",
                        )
                    )
    finally:
        process.stdin.close()
        process.wait(timeout=10)
    return findings


def inspect_release_state(root: Path) -> list[Finding]:
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        return [Finding("release_state_unavailable", ".git", "could not read release state")]
    findings: list[Finding] = []
    if status.stdout:
        findings.append(
            Finding(
                "dirty_release_tree",
                ".git",
                "release mode requires every intended file to be committed and the tree clean",
            )
        )
    tree = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "-z", "HEAD"],
        capture_output=True,
        check=False,
    )
    if tree.returncode != 0:
        findings.append(
            Finding("release_state_unavailable", ".git", "could not read the HEAD release tree")
        )
        return findings
    tracked = {item for item in tree.stdout.decode("utf-8", errors="replace").split("\0") if item}
    findings.extend(
        Finding(
            "release_untracked_required",
            relative,
            "required public file is not committed in HEAD",
        )
        for relative in sorted(REQUIRED_PATHS - tracked)
    )
    return findings


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    findings = [
        Finding("missing_required", item, "required public file is missing")
        for item in sorted(REQUIRED_PATHS)
        if not (root / item).is_file()
    ]
    if args.release:
        findings.extend(inspect_release_state(root))
    files = candidate_files(root)
    for path in files:
        findings.extend(inspect_path(root, path))
    if args.history:
        findings.extend(inspect_history(root, args.revision))
    if findings:
        for item in findings:
            print(f"FAIL {item.code} {item.path}: {item.detail}")
        print(f"Public boundary failed with {len(findings)} finding(s).")
        return 1
    print(f"Public boundary passed for {len(files)} files; no secret values were printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
