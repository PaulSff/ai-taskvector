"""
PayloadTransform unit: map ``data`` → ``parser_output`` dict for downstream units (e.g. RunWorkflow).

Uses the same **route / rule** vocabulary as ``Router`` (``all`` / ``any`` / ``default``). Each route
provides a ``parser_output`` template (mapping). String leaves may contain ``{field}`` placeholders
(dot paths into ``data``, same as Router rules).

First matching non-default route wins; then a route with ``default: true``; else emits ``{}``.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from units.canonical.router.router import _get_field, _match_all, _match_any
from units.registry import UnitSpec, register_unit

_PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_.]+)\}")

PAYLOAD_TRANSFORM_INPUT_PORTS = [("data", "Any")]
PAYLOAD_TRANSFORM_OUTPUT_PORTS = [("parser_output", "Any")]


def _substitute(obj: Any, data: Any) -> Any:
    """Deep-copy ``obj`` and replace ``{field}`` in strings using ``_get_field(data, field)``."""

    def _sub_str(s: str) -> str:
        def repl(m: re.Match[str]) -> str:
            v = _get_field(data, m.group(1))
            if v is None:
                return ""
            if isinstance(v, (dict, list)):
                try:
                    return json.dumps(v)
                except (TypeError, ValueError):
                    return str(v)
            return str(v)

        return _PLACEHOLDER.sub(repl, s)

    if isinstance(obj, str):
        return _sub_str(obj)
    if isinstance(obj, dict):
        return {k: _substitute(v, data) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v, data) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_substitute(v, data) for v in obj)
    return obj


def _repeat_for_each_payload(
    data: Any,
    spec: dict[str, Any],
) -> dict[str, Any] | None:
    """
    If ``spec`` defines ``field`` + ``item_template``, build ``{output_key: [substituted item, ...]}``
    by merging each list element into a copy of ``data`` under ``merge_key`` (for ``{merge_key}`` placeholders).
    ``data`` must be a dict. Returns None if repeat mode is not active or misconfigured.
    """
    if not isinstance(spec, dict):
        return None
    field = str(spec.get("field") or "").strip()
    item_template = spec.get("item_template")
    if not field or item_template is None:
        return None
    if not isinstance(data, dict):
        return None
    merge_key = str(spec.get("merge_key") or "path").strip() or "path"
    output_key = str(spec.get("output_key") or "actions").strip() or "actions"
    raw_list = _get_field(data, field)
    if not isinstance(raw_list, list):
        raw_list = []
    built: list[Any] = []
    for el in raw_list:
        row = dict(data)
        row[merge_key] = el
        built.append(_substitute(copy.deepcopy(item_template), row))
    return {output_key: built}


def _payload_transform_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = inputs.get("data")
    if data is None:
        return {"parser_output": {}}, state

    repeated = _repeat_for_each_payload(data, params.get("repeat_for_each") or {})
    if repeated is not None:
        return {"parser_output": repeated}, state

    routes = params.get("routes")
    if not isinstance(routes, list):
        routes = []

    default_template: Any | None = None
    ordered: list[dict[str, Any]] = []
    for raw in routes:
        if not isinstance(raw, dict):
            continue
        if raw.get("default") is True:
            if "parser_output" in raw and default_template is None:
                default_template = raw.get("parser_output")
            continue
        ordered.append(raw)

    chosen: Any | None = None
    for raw in ordered:
        all_rules = raw.get("all")
        any_rules = raw.get("any")
        ok = False
        if isinstance(all_rules, list) and all_rules:
            ok = _match_all(data, all_rules)
        elif isinstance(any_rules, list) and any_rules:
            ok = _match_any(data, any_rules)
        if not ok:
            continue
        if "parser_output" not in raw:
            continue
        chosen = raw.get("parser_output")
        break

    if chosen is None and default_template is not None:
        chosen = default_template

    if chosen is None:
        out: dict[str, Any] = {}
    elif isinstance(chosen, dict):
        out = _substitute(copy.deepcopy(chosen), data)
    else:
        out = _substitute(copy.deepcopy(chosen), data) if chosen is not None else {}

    if not isinstance(out, dict):
        out = {"_transformed": out}

    return {"parser_output": out}, state


def register_payload_transform() -> None:
    register_unit(
        UnitSpec(
            type_name="PayloadTransform",
            input_ports=PAYLOAD_TRANSFORM_INPUT_PORTS,
            output_ports=PAYLOAD_TRANSFORM_OUTPUT_PORTS,
            step_fn=_payload_transform_step,
            description=(
                "Build ``parser_output`` from ``data`` using ``params.routes`` (rules + templates); "
                "supports ``{field}`` substitution. Optional ``params.repeat_for_each`` "
                "(field, merge_key, output_key, item_template) expands ``item_template`` once per list element "
                "from ``data[field]`` (shallow merge of each element into ``data`` under ``merge_key``); "
                "when set, repeat mode runs instead of ``routes``."
            ),
        )
    )


__all__ = [
    "PAYLOAD_TRANSFORM_INPUT_PORTS",
    "PAYLOAD_TRANSFORM_OUTPUT_PORTS",
    "register_payload_transform",
]
