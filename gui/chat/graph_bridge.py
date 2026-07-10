"""Bridge between messenger-driven turns (e.g. telegram_worker) and the live workflow canvas."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

_get_live_graph_dict: Callable[[], dict[str, Any] | None] | None = None
_on_apply_graph: Callable[[dict[str, Any]], Awaitable[None]] | None = None


def register_live_graph_accessors(
    *,
    get_graph_dict: Callable[[], dict[str, Any] | None],
    on_apply_graph: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> None:
    """Register canvas graph getter/apply hooks (called from gui.main on startup)."""
    global _get_live_graph_dict, _on_apply_graph
    _get_live_graph_dict = get_graph_dict
    _on_apply_graph = on_apply_graph


def get_live_graph_dict() -> dict[str, Any] | None:
    """Return the current canvas graph as a dict, or None when GUI is not running."""
    if _get_live_graph_dict is None:
        return None
    try:
        g = _get_live_graph_dict()
        return g if isinstance(g, dict) else None
    except Exception:
        return None


async def apply_graph_from_turn(inner_msg: dict[str, Any]) -> bool:
    """Apply graph from an orchestrator in-progress/final message to the canvas."""
    if _on_apply_graph is None:
        return False
    if not isinstance(inner_msg, dict) or inner_msg.get("graph") is None:
        return False
    try:
        await _on_apply_graph(inner_msg)
        return True
    except Exception:
        return False
