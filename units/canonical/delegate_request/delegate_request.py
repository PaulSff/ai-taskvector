"""
delegate_request unit: normalize LLM ``delegate_request`` actions for chat handoff.

Input: optional inject ``action`` dict and/or ``parser_output`` (ProcessAgent) with side-channel
``delegate_request``. Expected payload::

  {"action": "delegate_request", "delegate_to": "<role_id or role_name>", "message": "..."}

``message`` is optional (GUI uses the current user message when omitted).
"""
from __future__ import annotations

from typing import Any, Tuple

from units.registry import UnitSpec, register_unit

DELEGATE_REQUEST_INPUT_PORTS = [
    ("action", "Any"),
    ("parser_output", "Any"),
]
DELEGATE_REQUEST_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _resolve_delegate_to(raw: str) -> Tuple[str | None, str]:
    """Map ``delegate_to`` string to ``role_id`` (snake_case folder id) or return (None, error)."""
    s = (raw or "").strip()
    if not s:
        return None, "delegate_to is required"
    key = s.lower()
    try:
        from assistants.roles import get_role, list_chat_dropdown_role_ids

        allowed = frozenset(list_chat_dropdown_role_ids())
        if not allowed:
            return None, "no chat assistants configured"
        for rid in allowed:
            if rid.lower() == key:
                return rid, ""
        for rid in allowed:
            try:
                rn = (get_role(rid).role_name or "").strip().lower()
                if rn and rn == key:
                    return rid, ""
            except Exception:
                continue
        return None, f"unknown delegate_to: {raw!r} (use role id or role name from the chat list)"
    except Exception as e:
        return None, f"resolve delegate_to: {e}"[:200]


def delegate_handoff_data_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a ``delegate_request`` action dict to the same ``data`` shape the unit emits on its ``data`` port
    (``ok``, ``delegate_to``, ``message``, ``error``). Used by the delegate_request unit and RL Coach training apply.
    """
    if not isinstance(payload, dict) or not payload:
        return {"ok": False, "delegate_to": None, "message": None, "error": ""}

    if payload.get("action") != "delegate_request":
        return {
            "ok": False,
            "delegate_to": None,
            "message": None,
            "error": f"unsupported action: {payload.get('action')!r}",
        }

    raw_to = payload.get("delegate_to")
    if not isinstance(raw_to, str):
        raw_to = str(raw_to).strip() if raw_to is not None else ""
    role_id, err = _resolve_delegate_to(raw_to)
    if err or not role_id:
        return {
            "ok": False,
            "delegate_to": None,
            "message": None,
            "error": err or "invalid delegate_to",
        }

    msg_raw = payload.get("message")
    if msg_raw is None or (isinstance(msg_raw, str) and not msg_raw.strip()):
        message_out = None
    else:
        message_out = str(msg_raw).strip()

    return {
        "ok": True,
        "delegate_to": role_id,
        "message": message_out,
        "error": "",
    }


def _delegate_request_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload: dict[str, Any] | None = None
    parser_output = inputs.get("parser_output") if inputs else None
    if isinstance(parser_output, dict):
        dr = parser_output.get("delegate_request")
        if isinstance(dr, dict):
            payload = dr
    if payload is None:
        act = inputs.get("action") if inputs else None
        if isinstance(act, dict) and act.get("action") == "delegate_request":
            payload = act
    if not payload:
        return (
            {
                "data": {"ok": False, "delegate_to": None, "message": None, "error": ""},
                "error": "",
            },
            state,
        )

    data = delegate_handoff_data_from_payload(payload)
    return ({"data": data, "error": ""}, state)


def register_delegate_request() -> None:
    register_unit(
        UnitSpec(
            type_name="delegate_request",
            input_ports=DELEGATE_REQUEST_INPUT_PORTS,
            output_ports=DELEGATE_REQUEST_OUTPUT_PORTS,
            step_fn=_delegate_request_step,
            environment_tags=["canonical"],
            environment_tags_are_agnostic=True,
            runtime_scope=None,
            description="Chat delegation: parse delegate_request action; output resolved role id and optional message for GUI handoff.",
        )
    )


__all__ = [
    "DELEGATE_REQUEST_INPUT_PORTS",
    "DELEGATE_REQUEST_OUTPUT_PORTS",
    "delegate_handoff_data_from_payload",
    "register_delegate_request",
]
