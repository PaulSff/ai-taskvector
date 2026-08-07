from __future__ import annotations

from pathlib import Path
from threading import Lock

# Shared in-process locks keyed by resolved persist_dir
_CHROMA_LOCKS: dict[str, Lock] = {}
_GUARD = Lock()


def _persist_key(persist_dir: str | Path) -> str:
    return str(Path(persist_dir).expanduser().resolve())


def get_chroma_write_lock(persist_dir: str | Path) -> Lock:
    """
    A simple mutex (write lock) per persist_dir.

    Use this for both:
    - indexing mutations (add/upsert/delete/rebuild)
    - read queries if you don't implement a true RW-lock
    """
    key = _persist_key(persist_dir)
    with _GUARD:
        lock = _CHROMA_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _CHROMA_LOCKS[key] = lock
        return lock
