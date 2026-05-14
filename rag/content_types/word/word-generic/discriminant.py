from __future__ import annotations

import json
from pathlib import Path

import yaml

CONTENT_KIND = "word-generic"
PRIORITY = 1


def _load_mydata_dir(settings_path: Path = Path("config/app_settings.json")) -> str:
    try:
        cfg = json.loads(settings_path.read_text(encoding="utf-8"))
        return str(cfg.get("mydata_dir", "")).strip().strip("/").lower()
    except Exception:
        return ""


def _load_allowed_suffixes(discriminant_path: Path) -> list[str]:
    """
    Load content_type.yaml located alongside this discriminant file and return
    a list of allowed suffixes in lower case (including the leading dot).
    Raises on error or if no suffixes are defined.
    """
    ct_path = discriminant_path.with_name("content_type.yaml")
    raw = ct_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw) or {}
    suffixes = doc.get("detect", {}).get("suffixes")
    if not isinstance(suffixes, list) or not suffixes:
        raise ValueError(
            "content_type.yaml must define detect.suffixes as a non-empty list"
        )
    cleaned: list[str] = []
    for s in suffixes:
        if not isinstance(s, str):
            continue
        s2 = s.strip().lower()
        if not s2:
            continue
        if not s2.startswith("."):
            s2 = "." + s2
        cleaned.append(s2)
    if not cleaned:
        raise ValueError("No valid suffixes found in content_type.yaml")
    return cleaned


def matches(path: Path, data: object = None) -> bool:
    """
    Strict: the file's suffix must exactly match one of the suffixes listed in
    content_type.yaml (no fallback). File must not be under /ai-taskvector/
    unless it's inside the configured mydata_dir from config/app_settings.json.
    """
    p = path.as_posix().lower()

    # load allowed suffixes from content_type.yaml located next to this file
    allowed_suffixes = _load_allowed_suffixes(Path(__file__))

    if path.suffix.lower() not in allowed_suffixes:
        return False

    mydata_dir = _load_mydata_dir()
    allowed_fragment = f"/{mydata_dir}/" if mydata_dir else ""

    if "/ai-taskvector/" in p:
        if allowed_fragment and allowed_fragment in p:
            return True
        return False

    return True
