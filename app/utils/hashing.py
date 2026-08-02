"""Content hashing helpers used for source provenance (SDS-002 §9.2)."""

import hashlib
from pathlib import Path

_CHUNK_SIZE = 65536


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
