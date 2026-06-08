from typing import Any, Dict, Optional


def _coerce_graph(g: Any) -> Optional[Dict]:
    """Convert ProcessGraph/dict/None to a plain dict for output ports."""
    if g is None:
        return None
    if hasattr(g, "model_dump"):
        return g.model_dump(by_alias=True)
    if isinstance(g, dict):
        return g
    return None
