from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def slugify_filename(text: str, *, max_len: int = 64) -> str:
    """Convert text to a safe snake_case-ish filename base (no extension)."""
    t = (text or "").strip().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    if not t:
        t = "chat"
    return t[:max_len].strip("_") or "chat"


def unique_path(dir_path: Path, base: str) -> Path:
    """Return a unique path under dir_path for base.json (adds _2, _3...)."""
    p = dir_path / f"{base}.json"
    if not p.exists():
        return p
    i = 2
    while True:
        cand = dir_path / f"{base}_{i}.json"
        if not cand.exists():
            return cand
        i += 1


def list_recent_chat_files(chat_history_dir: Path, *, limit: int = 30) -> list[Path]:
    """List most recently modified chat JSON files."""
    try:
        files = [p for p in chat_history_dir.iterdir() if p.is_file() and p.suffix.lower() == ".json"]
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def load_chat_payload(path: Path) -> dict[str, Any] | None:
    """Load chat payload JSON from path."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_chat_payload(path: Path, payload: dict[str, Any]) -> bool:
    """Write chat payload JSON to path. Returns success."""
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False

