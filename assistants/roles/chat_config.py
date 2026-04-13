"""Optional ``chat:`` block in ``role.yaml`` (Flet assistants panel)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _coerce_features(raw: Any) -> dict[str, bool]:
    if raw is None or not isinstance(raw, dict):
        return {}
    out: dict[str, bool] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        if isinstance(v, bool):
            out[key] = v
        elif isinstance(v, (int, float)):
            out[key] = bool(v)
        elif isinstance(v, str):
            out[key] = v.strip().lower() in ("1", "true", "yes", "y")
    return out


def role_chat_feature_enabled(chat: RoleChatConfig | None, key: str, *, default: bool = True) -> bool:
    """
    Read a boolean from ``chat.features[key]``.

    If ``chat`` is None, ``features`` is empty, or ``key`` is absent, returns ``default``.
    """
    if chat is None or not chat.features:
        return default
    if key not in chat.features:
        return default
    return bool(chat.features[key])


@dataclass(frozen=True)
class RoleChatConfig:
    """
    Declarative wiring for the main assistants chat (see ``gui/chat_with_the_assistants``).

    ``workflow`` is a filename under ``assistants/roles/<role_id>/`` (e.g. ``assistant_workflow.json``).

    ``chat_handler`` is an optional ``module.path:ClassName`` (or ``module.path.ClassName``) for a
    ``RoleChatHandler`` loaded on demand by the Flet registry (see plan Phase D).
    """

    enabled: bool = True
    workflow: str | None = None
    features: dict[str, bool] = field(default_factory=dict)
    chat_handler: str | None = None


def parse_role_chat_config(raw: Any) -> RoleChatConfig | None:
    """Parse ``chat:`` from role YAML; return None if key absent."""
    if raw is None:
        return None
    if raw is True:
        return RoleChatConfig(enabled=True)
    if raw is False:
        return RoleChatConfig(enabled=False)
    if not isinstance(raw, dict):
        return RoleChatConfig()
    en = raw.get("enabled")
    if en is False or (isinstance(en, str) and en.strip().lower() in ("0", "false", "no")):
        enabled = False
    elif en is None or en == "":
        enabled = True
    else:
        enabled = bool(en)
    wf = raw.get("workflow") or raw.get("chat_workflow")
    workflow = str(wf).strip() if isinstance(wf, str) and str(wf).strip() else None
    features = _coerce_features(raw.get("features"))
    h = raw.get("chat_handler") or raw.get("handler")
    chat_handler = str(h).strip() if isinstance(h, str) and str(h).strip() else None
    return RoleChatConfig(enabled=enabled, workflow=workflow, features=features, chat_handler=chat_handler)
