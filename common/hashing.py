"""File hashing and stable document identifiers.

File hashes are stored so reports can identify the exact source version used.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: str | Path) -> str:
    """Compute the SHA-256 digest of a file, streaming in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(namespace: str, *parts) -> str:
    """Short stable identifier derived from namespace + parts (e.g. doc ids)."""
    payload = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(f"{namespace}:{payload}".encode("utf-8")).hexdigest()
    return f"{namespace}-{digest[:12]}"


def file_size(path: str | Path) -> int:
    return Path(path).stat().st_size
