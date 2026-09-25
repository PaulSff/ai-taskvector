"""Bridge between messenger-driven turns (e.g. telegram_worker) and the live workflow canvas."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.schemas.primitives import Data, JsonObject, is_json_object

_get_live_graph_dict: Callable[[], Data | None] | None = None
_on_apply_graph: Callable[[Data], Awaitable[None]] | None = None


def register_live_graph_accessors(
    *,
    get_graph_dict: Callable[[], Data | None],
    on_apply_graph: Callable[[Data], Awaitable[None]] | None = None,
) -> None:
    """Register canvas graph getter/apply hooks (called from gui.main on startup)."""
    global _get_live_graph_dict, _on_apply_graph
    _get_live_graph_dict = get_graph_dict
    _on_apply_graph = on_apply_graph


def get_live_graph_dict() -> JsonObject | None:
    """Return the current canvas graph as a JSON-compatible dict,
    or None when GUI is not running.
    """
    if _get_live_graph_dict is None:
        return None

    try:
        graph = _get_live_graph_dict()
    except (TypeError, ValueError, AttributeError):
        return None

    if not is_json_object(graph):
        return None

    return graph


async def apply_graph_from_turn(inner_msg: Data) -> bool:
    """Apply graph from an orchestrator in-progress/final message to the canvas."""
    if _on_apply_graph is None:
        return False
    if not isinstance(inner_msg, dict) or inner_msg.get("graph") is None:
        return False

    try:
        await _on_apply_graph(inner_msg)
        return True
    except (TypeError, ValueError, RuntimeError):
        return False
