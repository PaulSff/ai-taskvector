"""
Centralized native versus external runtime detection from graph origin metadata.

Rule: if the workflow is not canonical, it is external. No hardcoded list of
external runtime types is required; the runtime type comes from the graph.

Accepts a ProcessGraph, a JSON graph summary, or None.
"""

from __future__ import annotations

from core.schemas.primitives import JsonObject, is_json_object
from core.schemas.process_graph import ProcessGraph

# Only canonical formats are named. Anything else is external.
_CANONICAL_ORIGIN_FORMATS = frozenset({"dict", "canonical"})


GraphInput = ProcessGraph | JsonObject | None
OriginData = JsonObject


def _origin_to_json_object(origin: object) -> OriginData:
    if is_json_object(origin):
        return origin

    model_dump = getattr(origin, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if is_json_object(dumped) else {}

    legacy_dict = getattr(origin, "dict", None)
    if callable(legacy_dict):
        dumped = legacy_dict()
        return dumped if is_json_object(dumped) else {}

    return {}


def _get_origin_format_and_dict(
    graph: GraphInput,
) -> tuple[str | None, OriginData]:
    """Extract origin_format and origin metadata from a graph or JSON summary."""

    if graph is None:
        return None, {}

    if isinstance(graph, ProcessGraph):
        origin_format = graph.origin_format
        origin = _origin_to_json_object(graph.origin)

        return origin_format, origin

    origin_format = graph.get("origin_format")
    origin = _origin_to_json_object(graph.get("origin"))

    return (
        str(origin_format) if origin_format is not None else None,
        origin,
    )


def is_canonical_runtime(graph: GraphInput) -> bool:
    """Return True for canonical/native graphs and False for external graphs."""

    origin_format, origin = _get_origin_format_and_dict(graph)

    if (
        origin_format is not None
        and origin_format not in _CANONICAL_ORIGIN_FORMATS
    ):
        return False

    # Any truthy origin key other than "canonical" identifies an external
    # runtime. The runtime name is preserved from the graph itself.
    return not any(
        key != "canonical" and bool(value)
        for key, value in origin.items()
    )


def is_external_runtime(graph: GraphInput) -> bool:
    """Return True when the graph targets an external runtime."""

    return not is_canonical_runtime(graph)


def runtime_label(graph: GraphInput) -> str:
    """
    Return the runtime label from the graph.

    Canonical graphs return "canonical". External graphs use origin_format
    first, followed by the first truthy origin metadata key.
    """

    if is_canonical_runtime(graph):
        return "canonical"

    origin_format, origin = _get_origin_format_and_dict(graph)

    if (
        origin_format is not None
        and origin_format not in _CANONICAL_ORIGIN_FORMATS
    ):
        return origin_format

    for key, value in origin.items():
        if key != "canonical" and bool(value):
            return key

    return "canonical"


def external_runtime_or_none(graph: GraphInput) -> str | None:
    """Return the external runtime label, or None for canonical graphs."""

    if not is_external_runtime(graph):
        return None

    return runtime_label(graph)
