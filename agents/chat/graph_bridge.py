"""Bridge between messenger-driven turns and the live workflow canvas."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.normalizer.normalizer import to_process_graph
from core.schemas.primitives import Data, JsonObject, is_json_object
from core.schemas.process_graph import ProcessGraph

_get_live_graph_dict: Callable[[], Data | None] | None = None
_on_apply_graph: Callable[[Data], Awaitable[None]] | None = None


def register_live_graph_accessors(
    *,
    get_graph_dict: Callable[[], Data | None],
    on_apply_graph: Callable[[Data], Awaitable[None]] | None = None,
) -> None:
    global _get_live_graph_dict, _on_apply_graph

    _get_live_graph_dict = get_graph_dict
    _on_apply_graph = on_apply_graph


def get_live_graph_dict() -> JsonObject | None:
    if _get_live_graph_dict is None:
        return None

    try:
        graph = _get_live_graph_dict()
    except (TypeError, ValueError, AttributeError):
        return None

    if not is_json_object(graph):
        return None

    return graph


def _normalize_inner_msg(inner_msg: Data) -> Data | None:
    if not isinstance(inner_msg, dict):
        return None

    raw_graph = inner_msg.get("graph")
    if raw_graph is None:
        return None

    if isinstance(raw_graph, ProcessGraph):
        return inner_msg

    if not isinstance(raw_graph, dict):
        return None

    process_graph = to_process_graph(
        raw_graph,
        format="dict",
    )

    normalized_msg = dict(inner_msg)
    normalized_msg["graph"] = process_graph

    return normalized_msg


async def apply_graph_from_turn(inner_msg: Data) -> bool:
    """Normalize and apply a graph from an orchestrator message."""
    if _on_apply_graph is None:
        return False

    try:
        normalized_msg = _normalize_inner_msg(inner_msg)

        if normalized_msg is None:
            return False

        await _on_apply_graph(normalized_msg)
        return True

    except (TypeError, ValueError, KeyError):
        return False
