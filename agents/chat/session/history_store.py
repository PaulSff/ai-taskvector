from __future__ import annotations

import json
import re
from pathlib import Path

from core.schemas.primitives import Data, is_data


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


def load_chat_payload(path: Path) -> Data | None:
    """Load chat payload JSON from path."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not is_data(payload):
        return None

    messages = payload.get("messages")
    if not isinstance(messages, list):
        messages = []
        payload["messages"] = messages

    for event in read_chat_message_deltas(path):
        if event.get("op") != "append":
            continue

        message = event.get("message")
        if is_data(message):
            messages.append(message)

    return payload


async def write_chat_payload(path: Path, payload: Data) -> bool:
    """Write chat payload JSON to path. Returns success."""
    try:
        _ = path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Compaction point: full snapshot now contains all messages.
        clear_chat_message_deltas(path)
        return True
    except OSError:
        return False


def _chat_delta_path(path: Path) -> Path:
    """Companion append-only delta log for chat JSON payload."""
    return path.with_suffix(".delta.jsonl")


async def append_chat_message_delta(path: Path, message: Data) -> bool:
    """Append one chat message delta record (JSONL)."""
    rec = {"op": "append", "message": message}
    try:
        with _chat_delta_path(path).open("a", encoding="utf-8") as f:
            _ = f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def read_chat_message_deltas(path: Path) -> list[Data]:
    """Read append-only message deltas (best effort)."""

    delta_path = _chat_delta_path(path)

    try:
        lines = delta_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    output: list[Data] = []

    for line in lines:
        text = line.strip()
        if not text:
            continue

        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue

        if is_data(obj):
            output.append(obj)

    return output


def clear_chat_message_deltas(path: Path) -> None:
    """Remove append-only delta log if present."""
    p = _chat_delta_path(path)
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass
