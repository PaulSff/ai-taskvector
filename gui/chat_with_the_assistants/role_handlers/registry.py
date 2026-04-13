"""Map ``role_id`` to a ``RoleChatHandler`` instance for the assistants chat panel."""
from __future__ import annotations

import importlib
from typing import Any

from gui.chat_with_the_assistants.role_handlers.protocol import RoleChatHandler

_BUILTIN_HANDLERS: tuple[RoleChatHandler, ...] | None = None
_BY_ROLE_ID: dict[str, RoleChatHandler] | None = None


def _builtin_handlers() -> tuple[RoleChatHandler, ...]:
    """Lazily construct built-ins so ``turn_edits`` (and other helpers) can import without a WD import cycle."""
    global _BUILTIN_HANDLERS
    if _BUILTIN_HANDLERS is None:
        from gui.chat_with_the_assistants.role_handlers.rl_coach import RlCoachChatHandler
        from gui.chat_with_the_assistants.role_handlers.workflow_designer import WorkflowDesignerChatHandler

        _BUILTIN_HANDLERS = (WorkflowDesignerChatHandler(), RlCoachChatHandler())
    return _BUILTIN_HANDLERS


def _by_role_id() -> dict[str, RoleChatHandler]:
    global _BY_ROLE_ID
    if _BY_ROLE_ID is None:
        _BY_ROLE_ID = {h.role_id: h for h in _builtin_handlers()}
    return _BY_ROLE_ID

# Handlers loaded from ``role.yaml`` ``chat.chat_handler`` / ``chat.handler`` (see assistants.roles.chat_config).
_DYNAMIC_HANDLER_CACHE: dict[str, RoleChatHandler] = {}


def clear_dynamic_handler_cache() -> None:
    """Tests only: reset handlers loaded from YAML ``chat.handler``."""
    _DYNAMIC_HANDLER_CACHE.clear()


def _parse_chat_handler_spec(spec: str) -> tuple[str, str] | None:
    s = (spec or "").strip()
    if not s:
        return None
    if ":" in s:
        mod, _, cls = s.partition(":")
        mod, cls = mod.strip(), cls.strip()
    else:
        dot = s.rfind(".")
        if dot <= 0:
            return None
        mod, cls = s[:dot].strip(), s[dot + 1 :].strip()
    if not mod or not cls:
        return None
    return (mod, cls)


def _load_handler_from_yaml_spec(spec: str, *, expected_role_id: str) -> RoleChatHandler | None:
    parsed = _parse_chat_handler_spec(spec)
    if parsed is None:
        return None
    mod_name, cls_name = parsed
    try:
        mod = importlib.import_module(mod_name)
        cls: Any = getattr(mod, cls_name, None)
        if cls is None or not callable(cls):
            return None
        inst = cls()
        if not hasattr(inst, "run_turn") or not hasattr(inst, "role_id"):
            return None
        if getattr(inst, "role_id", None) != expected_role_id:
            return None
        return inst  # type: ignore[return-value]
    except Exception:
        return None


def get_role_chat_handler(role_id: str) -> RoleChatHandler | None:
    key = (role_id or "").strip()
    if not key:
        return None
    built_in = _by_role_id().get(key)
    if built_in is not None:
        return built_in
    if key in _DYNAMIC_HANDLER_CACHE:
        return _DYNAMIC_HANDLER_CACHE[key]
    from assistants.roles import get_role

    try:
        role = get_role(key)
    except Exception:
        return None
    spec = (role.chat.chat_handler if role.chat else None) or ""
    spec = str(spec).strip()
    if not spec:
        return None
    inst = _load_handler_from_yaml_spec(spec, expected_role_id=key)
    if inst is not None:
        _DYNAMIC_HANDLER_CACHE[key] = inst
    return inst
