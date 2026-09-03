from __future__ import annotations

from core.schemas.primitives import Data
from core.schemas.process_graph import ProcessGraph


def coerce_graph(g: ProcessGraph) -> Data | None:
    """Convert ProcessGraph/dict/None to a plain dict for output ports."""
    if g is None:
        return None

    if hasattr(g, "model_dump"):
        return g.model_dump(by_alias=True)

    if isinstance(g, dict):
        return g

    return None
