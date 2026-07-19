from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from context_loom.storage.cas import (
    ContentAddressedStore,
    CorruptObject,
    InvalidDigest,
)


def test_cas_writes_private_atomic_deduplicated_objects(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "objects")
    content = b"sanitized context\n"

    with ThreadPoolExecutor(max_workers=4) as pool:
        digests = list(pool.map(store.put, [content] * 8))

    assert len(set(digests)) == 1
    digest = digests[0]
    assert store.get(digest) == content
    assert store.get_text(digest) == "sanitized context\n"
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.object_path(digest).stat().st_mode) == 0o600
    assert not list(store.root.rglob("*.tmp"))


@pytest.mark.parametrize("digest", ["../escape", "A" * 64, "a" * 63, "g" * 64])
def test_cas_rejects_noncanonical_addresses(tmp_path: Path, digest: str) -> None:
    store = ContentAddressedStore(tmp_path / "objects")
    with pytest.raises(InvalidDigest):
        store.get(digest)


def test_cas_detects_corruption_and_symlink_shards(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path / "objects")
    digest = store.put(b"original")
    store.object_path(digest).write_bytes(b"changed")
    with pytest.raises(CorruptObject):
        store.get(digest)

    other = tmp_path / "outside"
    other.mkdir()
    shard = store.root / "ff"
    os.symlink(other, shard)
    with pytest.raises(CorruptObject):
        store.object_path("f" * 64)
