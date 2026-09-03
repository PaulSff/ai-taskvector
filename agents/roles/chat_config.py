"""Optional ``chat:`` block in ``role.yaml`` (Flet agents panel)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.schemas.primitives import WorkflowInputs


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


def role_chat_feature_enabled(
    chat: RoleChatConfig | None, key: str, *, default: bool = True
) -> bool:
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
    Declarative wiring for the main agents chat (see ``agents/chat``).

    ``workflow`` is a filename under ``agents/roles/<role_id>/`` (e.g. ``workflow_designer_workflow.json``).

    ``chat_handler`` is an optional ``module.path:ClassName`` (or ``module.path.ClassName``) for a
    ``RoleChatHandler`` loaded on demand by the Flet registry (see plan Phase D).
    """

    enabled: bool = True
    workflow: str | None = None
    overrides: WorkflowInputs | None = None
    features: dict[str, bool] = field(default_factory=dict)
    chat_handler: str | None = None
    analyst_mode: bool = False


def parse_role_chat_config(raw: Any) -> RoleChatConfig | None:
    """Parse the optional ``chat:`` block from role YAML."""

    if raw is None:
        return None

    if raw is True:
        return RoleChatConfig(enabled=True)

    if raw is False:
        return RoleChatConfig(enabled=False)

    if not isinstance(raw, dict):
        return RoleChatConfig()

    # enabled
    en = raw.get("enabled")

    if en is False or (
        isinstance(en, str)
        and en.strip().lower() in ("0", "false", "no")
    ):
        enabled = False
    elif en is None or en == "":
        enabled = True
    else:
        enabled = bool(en)

    # workflow
    wf = raw.get("workflow") or raw.get("chat_workflow")

    workflow = (
        wf.strip()
        if isinstance(wf, str) and wf.strip()
        else None
    )

    # overrides
    raw_overrides = raw.get("overrides")

    if raw_overrides is None:
        overrides = None
    elif isinstance(raw_overrides, dict):
        overrides = raw_overrides
    else:
        raise TypeError(
            "role.yaml field 'chat.overrides' must be a mapping or null"
        )

    # features
    features = _coerce_features(raw.get("features"))

    # optional chat handler
    h = raw.get("chat_handler") or raw.get("handler")

    chat_handler = (
        h.strip()
        if isinstance(h, str) and h.strip()
        else None
    )

    # analyst mode
    raw_analyst_mode = raw.get("analyst_mode")

    if isinstance(raw_analyst_mode, str):
        analyst_mode = raw_analyst_mode.strip().lower() in (
            "1",
            "true",
            "yes",
            "y",
        )
    elif isinstance(raw_analyst_mode, (bool, int, float)):
        analyst_mode = bool(raw_analyst_mode)
    else:
        analyst_mode = False

    return RoleChatConfig(
        enabled=enabled,
        workflow=workflow,
        overrides=overrides,
        features=features,
        chat_handler=chat_handler,
        analyst_mode=analyst_mode,
    )
