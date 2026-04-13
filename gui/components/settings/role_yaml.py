"""Patch ``assistants/roles/<id>/role.yaml`` (llm block and top-level keys)."""
from __future__ import annotations

from typing import Any

import yaml

from .paths import _ROLES_YAML_ROOT


def _patch_role_llm(role_id: str, patch: dict[str, Any]) -> None:
    """Merge ``patch`` into ``assistants/roles/<role_id>/role.yaml`` under ``llm:`` and clear role cache."""
    rid = (role_id or "").strip()
    if not rid or not patch:
        return
    path = _ROLES_YAML_ROOT / rid / "role.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"role.yaml not found: {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        doc = {}
    llm = doc.get("llm")
    if not isinstance(llm, dict):
        llm = {}
    llm.update(patch)
    doc["llm"] = llm
    path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    try:
        from assistants.roles.registry import clear_role_cache

        clear_role_cache()
    except Exception:
        pass


def _patch_role_document(role_id: str, patch: dict[str, Any]) -> None:
    """Merge top-level keys into ``assistants/roles/<role_id>/role.yaml`` (e.g. ``follow_up_max_rounds``)."""
    rid = (role_id or "").strip()
    if not rid or not patch:
        return
    path = _ROLES_YAML_ROOT / rid / "role.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"role.yaml not found: {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        doc = {}
    doc.update(patch)
    path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    try:
        from assistants.roles.registry import clear_role_cache

        clear_role_cache()
    except Exception:
        pass


def _role_llm_str(role_id: str, key: str, *, default: str) -> str:
    """Read ``llm.<key>`` from ``assistants/roles/<role_id>/role.yaml`` via param ref."""
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref(f"role.{role_id}.llm.{key}")
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw.strip() or default
    return str(raw)


def _role_llm_float(role_id: str, key: str, *, default: float) -> float:
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref(f"role.{role_id}.llm.{key}")
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _role_llm_int(role_id: str, key: str, *, default: int) -> int:
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref(f"role.{role_id}.llm.{key}")
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default
