"""
RagContentClassify unit: pick a string label from the first matching rule set (declarative params).

Rule shape matches Router-style ``all`` / ``any`` lists of ``{field, exists, equals, ...}`` (see Router unit).
"""
from __future__ import annotations

import re
from typing import Any

from units.registry import UnitSpec, register_unit

RAG_CONTENT_CLASSIFY_INPUT_PORTS = [("data", "Any")]
RAG_CONTENT_CLASSIFY_OUTPUT_PORTS = [("label", "str"), ("data", "Any"), ("error", "str")]


def _get_field(data: Any, field: str) -> Any:
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


def _rag_content_classify_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = inputs.get("data")
    err = ""
    raw_list = params.get("classifications")
    if not isinstance(raw_list, list):
        raw_list = []
    default_label = str(params.get("default_label") or "unclassified").strip() or "unclassified"

    chosen = default_label
    for block in raw_list:
        if not isinstance(block, dict):
            continue
        label = str(block.get("label") or "").strip()
        if not label:
            continue
        all_rules = block.get("all")
        any_rules = block.get("any")
        ok = False
        if isinstance(all_rules, list) and all_rules:
            ok = _match_all(data, all_rules)
        elif isinstance(any_rules, list) and any_rules:
            ok = _match_any(data, any_rules)
        else:
            continue
        if ok:
            chosen = label
            break

    return {"label": chosen, "data": data, "error": err}, state


def register_rag_content_classify() -> None:
    register_unit(
        UnitSpec(
            type_name="RagContentClassify",
            input_ports=RAG_CONTENT_CLASSIFY_INPUT_PORTS,
            output_ports=RAG_CONTENT_CLASSIFY_OUTPUT_PORTS,
            step_fn=_rag_content_classify_step,
            environment_tags_are_agnostic=True,
            description=(
                "Declarative label for RAG: params.classifications [{label, all:[rules]}, …], "
                "params.default_label; same rule keys as Router."
            ),
        )
    )


__all__ = [
    "register_rag_content_classify",
    "RAG_CONTENT_CLASSIFY_INPUT_PORTS",
    "RAG_CONTENT_CLASSIFY_OUTPUT_PORTS",
]
