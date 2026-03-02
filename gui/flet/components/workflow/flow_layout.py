"""
Convert canonical ProcessGraph to React Flow nodes/edges with layered layout.
Reuses the same layout logic as the Streamlit GUI (gui/app.py).
"""
from __future__ import annotations

from typing import Any

from schemas.process_graph import ProcessGraph


def _layered_layout(unit_list: list, conn_list: list) -> dict[str, tuple[float, float]]:
    """Assign positions with a left-to-right layered layout to reduce edge crossings."""
    unit_ids = [u.id for u in unit_list]
    id_to_idx = {uid: i for i, uid in enumerate(unit_ids)}
    preds: dict[str, list[str]] = {uid: [] for uid in unit_ids}
    for c in conn_list:
        if c.from_id in id_to_idx and c.to_id in id_to_idx and c.from_id != c.to_id:
            preds[c.to_id].append(c.from_id)

    layers: list[list[str]] = []
    assigned: set[str] = set()

    def has_all_preds_assigned(uid: str) -> bool:
        return all(p in assigned for p in preds[uid])

    while len(assigned) < len(unit_ids):
        layer = [uid for uid in unit_ids if uid not in assigned and has_all_preds_assigned(uid)]
        if not layer:
            layer = [uid for uid in unit_ids if uid not in assigned]
        for uid in layer:
            assigned.add(uid)
        layers.append(layer)

    for layer_idx in range(1, len(layers)):
        prev_layer = layers[layer_idx - 1]
        prev_order = {uid: i for i, uid in enumerate(prev_layer)}

        def key(uid: str) -> float:
            p = preds[uid]
            if not p:
                return 0.0
            return sum(prev_order.get(x, 0) for x in p) / len(p)

        layers[layer_idx] = sorted(layers[layer_idx], key=key)

    dx, dy = 260.0, 100.0
    x0, y0 = 80.0, 60.0
    positions: dict[str, tuple[float, float]] = {}
    for li, layer in enumerate(layers):
        base_y = y0 - (len(layer) - 1) * dy / 2 if layer else 0.0
        for ni, uid in enumerate(layer):
            positions[uid] = (x0 + li * dx, base_y + ni * dy)
    return positions


def process_graph_to_react_flow(graph: ProcessGraph) -> dict[str, Any]:
    """Convert canonical ProcessGraph to React Flow nodes and edges (plain dicts)."""
    unit_list = graph.units
    conn_list = graph.connections
    positions = _layered_layout(unit_list, conn_list)

    nodes: list[dict[str, Any]] = []
    for u in unit_list:
        pos = positions.get(u.id, (100.0, 100.0))
        name = (u.name or "").strip() if getattr(u, "name", None) else ""
        if name:
            label = f"{name}\n{u.type}" + ("\n(control)" if u.controllable else "")
        else:
            label = f"{u.type}\n{u.id}" + ("\n(control)" if u.controllable else "")
        nodes.append({
            "id": u.id,
            "type": "default",
            "position": {"x": pos[0], "y": pos[1]},
            "data": {"label": label},
        })

    edges: list[dict[str, Any]] = []
    for j, c in enumerate(conn_list):
        edges.append({
            "id": f"e_{c.from_id}_{c.to_id}_{j}",
            "source": c.from_id,
            "target": c.to_id,
        })

    return {"nodes": nodes, "edges": edges}


# Minimum top/left margin so no nodes are placed above or left of the visible area
CANVAS_LAYOUT_MARGIN = 60.0


EdgeTuple = tuple[str, str, str, str]  # (from_id, to_id, from_port, to_port)


def get_graph_layout_for_canvas(graph: ProcessGraph) -> tuple[dict[str, tuple[float, float]], list[EdgeTuple]]:
    """Return (unit_id -> (left, top), [(from_id, to_id, from_port, to_port), ...]) for Flet Canvas graph.
    Positions are top-left of each node; edges include port indices for visual connection points.
    If graph.layout is present (e.g. from Node-RED/n8n import), use it for the visual preview;
    otherwise use layered auto-layout. Layout is shifted so no node is above or left of CANVAS_LAYOUT_MARGIN."""
    # Start from stored layout if available (import from Node-RED, PyFlow, n8n)
    if graph.layout and graph.layout:
        positions = {uid: (pos.x, pos.y) for uid, pos in graph.layout.items()}
        # Fill in any units missing from layout with layered positions
        missing = [u for u in graph.units if u.id not in positions]
        if missing:
            fallback = _layered_layout(missing, graph.connections)
            for uid, pt in fallback.items():
                positions[uid] = pt
    else:
        positions = _layered_layout(graph.units, graph.connections)
    if not positions:
        return positions, [
            (c.from_id, c.to_id, str(c.from_port or "0"), str(c.to_port or "0"))
            for c in graph.connections
        ]
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    min_x, min_y = min(xs), min(ys)
    shift_x = CANVAS_LAYOUT_MARGIN - min_x if min_x < CANVAS_LAYOUT_MARGIN else 0
    shift_y = CANVAS_LAYOUT_MARGIN - min_y if min_y < CANVAS_LAYOUT_MARGIN else 0
    if shift_x or shift_y:
        positions = {uid: (x + shift_x, y + shift_y) for uid, (x, y) in positions.items()}
    edges: list[EdgeTuple] = [
        (c.from_id, c.to_id, str(c.from_port or "0"), str(c.to_port or "0"))
        for c in graph.connections
    ]
    return positions, edges
