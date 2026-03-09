"""
Convert canonical ProcessGraph to React Flow nodes/edges with layered layout.
Reuses the same layout logic as the Streamlit GUI (gui/app.py).
"""
from __future__ import annotations

from typing import Any

from core.schemas.process_graph import NodePosition, ProcessGraph


# Spacing for layered layout; increase when many nodes so they don't overlap
LAYER_DX = 280.0
LAYER_DY = 120.0
LAYER_DY_LARGE = 140.0  # when many units
LAYER_NODE_THRESHOLD = 10  # use LAYER_DY_LARGE when unit count >= this
LAYER_X0, LAYER_Y0 = 80.0, 60.0


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

    dy = LAYER_DY_LARGE if len(unit_ids) >= LAYER_NODE_THRESHOLD else LAYER_DY
    dx, x0, y0 = LAYER_DX, LAYER_X0, LAYER_Y0
    positions: dict[str, tuple[float, float]] = {}
    for li, layer in enumerate(layers):
        base_y = y0 - (len(layer) - 1) * dy / 2 if layer else 0.0
        for ni, uid in enumerate(layer):
            positions[uid] = (x0 + li * dx, base_y + ni * dy)
    return positions


def _bbox(positions: dict[str, tuple[float, float]]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y)."""
    if not positions:
        return 0.0, 0.0, 0.0, 0.0
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    return min(xs), min(ys), max(xs), max(ys)


def _layout_has_overlaps(
    positions: dict[str, tuple[float, float]],
    min_dist: float = 100.0,
) -> bool:
    """True if any two nodes are closer than min_dist (used to detect messy/imported layouts). O(n^2) one-time at layout."""
    if len(positions) < 2:
        return False
    uids = list(positions.keys())
    for i, a in enumerate(uids):
        xa, ya = positions[a]
        for b in uids[i + 1 :]:
            xb, yb = positions[b]
            d = ((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5
            if d < min_dist:
                return True
    return False


def _ensure_minimum_spacing(
    positions: dict[str, tuple[float, float]],
    min_dist: float = 90.0,
) -> dict[str, tuple[float, float]]:
    """Push apart nodes that are closer than min_dist (simple iterative nudge). O(n^2) per pass, one-time at layout."""
    if len(positions) < 2:
        return positions
    uids = list(positions.keys())
    out = dict(positions)
    for _ in range(5):  # few passes
        moved = False
        for i, a in enumerate(uids):
            xa, ya = out[a]
            for b in uids[i + 1 :]:
                xb, yb = out[b]
                dx, dy = xb - xa, yb - ya
                d = (dx * dx + dy * dy) ** 0.5
                if d > 0 and d < min_dist:
                    nudge = (min_dist - d) / d
                    half = nudge * 0.5
                    out[a] = (xa - dx * half, ya - dy * half)
                    out[b] = (xb + dx * half, yb + dy * half)
                    xa, ya = out[a]
                    moved = True
        if not moved:
            break
    return out


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


# Margin to place new-unit block to the right of existing layout
FALLBACK_BLOCK_MARGIN = 120.0


def get_graph_layout_for_canvas(graph: ProcessGraph) -> tuple[dict[str, tuple[float, float]], list[EdgeTuple]]:
    """Return (unit_id -> (left, top), [(from_id, to_id, from_port, to_port), ...]) for Flet Canvas graph.
    Positions are top-left of each node; edges include port indices for visual connection points.
    Uses the same layered layout as first startup whenever the stored layout is missing, overlapping,
    or has missing units (e.g. after import or add_unit), so the preview stays readable."""
    # Use stored layout only if it exists, has no overlaps, and covers all units
    if graph.layout and graph.layout:
        positions = {uid: (pos.x, pos.y) for uid, pos in graph.layout.items()}
        missing = [u for u in graph.units if u.id not in positions]
        use_stored = not missing and not _layout_has_overlaps(positions, min_dist=100.0)
        if use_stored:
            # Stored layout is fine: apply minimum spacing and use it
            positions = _ensure_minimum_spacing(positions)
        else:
            # Same arrangement as first startup: full layered layout
            positions = _layered_layout(graph.units, graph.connections)
            if graph.layout is None:
                graph.layout = {}
            graph.layout.clear()
            for uid, (x, y) in positions.items():
                graph.layout[uid] = NodePosition(x=x, y=y)
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
