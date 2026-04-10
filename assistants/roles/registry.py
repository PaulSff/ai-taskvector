"""Load and cache role definitions from assistants/roles/<id>/role.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from assistants.roles.types import RoleConfig

_ROLES_ROOT = Path(__file__).resolve().parent
_CACHE: dict[str, RoleConfig] = {}


def _coerce_tools(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, list):
        return tuple(str(x).strip() for x in raw if str(x).strip())
    return ()


def _load_yaml(role_id: str) -> dict[str, Any]:
    path = _ROLES_ROOT / role_id / "role.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Role file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"role.yaml for {role_id!r} must be a mapping")
    return data


def _build_config(role_id: str, data: dict[str, Any]) -> RoleConfig:
    rid = str(data.get("id") or role_id).strip()
    if rid != role_id:
        raise ValueError(f"role.yaml id {rid!r} does not match folder {role_id!r}")
    display = str(data.get("display_name") or role_id).strip()
    fur = data.get("follow_up_max_rounds")
    follow_up: int | None
    if fur is None or fur == "":
        follow_up = None
    else:
        follow_up = max(1, min(50, int(fur)))
    known = {"id", "display_name", "follow_up_max_rounds", "tools", "use_legacy_followups"}
    extra = {k: v for k, v in data.items() if k not in known}
    return RoleConfig(
        id=rid,
        display_name=display,
        follow_up_max_rounds=follow_up,
        tools=_coerce_tools(data.get("tools")),
        extra=extra,
    )


def get_role(role_id: str) -> RoleConfig:
    """
    Return cached RoleConfig for ``role_id`` (e.g. ``workflow_designer``, ``rl_coach``).
    """
    key = (role_id or "").strip()
    if not key:
        raise ValueError("role_id is required")
    if key in _CACHE:
        return _CACHE[key]
    cfg = _build_config(key, _load_yaml(key))
    _CACHE[key] = cfg
    return cfg


def clear_role_cache() -> None:
    """Tests only: reset cached roles after editing YAML."""
    _CACHE.clear()
