from core.schemas.process_graph import ProcessGraph


def _topological_order(graph: ProcessGraph, process_unit_ids: set[str]) -> list[str]:
    """Return unit ids in execution order (dependencies first). Raises on cycle."""
    preds: dict[str, list[str]] = {uid: [] for uid in process_unit_ids}
    for c in graph.connections:
        if (
            c.from_id in process_unit_ids
            and c.to_id in process_unit_ids
            and c.from_id != c.to_id
        ):
            if c.to_id not in preds:
                preds[c.to_id] = []
            preds[c.to_id].append(c.from_id)

    order: list[str] = []
    remaining = set(process_unit_ids)
    while remaining:
        ready = [u for u in remaining if all(p in order for p in preds.get(u, []))]
        if not ready:
            raise ValueError("Cycle detected in graph or unresolved dependencies")
        order.extend(sorted(ready))
        remaining -= set(ready)
    return order
