"""
Centralized native vs external runtime detection from graph origin/origin_format.
Rule: if the workflow is not canonical, it is external. No hardcoded list of external types.
Accepts ProcessGraph or dict (e.g. graph summary with origin_format and origin).
"""
from __future__ import annotations

from typing import Any

# Only canonical is named; anything else is external (type comes from the graph).
_CANONICAL_ORIGIN_FORMATS = frozenset({"dict", "canonical"})


def _get_origin_format_and_dict(graph_or_dict: Any) -> tuple[str | None, dict[str, Any]]:
    """Extract origin_format and origin as dict from ProcessGraph or dict."""
    if graph_or_dict is None:
        return None, {}
    if hasattr(graph_or_dict, "origin_format") or hasattr(graph_or_dict, "origin"):
        fmt = getattr(graph_or_dict, "origin_format", None)
        origin = getattr(graph_or_dict, "origin", None)
        if origin is not None:
            if hasattr(origin, "model_dump") and callable(origin.model_dump):
                origin = origin.model_dump()
            elif hasattr(origin, "dict") and callable(origin.dict):
                origin = origin.dict()
            elif not isinstance(origin, dict):
                origin = {}
        else:
            origin = {}
        return (str(fmt) if fmt is not None else None), (origin if isinstance(origin, dict) else {})
    if isinstance(graph_or_dict, dict):
        fmt = graph_or_dict.get("origin_format")
        origin = graph_or_dict.get("origin")
        if origin is not None and not isinstance(origin, dict):
            origin = {}
        elif origin is None:
            origin = {}
        return (str(fmt) if fmt is not None else None), origin
    return None, {}


def is_canonical_runtime(graph_or_dict: Any) -> bool:
    """True if graph is canonical (native); False if external. Not canonical => external."""
    fmt, origin = _get_origin_format_and_dict(graph_or_dict)
    if fmt is not None and fmt not in _CANONICAL_ORIGIN_FORMATS:
        return False
    if isinstance(origin, dict) and origin:
        # Any truthy key other than "canonical" means external (type from graph).
        for k, v in origin.items():
            if k != "canonical" and v:
                return False
    return True


def is_external_runtime(graph_or_dict: Any) -> bool:
    """True if graph runs on an external runtime; False if canonical. Not canonical => external."""
    return not is_canonical_runtime(graph_or_dict)


def runtime_label(graph_or_dict: Any) -> str:
    """Runtime type from the graph: origin_format or first truthy origin key when external, else 'canonical'."""
    if is_canonical_runtime(graph_or_dict):
        return "canonical"
    fmt, origin = _get_origin_format_and_dict(graph_or_dict)
    if fmt and fmt not in _CANONICAL_ORIGIN_FORMATS:
        return str(fmt)
    if isinstance(origin, dict):
        for k, v in origin.items():
            if k != "canonical" and v:
                return k
    return "canonical"


def external_runtime_or_none(graph_or_dict: Any) -> str | None:
    """Return the external runtime type from the graph if external, else None."""
    if not is_external_runtime(graph_or_dict):
        return None
    return runtime_label(graph_or_dict)
