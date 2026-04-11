"""
Router unit: one ``data`` input, fan-out to at most one output port by declarative routes in ``params``.

First matching non-default route wins; then ``default`` if present; otherwise ``unmatched``.
The **same** payload object is emitted on the chosen port only (other ports are not set on outputs dict).

Typical use: branch ``read_file`` / path suffix (e.g. ``.xlsx``) before different downstream subgraphs.
"""
from __future__ import annotations

import re
from typing import Any

from units.registry import UnitSpec, register_unit

ROUTER_MAX_BRANCHES = 8

ROUTER_INPUT_PORTS = [("data", "Any")]
ROUTER_OUTPUT_PORTS: list[tuple[str, str]] = [
    *(("out_%d" % i, "Any") for i in range(ROUTER_MAX_BRANCHES)),
    ("default", "Any"),
    ("unmatched", "Any"),
]

_ALLOWED_PORTS = frozenset(p for p, _ in ROUTER_OUTPUT_PORTS)


def _get_field(data: Any, field: str) -> Any:
    """Walk ``field`` with dot segments on dicts; missing → None."""
    if not field:
        return data
    cur: Any = data
    for part in str(field).strip().split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _match_one_rule(value: Any, rule: dict[str, Any]) -> bool:
    if not isinstance(rule, dict):
        return False
    if rule.get("exists") is True:
        return value is not None
    if "equals" in rule:
        return value == rule.get("equals")
    if "equals_str" in rule:
        return str(value or "").strip() == str(rule.get("equals_str") or "").strip()
    if "ends_with" in rule:
        s = str(value or "")
        suf = str(rule.get("ends_with") or "")
        return s.lower().endswith(suf.lower()) if suf else False
    if "starts_with" in rule:
        s = str(value or "")
        pre = str(rule.get("starts_with") or "")
        return s.lower().startswith(pre.lower()) if pre else False
    if "contains" in rule:
        needle = str(rule.get("contains") or "")
        return needle.lower() in str(value or "").lower() if needle else False
    if "regex" in rule:
        pat = str(rule.get("regex") or "")
        if not pat:
            return False
        try:
            return re.search(pat, str(value or ""), flags=re.DOTALL) is not None
        except re.error:
            return False
    return False


def _rule_field_value(data: Any, rule: dict[str, Any]) -> Any:
    field = str(rule.get("field") or "").strip()
    if not field:
        return data
    return _get_field(data, field)


def _match_rule(data: Any, rule: dict[str, Any]) -> bool:
    return _match_one_rule(_rule_field_value(data, rule), rule)


def _match_all(data: Any, rules: list[Any]) -> bool:
    if not rules:
        return True
    for r in rules:
        if not isinstance(r, dict):
            return False
        if not _match_rule(data, r):
            return False
    return True


def _match_any(data: Any, rules: list[Any]) -> bool:
    if not rules:
        return False
    for r in rules:
        if isinstance(r, dict) and _match_rule(data, r):
            return True
    return False


def _router_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = inputs.get("data")
    routes = params.get("routes")
    if not isinstance(routes, list):
        routes = []

    default_port: str | None = None
    ordered: list[tuple[str, dict[str, Any]]] = []
    for raw in routes:
        if not isinstance(raw, dict):
            continue
        port = str(raw.get("port") or "").strip()
        if not port or port not in _ALLOWED_PORTS:
            continue
        if raw.get("default") is True:
            if default_port is None:
                default_port = port
            continue
        ordered.append((port, raw))

    chosen: str | None = None
    for port, raw in ordered:
        all_rules = raw.get("all")
        any_rules = raw.get("any")
        ok = True
        if isinstance(all_rules, list) and all_rules:
            ok = _match_all(data, all_rules)
        elif isinstance(any_rules, list) and any_rules:
            ok = _match_any(data, any_rules)
        else:
            # no conditions = never matches (avoid accidental always-on)
            ok = False
        if ok:
            chosen = port
            break

    if chosen is None and default_port is not None:
        chosen = default_port
    if chosen is None:
        chosen = "unmatched"

    return {chosen: data}, state


def register_router() -> None:
    register_unit(
        UnitSpec(
            type_name="Router",
            input_ports=ROUTER_INPUT_PORTS,
            output_ports=ROUTER_OUTPUT_PORTS,
            step_fn=_router_step,
            description=(
                "Route one ``data`` payload to a single output port by ``params.routes`` "
                "(first match wins; optional ``default``; else ``unmatched``)."
            ),
        )
    )


__all__ = [
    "register_router",
    "ROUTER_INPUT_PORTS",
    "ROUTER_OUTPUT_PORTS",
    "ROUTER_MAX_BRANCHES",
]
