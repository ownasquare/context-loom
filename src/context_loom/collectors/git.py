"""Read-only Git identity metadata without invoking Git or repository hooks."""

from __future__ import annotations

import json
import re
from pathlib import Path

from context_loom.collectors.base import VirtualResource
from context_loom.indexing.scanner import bounded_read

_REF = re.compile(r"refs/(?:heads|tags)/[A-Za-z0-9._/-]{1,240}\Z")
_OBJECT_ID = re.compile(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?\Z")


def _read_text(root: Path, relative_path: str, max_bytes: int = 256_000) -> str | None:
    try:
        return bounded_read(root, relative_path, max_bytes=max_bytes).data.decode("ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None


def collect_git_metadata(root: Path | str) -> VirtualResource | None:
    """Collect branch/ref/object-id only; never run Git, filters, or hooks."""

    root_path = Path(root).expanduser().resolve(strict=True)
    git_path = root_path / ".git"
    if git_path.is_symlink() or not git_path.is_dir():
        return None
    head = _read_text(root_path, ".git/HEAD", 512)
    if head is None:
        return None
    metadata: dict[str, str | bool] = {"repository_present": True}
    if head.startswith("ref: "):
        ref = head[5:].strip()
        if _REF.fullmatch(ref):
            metadata["ref"] = ref
            metadata["branch"] = ref.rsplit("/", 1)[-1]
            object_id = _read_text(root_path, f".git/{ref}", 128)
            if object_id is not None and _OBJECT_ID.fullmatch(object_id):
                metadata["object_id"] = object_id.casefold()
    elif _OBJECT_ID.fullmatch(head):
        metadata["detached"] = True
        metadata["object_id"] = head.casefold()
    return VirtualResource(
        relative_path=".context-loom/metadata/git.json",
        content=json.dumps(metadata, sort_keys=True, indent=2) + "\n",
        kind="configuration",
        origin="git_metadata",
    )
