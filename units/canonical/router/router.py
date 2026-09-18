"""
Router unit: one ``data`` input, fan-out to at most one output port by declarative routes in ``params``.

First matching non-default route wins; then ``default`` if present; otherwise ``unmatched``.
The **same** payload object is emitted on the chosen port only (other ports are not set on outputs dict).

Typical use: branch ``read_file`` / path suffix (e.g. ``.xlsx``) before different downstream subgraphs.
"""
from __future__ import annotations

import re

from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

ROUTER_MAX_BRANCHES = 16

ROUTER_INPUT_PORTS = [("data", "Any")]
ROUTER_OUTPUT_PORTS: list[tuple[str, str]] = [
    *( (f"out_{i}", "Any") for i in range(ROUTER_MAX_BRANCHES)),
    ("default", "Any"),
    ("unmatched", "Any"),
]


_ALLOWED_PORTS = frozenset(p for p, _ in ROUTER_OUTPUT_PORTS)


def _get_field(data: object, field: str) -> object | None:
    if not field:
        return data

    cur: object = data

    for part in field.strip().split("."):
        if not part:
            continue

        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None

    return cur

def _match_one_rule(value: object, rule: Data) -> bool:
    if rule.get("exists") is True:
        return value is not None

    if "equals" in rule:
        return value == rule.get("equals")

    if "equals_str" in rule:
        return str(value or "").strip() == str(
            rule.get("equals_str") or ""
        ).strip()

    if "gt" in rule:
        threshold = rule.get("gt")

        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
        ):
            return value > threshold

        return False

    if "gte" in rule:
        threshold = rule.get("gte")

        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
        ):
            return value >= threshold

        return False

    if "ends_with" in rule:
        suffix = str(rule.get("ends_with") or "")
        text = str(value or "")

        return bool(suffix) and text.lower().endswith(suffix.lower())

    if "starts_with" in rule:
        prefix = str(rule.get("starts_with") or "")
        text = str(value or "")

        return bool(prefix) and text.lower().startswith(prefix.lower())

    if "contains" in rule:
        needle = str(rule.get("contains") or "")
        text = str(value or "")

        return bool(needle) and needle.lower() in text.lower()

    if "regex" in rule:
        pattern = str(rule.get("regex") or "")

        if not pattern:
            return False

        try:
            return re.search(
                pattern,
                str(value or ""),
                flags=re.DOTALL,
            ) is not None
        except re.error:
            return False

    return False


def _match_rule(data: object, rule: Data) -> bool:
    # Check whether at least one item in an array matches the nested rule.
    if "any_item" in rule:
        config = rule.get("any_item")

        if not isinstance(config, dict):
            return False

        field = config.get("field", "")

        if not isinstance(field, str):
            return False

        items = _get_field(data, field)

        if not isinstance(items, list):
            return False

        nested_rule = config.get("rule")

        if not isinstance(nested_rule, dict):
            return False

        return any(_match_rule(item, nested_rule) for item in items)

    raw_field = rule.get("field", "")

    if raw_field is None:
        field = ""
    elif isinstance(raw_field, str):
        field = raw_field.strip()
    else:
        field = str(raw_field).strip()

    if not field:
        value = data
    else:
        if not isinstance(data, dict):
            return _match_one_rule(None, rule)

        value = _get_field(data, field)

    return _match_one_rule(value, rule)



def _match_all(data: object, rules: list[object]) -> bool:
    if not rules:
        return True

    for rule in rules:
        if not isinstance(rule, dict):
            return False

        if not _match_rule(data, rule):
            return False

    return True


def _match_any(data: object, rules: list[object]) -> bool:
    if not rules:
        return False

    for rule in rules:
        if isinstance(rule, dict) and _match_rule(data, rule):
            return True

    return False


def _router_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    data = inputs.get("data")

    routes = params.get("routes")
    if not isinstance(routes, list):
        routes = []

    default_port: str | None = None
    default_route: Data | None = None

    ordered: list[tuple[str, Data]] = []

    for raw in routes:
        if not isinstance(raw, dict):
            continue

        port = str(raw.get("port") or "").strip()

        if not port or port not in _ALLOWED_PORTS:
            continue

        if raw.get("default") is True:
            if default_port is None:
                default_port = port
                default_route = raw
            continue

        ordered.append((port, raw))

    chosen: str | None = None
    chosen_route: Data | None = None

    # Evaluate conditional routes in declaration order.
    for port, raw in ordered:
        all_rules = raw.get("all")
        any_rules = raw.get("any")

        if isinstance(all_rules, list) and all_rules:
            ok = _match_all(data, all_rules)
        elif isinstance(any_rules, list) and any_rules:
            ok = _match_any(data, any_rules)
        else:
            # No conditions means the route never matches.
            ok = False

        if ok:
            chosen = port
            chosen_route = raw
            break

    # Use the configured default route when no conditional route matches.
    if chosen is None and default_port is not None:
        chosen = default_port
        chosen_route = default_route

    # No matching route and no default route.
    if chosen is None:
        chosen = "unmatched"

    # If the selected route defines parser_output, emit the configured
    # output instead of the original input payload.
    if (
        isinstance(chosen_route, dict)
        and "parser_output" in chosen_route
    ):
        output_data = chosen_route["parser_output"]
    else:
        output_data = data

    return {chosen: output_data}, state


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
    "ROUTER_INPUT_PORTS",
    "ROUTER_MAX_BRANCHES",
    "ROUTER_OUTPUT_PORTS",
    "register_router",
]
