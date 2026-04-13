"""
Discover assistant roles that expose LLM settings in ``role.yaml``.

Used by the Settings tab to render per-role LLM blocks without hard-coding role ids.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# gui/utils/role_settings_discovery.py -> gui -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROLES_ROOT = _REPO_ROOT / "assistants" / "roles"


@dataclass(frozen=True)
class RoleLlmUiEntry:
    """One role that should get an LLM provider / Ollama subsection in Settings."""

    role_id: str
    display_name: str


def _role_yaml_path(roles_root: Path, role_id: str) -> Path:
    return roles_root / role_id / "role.yaml"


def _load_role_doc(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return raw if isinstance(raw, dict) else None


def _include_role_for_llm_ui(doc: dict[str, Any]) -> bool:
    """True if this role should show the standard LLM fields in Settings."""
    settings = doc.get("settings")
    if isinstance(settings, dict) and settings.get("show_llm_ui") is False:
        return False
    llm = doc.get("llm")
    return isinstance(llm, dict) and bool(llm)


def discover_role_llm_ui_entries(*, roles_root: Path | None = None) -> tuple[RoleLlmUiEntry, ...]:
    """
    Scan ``assistants/roles/*/role.yaml`` and return roles that declare an ``llm:`` block.

    Ordering: ``CHAT_MAIN_ASSISTANT_ROLE_IDS`` first (when present), then remaining ids sorted.
    Roles may set ``settings.show_llm_ui: false`` to opt out while keeping ``llm`` for runtime.
    """
    root = roles_root or _DEFAULT_ROLES_ROOT
    if not root.is_dir():
        return ()

    try:
        from assistants.roles.registry import CHAT_MAIN_ASSISTANT_ROLE_IDS
    except Exception:
        CHAT_MAIN_ASSISTANT_ROLE_IDS = ()

    candidates: list[str] = []
    try:
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            rid = p.name
            doc = _load_role_doc(_role_yaml_path(root, rid))
            if doc is None or not _include_role_for_llm_ui(doc):
                continue
            yaml_id = str(doc.get("id") or rid).strip()
            if yaml_id != rid:
                continue
            candidates.append(rid)
    except OSError:
        return ()

    order_map = {rid: i for i, rid in enumerate(CHAT_MAIN_ASSISTANT_ROLE_IDS)}
    main = [rid for rid in CHAT_MAIN_ASSISTANT_ROLE_IDS if rid in candidates]
    rest = sorted(rid for rid in candidates if rid not in order_map)
    ordered = main + rest

    out: list[RoleLlmUiEntry] = []
    for rid in ordered:
        doc = _load_role_doc(_role_yaml_path(root, rid)) or {}
        name = str(doc.get("display_name") or rid).strip() or rid
        out.append(RoleLlmUiEntry(role_id=rid, display_name=name))
    return tuple(out)


__all__ = [
    "RoleLlmUiEntry",
    "discover_role_llm_ui_entries",
]
