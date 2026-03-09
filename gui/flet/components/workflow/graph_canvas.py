"""
Pure Flet process graph: Canvas for edges + draggable Node controls.
Grid is drawn as a background SVG (one asset) to reduce canvas load; canvas holds only edges.
"""
from __future__ import annotations

import asyncio
import base64
import time
from typing import Callable, Optional

import flet as ft
import flet.canvas as cv

from core.schemas.process_graph import NodePosition, ProcessGraph, Unit

from gui.flet.components.workflow.flow_layout import (
    CANVAS_LAYOUT_MARGIN,
    EdgeTuple,
    get_graph_layout_for_canvas,
)
from gui.flet.components.workflow.grid import (
    DEFAULT_CELL_SIZE as GRID_DEFAULT_CELL_SIZE,
    IndexGrid,
    NodeGrid,
    build_node_grid,
)
from gui.flet.components.workflow.index import (
    GraphIndex,
    build_graph_index,
    compute_visual_ports,
)
from gui.flet.components.workflow.graph_style_config import (
    DEFAULT_NODE_HEIGHT,
    DEFAULT_NODE_WIDTH,
    NODE_PADDING,
    PORT_DOT_RADIUS,
    PORT_EDGE_MARGIN,
    PORT_ROW_HEIGHT,
    get_default_style_config,
    get_link_style,
    get_link_style_from_node_border,
    get_node_style,
    GraphStyleConfig,
    ResolvedLinkStyle,
    ResolvedNodeStyle,
)
from gui.flet.tools.gestures import wrap_hover

# Minimum canvas size for scroll/pan; actual size grows to fit graph (see build_graph_canvas)
CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 1200
# Background dot grid uses same cell size as spatial grid (grid.py); dots at cell vertices.
DOT_RADIUS = 0.8  # Smaller = 1.0 or 0.75; larger = 1.5 or 2
DRAG_UPDATE_INTERVAL_S = 1 / 10  # Throttle node redraws during drag to reduce lag
# Run hover hit-test in a thread so UI doesn't block (disable if no threads, e.g. Pyodide)
HOVER_HIT_TEST_IN_THREAD = True
# Canvas hover: ms between hover events; higher = less CPU, slightly less responsive (default 50)
CANVAS_HOVER_INTERVAL_MS = 130
# Node drag: ms between pan_update events; higher = fewer updates during drag (default 80)
NODE_DRAG_INTERVAL_MS = 180
# Grid and canvas (node/link styling is in graph_style_config)
GRID_DOT_COLOR_HEX = "#616161"  # Material grey 700
CANVAS_BG = ft.Colors.GREY_900

# Node-RED (and similar) can include non-executable container/config items (e.g. tabs/groups).
# We preserve them for roundtrip metadata but do not render them as nodes in our canvas.
_HIDDEN_UNIT_TYPES: set[str] = {"tab", "group"}


def _get_port_counts(unit: Unit, graph: ProcessGraph) -> tuple[int, int]:
    """Return (n_inputs, n_outputs): one dot per port from unit spec, or from connections if no ports set."""
    uid = unit.id
    in_ports = getattr(unit, "input_ports", None)
    out_ports = getattr(unit, "output_ports", None)
    n_in = len(in_ports) if in_ports else 0
    n_out = len(out_ports) if out_ports else 0
    if n_in == 0:
        n_in = max(1, sum(1 for c in graph.connections if c.to_id == uid))
    if n_out == 0:
        n_out = max(1, sum(1 for c in graph.connections if c.from_id == uid))
    return (n_in, n_out)


def _get_connected_port_indices(unit_id: str, graph: ProcessGraph) -> tuple[set[int], set[int]]:
    """Return (connected_input_indices, connected_output_indices) for the unit (0-based port index)."""
    connected_in: set[int] = set()
    connected_out: set[int] = set()
    for c in graph.connections:
        if c.to_id == unit_id:
            try:
                connected_in.add(int(c.to_port) if c.to_port else 0)
            except (ValueError, TypeError):
                connected_in.add(0)
        if c.from_id == unit_id:
            try:
                connected_out.add(int(c.from_port) if c.from_port else 0)
            except (ValueError, TypeError):
                connected_out.add(0)
    return (connected_in, connected_out)


def _build_node_content(
    unit: Unit,
    style: ResolvedNodeStyle,
    n_inputs: int,
    n_outputs: int,
    connected_inputs: set[int] | None = None,
    connected_outputs: set[int] | None = None,
) -> tuple[ft.Control, int, int]:
    """Build node with port dots. Filled dot for connected ports, empty (hollow) dot for unconnected. Returns (control, width, height)."""
    display_name = (unit.name or "").strip() if getattr(unit, "name", None) else ""
    if display_name:
        text_controls = [
            ft.Text(display_name, size=14, weight=ft.FontWeight.BOLD, color=style.text_color),
            ft.Text(unit.type, size=11, color=style.text_secondary_color),
        ]
    else:
        text_controls = [
            ft.Text(unit.type, size=14, weight=ft.FontWeight.BOLD, color=style.text_color),
            ft.Text(unit.id, size=11, color=style.text_secondary_color),
        ]
    if unit.controllable:
        text_controls.append(ft.Text("(control)", size=10, color=ft.Colors.BLUE_300))
    text_col = ft.Column(text_controls, tight=True, spacing=2)
    if style.icon:
        icon_name = style.icon.upper().replace("-", "_").replace(" ", "_")
        icon = getattr(ft.Icons, icon_name, None)
        if icon is not None:
            content: ft.Control = ft.Row(
                [ft.Icon(icon, color=style.text_color, size=28), text_col],
                spacing=8,
                tight=True,
            )
        else:
            content = text_col
    else:
        content = text_col
    port_rows = max(n_inputs, n_outputs, 1)
    # Include edge margin and padding so first/last port dots stay inside node border
    body_height = max(
        style.height,
        2 * NODE_PADDING + 2 * PORT_EDGE_MARGIN + port_rows * PORT_ROW_HEIGHT,
    )
    port_color = style.border_color
    connected_in = connected_inputs if connected_inputs is not None else set()
    connected_out = connected_outputs if connected_outputs is not None else set()

    def _dot(connected: bool) -> ft.Control:
        if connected:
            return ft.Container(
                width=PORT_DOT_RADIUS * 2,
                height=PORT_DOT_RADIUS * 2,
                border_radius=PORT_DOT_RADIUS,
                bgcolor=port_color,
            )
        return ft.Container(
            width=PORT_DOT_RADIUS * 2,
            height=PORT_DOT_RADIUS * 2,
            border_radius=PORT_DOT_RADIUS,
            border=ft.border.all(1, port_color),
            bgcolor=style.bgcolor,
        )

    def _port_column(n: int, connected_set: set[int], margin_left: int = 0, margin_right: int = 0) -> ft.Control:
        if n <= 0:
            return ft.Container(width=1)
        col = ft.Column(
            [
                ft.Container(
                    content=_dot(i in connected_set),
                    alignment=ft.Alignment(0, 0),
                    height=PORT_ROW_HEIGHT,
                )
                for i in range(n)
            ],
            spacing=0,
            tight=True,
        )
        inner = ft.Container(content=col, margin=ft.Margin.only(top=PORT_EDGE_MARGIN, bottom=PORT_EDGE_MARGIN))
        if margin_left or margin_right:
            return ft.Container(
                content=inner,
                margin=ft.Margin.only(left=margin_left, right=margin_right),
            )
        return inner

    # Position port columns so dots straddle the border (half inside, half outside)
    left_col = _port_column(n_inputs, connected_in, margin_left=-PORT_DOT_RADIUS)
    right_col = _port_column(n_outputs, connected_out, margin_right=-PORT_DOT_RADIUS)
    inner = ft.Row(
        [left_col, content, right_col],
        spacing=4,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    control = ft.Container(
        content=inner,
        width=style.width,
        height=body_height,
        padding=NODE_PADDING,
        border=ft.border.all(1, style.border_color),
        border_radius=style.border_radius,
        bgcolor=style.bgcolor,
        clip_behavior=ft.ClipBehavior.NONE,  # Let port dots overflow the border
    )
    return control, style.width, body_height


def _port_y_offset(port_index: int, port_count: int, node_height: int) -> float:
    """Return Y offset from node top to center of port (port_index 0-based). Matches port column layout with PORT_EDGE_MARGIN and NODE_PADDING from style config."""
    if port_count <= 0:
        return node_height / 2
    return NODE_PADDING + PORT_EDGE_MARGIN + (port_index + 0.5) * PORT_ROW_HEIGHT


def _is_hidden_unit_type(unit_type: str) -> bool:
    return str(unit_type).lower() in _HIDDEN_UNIT_TYPES


def _build_dot_grid_svg(
    width: int,
    height: int,
    spacing: int | float,
    radius: float = DOT_RADIUS,
    fill: str = GRID_DOT_COLOR_HEX,
) -> str:
    """Dot grid as SVG string; dots at cell vertices (same spacing as spatial grid). One asset, no canvas shapes."""
    spacing = int(spacing)
    if spacing <= 0:
        spacing = 120
    circles: list[str] = []
    x = 0
    while x <= width:
        y = 0
        while y <= height:
            circles.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{fill}"/>')
            y += spacing
        x += spacing
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        + "".join(circles)
        + "</svg>"
    )


# How much edges curve (control point offset as fraction of edge length)
EDGE_CURVE_FACTOR = 0.25
# Hover: max distance from pointer to edge curve to count as "on" the line
EDGE_HOVER_THRESHOLD = 20.0


def _edge_bezier_points(
    positions: dict[str, tuple[float, float]],
    from_id: str,
    to_id: str,
    *,
    from_port: str = "0",
    to_port: str = "0",
    from_size: tuple[int, int] = (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT),
    to_size: tuple[int, int] = (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT),
    port_layout: dict[str, tuple[int, int]] | None = None,
) -> tuple[float, float, float, float, float, float, float, float] | None:
    """Return (sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty) for the edge curve, or None."""
    if from_id not in positions or to_id not in positions:
        return None
    x1, y1 = positions[from_id]
    x2, y2 = positions[to_id]
    fw, fh = from_size
    tw, th = to_size
    pl = port_layout or {}
    _, n_out = pl.get(from_id, (1, 1))
    n_in, _ = pl.get(to_id, (1, 1))
    try:
        fp_idx = min(int(from_port), n_out - 1) if n_out else 0
    except (ValueError, TypeError):
        fp_idx = 0
    try:
        tp_idx = min(int(to_port), n_in - 1) if n_in else 0
    except (ValueError, TypeError):
        tp_idx = 0
    # Start/end at port dot centers (dots straddle node border by PORT_DOT_RADIUS)
    sx = x1 + fw + PORT_DOT_RADIUS
    sy = y1 + _port_y_offset(fp_idx, n_out, fh)
    tx = x2 - PORT_DOT_RADIUS
    ty = y2 + _port_y_offset(tp_idx, n_in, th)
    dx, dy = tx - sx, ty - sy
    dist = (dx * dx + dy * dy) ** 0.5 or 1
    perp_x = -dy / dist
    perp_y = dx / dist
    offset = min(50, dist * EDGE_CURVE_FACTOR)
    # When target is lower-right (dx>0, dy>0), invert curve so it bulges toward the target instead of away
    if dx > 0 and dy > 0:
        offset = -offset
    mid_x = (sx + tx) / 2
    mid_y = (sy + ty) / 2
    cp1x = (sx + mid_x) / 2 + perp_x * offset
    cp1y = (sy + mid_y) / 2 + perp_y * offset
    cp2x = (tx + mid_x) / 2 - perp_x * offset
    cp2y = (ty + mid_y) / 2 - perp_y * offset
    return (sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty)


def _point_to_bezier_distance(
    px: float, py: float,
    x0: float, y0: float,
    cp1x: float, cp1y: float, cp2x: float, cp2y: float,
    x1: float, y1: float,
    samples: int = 12,
) -> float:
    """Approximate distance from (px, py) to cubic Bézier (x0,y0) -> cp1 -> cp2 -> (x1,y1)."""
    best = 1e30
    for i in range(samples + 1):
        t = i / samples
        u = 1.0 - t
        bx = u * u * u * x0 + 3 * u * u * t * cp1x + 3 * u * t * t * cp2x + t * t * t * x1
        by = u * u * u * y0 + 3 * u * u * t * cp1y + 3 * u * t * t * cp2y + t * t * t * y1
        d = ((px - bx) ** 2 + (py - by) ** 2) ** 0.5
        if d < best:
            best = d
    return best


def _hover_hit_test_thread(
    positions_snapshot: dict[str, tuple[float, float]],
    edges: list[EdgeTuple],
    node_ids_order: list[str],
    node_sizes_map: dict[str, tuple[int, int]],
    port_layout: dict[str, tuple[int, int]],
    visual_ports: list[tuple[str, str]],
    x: float,
    y: float,
    *,
    node_grid: NodeGrid | None = None,
    edge_grid: IndexGrid | None = None,
    node_order_map: dict[str, int] | None = None,
) -> tuple[str | None, EdgeTuple | None]:
    """Run in a thread: return (node_id, edge_key) for hover at (x, y).
    When node_grid/edge_grid are provided (built once at canvas build), only the cell under (x,y) is queried (O(1)).
    When node_order_map is provided with candidates, only nodes in that cell are walked (O(k))."""
    if node_grid is not None:
        node_candidates = node_grid.query(x, y)
    else:
        node_grid_built = build_node_grid(
            positions_snapshot,
            node_sizes_map,
            cell_size=GRID_DEFAULT_CELL_SIZE,
            default_width=DEFAULT_NODE_WIDTH,
            default_height=DEFAULT_NODE_HEIGHT,
        )
        node_candidates = node_grid_built.query(x, y)
    node = _node_at_point(
        positions_snapshot, node_ids_order, x, y,
        node_sizes=node_sizes_map, candidates=node_candidates, order_map=node_order_map,
    )
    edge_candidates: set[int] | None = None
    if node is None and edges:
        if edge_grid is not None:
            edge_candidates = edge_grid.query(x, y)
        else:
            edge_grid_built = IndexGrid(cell_size=GRID_DEFAULT_CELL_SIZE)
            pl = port_layout or {}
            vp = visual_ports or []
            def size(uid: str) -> tuple[int, int]:
                return node_sizes_map.get(uid, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
            for i, edge in enumerate(edges):
                from_id, to_id = edge[0], edge[1]
                fp, tp = vp[i] if i < len(vp) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
                bbox = _edge_bbox(
                    positions_snapshot, from_id, to_id,
                    from_port=fp, to_port=tp,
                    from_size=size(from_id), to_size=size(to_id),
                    port_layout=pl,
                )
                if bbox is not None:
                    min_x, min_y, max_x, max_y = bbox
                    edge_grid_built.insert(i, min_x, min_y, max_x, max_y, expand_by=EDGE_HOVER_THRESHOLD)
            edge_candidates = edge_grid_built.query(x, y)
    edge = (
        _edge_at_point(
            positions_snapshot, edges, x, y,
            node_sizes=node_sizes_map, port_layout=port_layout, visual_ports=visual_ports,
            candidate_indices=edge_candidates,
        )
        if node is None
        else None
    )
    return (node, edge)


def _node_at_point(
    positions: dict[str, tuple[float, float]],
    node_ids_order: list[str],
    px: float,
    py: float,
    *,
    node_sizes: dict[str, tuple[int, int]] | None = None,
    candidates: set[str] | None = None,
    order_map: dict[str, int] | None = None,
) -> str | None:
    """Return the topmost node id that contains (px, py), or None. node_ids_order = draw order (last = top).
    If candidates is provided, only those nodes are considered (from spatial grid).
    When both candidates and order_map are provided, iterates only over candidates (O(k)) and uses order_map for z-order."""
    if candidates is not None and order_map is not None:
        # Grid-based path: only walk nodes in the cell; pick topmost by order_map (higher = on top).
        best_uid: str | None = None
        best_order = -1
        for uid in candidates:
            if uid not in positions:
                continue
            left, top = positions[uid]
            w, h = (node_sizes.get(uid, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))) if node_sizes else (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)
            if left <= px <= left + w and top <= py <= top + h:
                o = order_map.get(uid, -1)
                if o > best_order:
                    best_order = o
                    best_uid = uid
        return best_uid
    # Fallback: full walk (when no grid/order_map).
    for uid in reversed(node_ids_order):
        if uid not in positions:
            continue
        if candidates is not None and uid not in candidates:
            continue
        left, top = positions[uid]
        w, h = (node_sizes.get(uid, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))) if node_sizes else (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)
        if left <= px <= left + w and top <= py <= top + h:
            return uid
    return None


def _edge_bbox(
    positions: dict[str, tuple[float, float]],
    from_id: str,
    to_id: str,
    *,
    from_port: str = "0",
    to_port: str = "0",
    from_size: tuple[int, int] = (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT),
    to_size: tuple[int, int] = (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT),
    port_layout: dict[str, tuple[int, int]] | None = None,
) -> tuple[float, float, float, float] | None:
    """Return (min_x, min_y, max_x, max_y) for the edge's Bézier curve, or None."""
    pts = _edge_bezier_points(
        positions, from_id, to_id,
        from_port=from_port, to_port=to_port,
        from_size=from_size, to_size=to_size,
        port_layout=port_layout or {},
    )
    if pts is None:
        return None
    sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty = pts
    min_x = min(sx, cp1x, cp2x, tx)
    max_x = max(sx, cp1x, cp2x, tx)
    min_y = min(sy, cp1y, cp2y, ty)
    max_y = max(sy, cp1y, cp2y, ty)
    return (min_x, min_y, max_x, max_y)


def _edge_at_point(
    positions: dict[str, tuple[float, float]],
    edges: list[EdgeTuple],
    px: float,
    py: float,
    threshold: float = EDGE_HOVER_THRESHOLD,
    *,
    node_sizes: dict[str, tuple[int, int]] | None = None,
    port_layout: dict[str, tuple[int, int]] | None = None,
    visual_ports: list[tuple[str, str]] | None = None,
    candidate_indices: set[int] | None = None,
) -> tuple[EdgeTuple, EdgeTuple] | None:
    """Return ((edge_for_callback, visual_key_for_highlight)) of nearest edge, or None.
    If candidate_indices is provided, only those edge indices are tested (from spatial grid)."""
    def size(uid: str) -> tuple[int, int]:
        return node_sizes.get(uid, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)) if node_sizes else (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)

    best_result: tuple[EdgeTuple, EdgeTuple] | None = None
    best_d = threshold + 1.0
    pl = port_layout or {}
    vp = visual_ports or []
    indices = range(len(edges)) if candidate_indices is None else sorted(candidate_indices)
    for i in indices:
        if i < 0 or i >= len(edges):
            continue
        edge = edges[i]
        from_id, to_id = edge[0], edge[1]
        fp, tp = vp[i] if i < len(vp) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
        pts = _edge_bezier_points(
            positions, from_id, to_id,
            from_port=fp, to_port=tp,
            from_size=size(from_id), to_size=size(to_id),
            port_layout=pl,
        )
        if pts is None:
            continue
        sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty = pts
        d = _point_to_bezier_distance(px, py, sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty)
        if d < best_d:
            best_d = d
            edge_for_cb = (from_id, to_id, edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
            visual_key = (from_id, to_id, fp, tp)
            best_result = (edge_for_cb, visual_key)
    return best_result


def _arrow_head(
    tip_x: float,
    tip_y: float,
    from_x: float,
    from_y: float,
    *,
    highlight: bool = False,
    link_style: ResolvedLinkStyle,
) -> cv.Path:
    """Filled triangle arrow at (tip_x, tip_y) pointing in direction from (from_x, from_y) toward tip."""
    paint = link_style.arrow_paint_highlight if highlight else link_style.arrow_paint
    dx = tip_x - from_x
    dy = tip_y - from_y
    dist = (dx * dx + dy * dy) ** 0.5 or 1
    fx = dx / dist
    fy = dy / dist
    px, py = -fy, fx
    bx = tip_x - link_style.arrow_length * fx
    by = tip_y - link_style.arrow_length * fy
    left_x = bx + link_style.arrow_half_width * px
    left_y = by + link_style.arrow_half_width * py
    right_x = bx - link_style.arrow_half_width * px
    right_y = by - link_style.arrow_half_width * py
    return cv.Path(
        paint=paint,
        elements=[
            cv.Path.MoveTo(x=tip_x, y=tip_y),
            cv.Path.LineTo(x=left_x, y=left_y),
            cv.Path.LineTo(x=right_x, y=right_y),
            cv.Path.Close(),
        ],
    )


def _build_single_edge_shapes(
    positions: dict[str, tuple[float, float]],
    from_id: str,
    to_id: str,
    *,
    from_port: str = "0",
    to_port: str = "0",
    arrows: bool = True,
    highlight: bool = False,
    link_style: ResolvedLinkStyle | None = None,
    from_size: tuple[int, int] = (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT),
    to_size: tuple[int, int] = (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT),
    port_layout: dict[str, tuple[int, int]] | None = None,
) -> list[cv.Shape]:
    """Build path + optional arrow for one edge. Returns [path_shape] or [path_shape, arrow_shape]."""
    if link_style is None:
        link_style = get_link_style(get_default_style_config()[1], "default")
    pts = _edge_bezier_points(
        positions, from_id, to_id,
        from_port=from_port, to_port=to_port,
        from_size=from_size, to_size=to_size,
        port_layout=port_layout or {},
    )
    if pts is None:
        return []
    sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty = pts
    path_paint = link_style.edge_paint_highlight if highlight else link_style.edge_paint
    path_shape = cv.Path(
        paint=path_paint,
        elements=[
            cv.Path.MoveTo(x=sx, y=sy),
            cv.Path.CubicTo(cp1x=cp1x, cp1y=cp1y, cp2x=cp2x, cp2y=cp2y, x=tx, y=ty),
        ],
    )
    shapes = [path_shape]
    if arrows:
        shapes.append(_arrow_head(tx, ty, cp2x, cp2y, highlight=highlight, link_style=link_style))
    return shapes


def _build_edge_shapes(
    positions: dict[str, tuple[float, float]],
    edges: list[EdgeTuple],
    *,
    arrows: bool = True,
    port_layout: dict[str, tuple[int, int]] | None = None,
) -> list[cv.Shape]:
    """Build edge paths and optionally arrowheads for all edges."""
    out: list[cv.Shape] = []
    for edge in edges:
        from_id, to_id = edge[0], edge[1]
        fp, tp = (edge[2], edge[3]) if len(edge) > 3 else ("0", "0")
        out.extend(_build_single_edge_shapes(
            positions, from_id, to_id,
            from_port=fp, to_port=tp,
            arrows=arrows, port_layout=port_layout,
        ))
    return out


def build_graph_canvas(
    page: ft.Page,
    graph: ProcessGraph,
    *,
    style_config: GraphStyleConfig | None = None,
    on_right_click_link: Optional[Callable[[EdgeTuple], None]] = None,
    on_right_click_node: Optional[Callable[[str], None]] = None,
    on_node_drag_start: Optional[Callable[[str], None]] = None,
    on_node_drag_end: Optional[Callable[[str], None]] = None,
) -> ft.Control:
    """
    Build the process graph: Canvas (edges) + Stack of draggable nodes.
    style_config: (node_styles, link_styles) for per-type styling; None = defaults.
    on_right_click_link: called with (from_id, to_id, from_port, to_port) when right-click over a link.
    on_right_click_node: called with unit_id when right-click over a node.
    Returns a Container. State is held in closures for drag/refresh.
    """
    positions, edges = get_graph_layout_for_canvas(graph)
    # One-time build costs: canvas size O(n), one container per node O(n), index O(n+e), edge shapes O(e).
    # Size canvas and dotted background to fit graph; keep minimum for small graphs.
    if positions:
        max_x = max(p[0] for p in positions.values())
        max_y = max(p[1] for p in positions.values())
        canvas_w = max(CANVAS_WIDTH, int(max_x + DEFAULT_NODE_WIDTH + CANVAS_LAYOUT_MARGIN))
        canvas_h = max(CANVAS_HEIGHT, int(max_y + DEFAULT_NODE_HEIGHT + CANVAS_LAYOUT_MARGIN))
    else:
        canvas_w, canvas_h = CANVAS_WIDTH, CANVAS_HEIGHT

    node_styles, link_styles = style_config or get_default_style_config()
    node_containers: dict[str, ft.Container] = {}
    canvas_ref: list[cv.Canvas] = []
    drag_start: dict[str, tuple[float, float, float, float]] = {}
    last_drag_update_time: list[float] = [0.0]
    edge_shapes_cache: dict[EdgeTuple, list[cv.Shape]] = {}
    port_layout: dict[str, tuple[int, int]] = {}
    node_sizes_map: dict[str, tuple[int, int]] = {}

    def _link_style_for_edge(from_id: str, _to_id: str) -> ResolvedLinkStyle:
        """Edge color matches the source (from) unit's border color."""
        unit = graph.get_unit(from_id)
        from_type = unit.type if unit else "default"
        return get_link_style_from_node_border(node_styles, from_type)

    def get_all_edge_shapes(
        arrows: bool,
        invalidate_node_id: str | None = None,
        no_arrows_for_node_id: str | None = None,
        hovered_edge: EdgeTuple | None = None,
    ) -> list[cv.Shape]:
        """Build full list of edge shapes (flat). Delegates to get_all_edge_shapes_per_edge and flattens."""
        per_edge = get_all_edge_shapes_per_edge(
            arrows=arrows,
            invalidate_node_id=invalidate_node_id,
            no_arrows_for_node_id=no_arrows_for_node_id,
            hovered_edge=hovered_edge,
        )
        return [s for shapes in per_edge for s in shapes]

    def get_all_edge_shapes_per_edge(
        arrows: bool,
        invalidate_node_id: str | None = None,
        no_arrows_for_node_id: str | None = None,
        hovered_edge: EdgeTuple | None = None,
    ) -> list[list[cv.Shape]]:
        """Build one list of shapes per edge (same order as edges). Used for partial updates on drag_start."""
        visual_ports = _visual_ports()
        result: list[list[cv.Shape]] = []

        for i, edge in enumerate(edges):
            from_id, to_id = edge[0], edge[1]
            vfp, vtp = visual_ports[i] if i < len(visual_ports) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
            if from_id not in positions or to_id not in positions:
                result.append([])
                continue
            key: EdgeTuple = (from_id, to_id, vfp, vtp)
            if invalidate_node_id is None or from_id == invalidate_node_id or to_id == invalidate_node_id:
                edge_link_style = _link_style_for_edge(from_id, to_id)
                edge_shapes_cache[key] = _build_single_edge_shapes(
                    positions, from_id, to_id,
                    from_port=vfp, to_port=vtp,
                    arrows=True, highlight=False, link_style=edge_link_style,
                    from_size=node_sizes_map.get(from_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)),
                    to_size=node_sizes_map.get(to_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)),
                    port_layout=port_layout,
                )
            edge_link_style = _link_style_for_edge(from_id, to_id)
            from_sz = node_sizes_map.get(from_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
            to_sz = node_sizes_map.get(to_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
            if key not in edge_shapes_cache:
                edge_shapes_cache[key] = _build_single_edge_shapes(
                    positions, from_id, to_id,
                    from_port=vfp, to_port=vtp,
                    arrows=True, highlight=False, link_style=edge_link_style,
                    from_size=from_sz, to_size=to_sz, port_layout=port_layout,
                )
            highlight = key == hovered_edge
            no_arrows = no_arrows_for_node_id is not None and (from_id == no_arrows_for_node_id or to_id == no_arrows_for_node_id)
            if highlight:
                shapes = _build_single_edge_shapes(
                    positions, from_id, to_id,
                    from_port=vfp, to_port=vtp,
                    arrows=True, highlight=True, link_style=edge_link_style,
                    from_size=from_sz, to_size=to_sz, port_layout=port_layout,
                )
            else:
                shapes = edge_shapes_cache[key]
            if no_arrows:
                result.append(shapes[:1])
            else:
                result.append(shapes if arrows else shapes[:1])
        return result

    # Per-edge shape lists so we can patch only connected edges on drag_start (avoid full rebuild).
    shapes_per_edge_ref: list[list[list[cv.Shape]] | None] = [None]

    # Graph index: spatial grids, order map, cached visual_ports, O(1) edge visual_key -> index. Rebuilt on drag_end.
    index_ref: list[GraphIndex | None] = [None]

    def _visual_ports() -> list[tuple[str, str]]:
        """Cached visual ports from index, or compute once when index not yet built."""
        idx = index_ref[0]
        return idx.visual_ports if idx is not None else compute_visual_ports(edges, port_layout)

    hovered_edge_ref: list[tuple[EdgeTuple, EdgeTuple] | None] = [None]  # (edge_for_callback, visual_key_for_highlight)
    hovered_node_ref: list[str | None] = [None]
    hover_request_id: list[int] = [0]

    def _get_shapes_for_edge_index(
        edge_index: int,
        no_arrows: bool = False,
        highlight: bool = False,
    ) -> list[cv.Shape]:
        """Build shapes for a single edge by index (for drag_start and hover partial updates)."""
        if edge_index < 0 or edge_index >= len(edges):
            return []
        edge = edges[edge_index]
        from_id, to_id = edge[0], edge[1]
        vp = _visual_ports()
        vfp, vtp = vp[edge_index] if edge_index < len(vp) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
        link_style = _link_style_for_edge(from_id, to_id)
        from_sz = node_sizes_map.get(from_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
        to_sz = node_sizes_map.get(to_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
        return _build_single_edge_shapes(
            positions, from_id, to_id,
            from_port=vfp, to_port=vtp,
            arrows=not no_arrows, highlight=highlight, link_style=link_style,
            from_size=from_sz, to_size=to_sz, port_layout=port_layout,
        )

    def _edge_visual_key_to_index(visual_key: EdgeTuple | None) -> int | None:
        """O(1) edge index from visual key when index exists; else linear scan fallback."""
        idx = index_ref[0]
        if idx is not None:
            return idx.edge_index_for_visual_key(visual_key)
        if visual_key is None:
            return None
        vp = _visual_ports()
        for i, edge in enumerate(edges):
            if edge[0] not in positions or edge[1] not in positions:
                continue
            vfp, vtp = vp[i] if i < len(vp) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
            if (edge[0], edge[1], vfp, vtp) == visual_key:
                return i
        return None

    def update_node_highlight(hovered_id: str | None, prev_hovered_id: str | None = None) -> None:
        """Update highlight on at most two nodes: prev and current hovered. Then update only those containers."""
        uids_to_update = {hovered_id, prev_hovered_id} - {None}
        for uid in uids_to_update:
            inner = node_inner_containers.get(uid)
            s = node_style_by_id.get(uid)
            if inner is None or s is None:
                continue
            if uid == hovered_id:
                inner.bgcolor = s.bg_highlight
                inner.border = ft.border.all(1, s.border_highlight)
            else:
                inner.bgcolor = s.bgcolor
                inner.border = ft.border.all(1, s.border_color)
            inner.update()
        # Update only the affected node containers (so parent repaints)
        for uid in uids_to_update:
            cont = node_containers.get(uid)
            if cont is not None:
                cont.update()

    def _safe_canvas_update() -> None:
        """Update canvas; no-op if control is no longer on page (e.g. user navigated away)."""
        if not canvas_ref:
            return
        try:
            canvas_ref[0].update()
        except RuntimeError:
            pass

    def refresh_edges(invalidate_node_id: str | None = None) -> None:
        if not canvas_ref:
            return
        hovered_visual = hovered_edge_ref[0][1] if hovered_edge_ref[0] else None
        if invalidate_node_id is not None and shapes_per_edge_ref[0] is not None:
            # Only rebuild shapes for edges connected to the moved node (O(degree) instead of O(e)).
            connected = node_to_edge_indices.get(invalidate_node_id, [])
            for i in connected:
                highlight = hovered_visual is not None and _edge_visual_key_to_index(hovered_visual) == i
                shapes_per_edge_ref[0][i] = _get_shapes_for_edge_index(i, no_arrows=False, highlight=highlight)
            canvas_ref[0].shapes = [s for shapes in shapes_per_edge_ref[0] for s in shapes]
        else:
            per_edge = get_all_edge_shapes_per_edge(
                arrows=True,
                invalidate_node_id=invalidate_node_id,
                no_arrows_for_node_id=None,
                hovered_edge=hovered_visual,
            )
            shapes_per_edge_ref[0] = per_edge
            canvas_ref[0].shapes = [s for shapes in per_edge for s in shapes]
        _safe_canvas_update()

    def refresh_edges_hover_only(prev_visual_key: EdgeTuple | None, new_visual_key: EdgeTuple | None) -> None:
        """Update only the prev and new hovered edge shapes (no full rebuild)."""
        if not canvas_ref or shapes_per_edge_ref[0] is None:
            refresh_edges()
            return
        indices_to_patch: list[int] = []
        if prev_visual_key is not None:
            pi = _edge_visual_key_to_index(prev_visual_key)
            if pi is not None:
                indices_to_patch.append(pi)
        new_idx = _edge_visual_key_to_index(new_visual_key) if new_visual_key else None
        if new_idx is not None and new_idx not in indices_to_patch:
            indices_to_patch.append(new_idx)
        for i in indices_to_patch:
            highlight = new_idx == i
            shapes_per_edge_ref[0][i] = _get_shapes_for_edge_index(i, no_arrows=False, highlight=highlight)
        canvas_ref[0].shapes = [s for shapes in shapes_per_edge_ref[0] for s in shapes]
        _safe_canvas_update()

    def on_drag_start(unit_id: str, e: ft.DragStartEvent) -> None:
        cont = node_containers.get(unit_id)
        if cont is not None:
            drag_start[unit_id] = (
                cont.left or 0,
                cont.top or 0,
                e.global_position.x,
                e.global_position.y,
            )
        if on_node_drag_start is not None:
            try:
                on_node_drag_start(unit_id)
            except Exception:
                pass
        if canvas_ref and shapes_per_edge_ref[0] is not None:
            # Only rebuild shapes for edges connected to the dragged node (line only, no arrows).
            connected_indices = node_to_edge_indices.get(unit_id, [])
            for i in connected_indices:
                shapes_per_edge_ref[0][i] = _get_shapes_for_edge_index(i, no_arrows=True)
            canvas_ref[0].shapes = [s for shapes in shapes_per_edge_ref[0] for s in shapes]
            _safe_canvas_update()

    def on_drag_end(unit_id: str) -> None:
        if cont := node_containers.get(unit_id):
            # Persist new coordinates into graph.layout so positions survive refresh/save.
            # layout is optional; create it lazily on first manual move.
            try:
                if graph.layout is None:
                    graph.layout = {}
                graph.layout[unit_id] = NodePosition(x=float(cont.left or 0.0), y=float(cont.top or 0.0))
            except Exception:
                # Best-effort: dragging should never crash the UI
                pass
            cont.update()
        if on_node_drag_end is not None:
            try:
                on_node_drag_end(unit_id)
            except Exception:
                pass
        refresh_edges(invalidate_node_id=unit_id)
        # Rebuild index so hover uses updated positions after drag.
        index_ref[0] = build_graph_index(
            positions,
            node_ids_order,
            node_sizes_map,
            edges,
            port_layout,
            _get_edge_bbox,
            cell_size=GRID_DEFAULT_CELL_SIZE,
            default_width=DEFAULT_NODE_WIDTH,
            default_height=DEFAULT_NODE_HEIGHT,
            edge_hover_threshold=EDGE_HOVER_THRESHOLD,
        )
        try:
            page.update(canvas_ref[0])
        except RuntimeError:
            pass

    def on_node_drag(unit_id: str, e: ft.DragUpdateEvent) -> None:
        cont = node_containers.get(unit_id)
        if cont is None:
            return
        start = drag_start.get(unit_id)
        if start is None:
            # Fallback if on_pan_start didn't fire first: use current position and this event as start
            drag_start[unit_id] = (
                cont.left or 0,
                cont.top or 0,
                e.global_position.x,
                e.global_position.y,
            )
            return
        start_left, start_top, start_gx, start_gy = start
        cont.left = start_left + (e.global_position.x - start_gx)
        cont.top = start_top + (e.global_position.y - start_gy)
        positions[unit_id] = (cont.left, cont.top)
        now = time.perf_counter()
        if now - last_drag_update_time[0] >= DRAG_UPDATE_INTERVAL_S:
            last_drag_update_time[0] = now
            page.update(cont)  # Scoped update: only repaint the dragged node

    node_style_by_id: dict[str, ResolvedNodeStyle] = {}
    node_inner_containers: dict[str, ft.Container] = {}
    visual_units = [u for u in graph.units if not _is_hidden_unit_type(u.type)]
    visual_unit_ids = {u.id for u in visual_units}
    node_ids_order = [u.id for u in visual_units]
    node_controls: list[ft.Control] = []
    for u in visual_units:
        uid = u.id
        left, top = positions.get(uid, (0.0, 0.0))
        style = get_node_style(node_styles, u.type)
        node_style_by_id[uid] = style
        n_in, n_out = _get_port_counts(u, graph)
        port_layout[uid] = (n_in, n_out)
        conn_in, conn_out = _get_connected_port_indices(uid, graph)
        inner, w, h = _build_node_content(u, style, n_in, n_out, conn_in, conn_out)
        node_sizes_map[uid] = (w, h)
        node_inner_containers[uid] = inner
        cont = ft.Container(
            content=ft.GestureDetector(
                content=inner,
                drag_interval=NODE_DRAG_INTERVAL_MS,
                on_pan_start=lambda e, id=uid: on_drag_start(id, e),
                on_pan_update=lambda e, id=uid: on_node_drag(id, e),
                on_pan_end=lambda e, id=uid: on_drag_end(id),
            ),
            left=left,
            top=top,
        )
        node_containers[uid] = cont
        node_controls.append(cont)

    # Hide edges to/from hidden container nodes (defensive; they should not exist).
    edges[:] = [e for e in edges if e[0] in visual_unit_ids and e[1] in visual_unit_ids]

    # Precompute node -> edge indices so on_drag_start and refresh_edges avoid O(e) scan (use O(degree)).
    node_to_edge_indices: dict[str, list[int]] = {}
    for i, edge in enumerate(edges):
        node_to_edge_indices.setdefault(edge[0], []).append(i)
        node_to_edge_indices.setdefault(edge[1], []).append(i)

    def _get_edge_bbox(
        edge_index: int,
        from_id: str,
        to_id: str,
        from_port: str,
        to_port: str,
    ) -> tuple[float, float, float, float] | None:
        from_sz = node_sizes_map.get(from_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
        to_sz = node_sizes_map.get(to_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
        return _edge_bbox(
            positions, from_id, to_id,
            from_port=from_port, to_port=to_port,
            from_size=from_sz, to_size=to_sz,
            port_layout=port_layout,
        )

    index_ref[0] = build_graph_index(
        positions,
        node_ids_order,
        node_sizes_map,
        edges,
        port_layout,
        _get_edge_bbox,
        cell_size=GRID_DEFAULT_CELL_SIZE,
        default_width=DEFAULT_NODE_WIDTH,
        default_height=DEFAULT_NODE_HEIGHT,
        edge_hover_threshold=EDGE_HOVER_THRESHOLD,
    )

    initial_shapes_per_edge = get_all_edge_shapes_per_edge(arrows=True, invalidate_node_id=None)
    shapes_per_edge_ref[0] = initial_shapes_per_edge
    initial_edge_shapes = [s for shapes in initial_shapes_per_edge for s in shapes]
    stack = ft.Stack(controls=node_controls, expand=True)
    canvas = cv.Canvas(
        width=canvas_w,
        height=canvas_h,
        shapes=initial_edge_shapes,
        content=stack,
    )
    canvas_ref.append(canvas)

    # Grid as background SVG (one static layer) so canvas only redraws edges
    grid_svg = _build_dot_grid_svg(canvas_w, canvas_h, GRID_DEFAULT_CELL_SIZE, radius=DOT_RADIUS)
    grid_b64 = base64.b64encode(grid_svg.encode()).decode()
    grid_image = ft.Image(
        src=f"data:image/svg+xml;base64,{grid_b64}",
        width=canvas_w,
        height=canvas_h,
    )
    grid_layer = ft.Container(content=grid_image, width=canvas_w, height=canvas_h)
    canvas_container = ft.Container(
        content=canvas,
        width=canvas_w,
        height=canvas_h,
        bgcolor=None,
    )

    def _apply_hover_result(
        node: str | None,
        edge: tuple[str, str] | None,
        prev_node: str | None,
    ) -> None:
        changed = (edge != hovered_edge_ref[0]) or (node != prev_node)
        if edge != hovered_edge_ref[0]:
            prev_visual_key = hovered_edge_ref[0][1] if hovered_edge_ref[0] else None
            new_visual_key = edge[1] if edge else None
            hovered_edge_ref[0] = edge
            refresh_edges_hover_only(prev_visual_key, new_visual_key)
        if node != prev_node:
            hovered_node_ref[0] = node
            update_node_highlight(node, prev_hovered_id=prev_node)
        if changed and canvas_ref:
            try:
                page.update(canvas_ref[0])
            except RuntimeError:
                pass

    def on_canvas_hover_xy(x: float, y: float) -> None:
        if not HOVER_HIT_TEST_IN_THREAD:
            idx = index_ref[0]
            vp = _visual_ports()
            ng = idx.node_grid if idx is not None else None
            eg = idx.edge_grid if idx is not None else None
            if ng is not None:
                node_candidates = ng.query(x, y)
            elif positions and node_sizes_map:
                node_candidates = build_node_grid(
                    positions, node_sizes_map,
                    cell_size=GRID_DEFAULT_CELL_SIZE,
                    default_width=DEFAULT_NODE_WIDTH,
                    default_height=DEFAULT_NODE_HEIGHT,
                ).query(x, y)
            else:
                node_candidates = set()
            order_map = idx.node_order_map if idx is not None else None
            node = _node_at_point(
                positions, node_ids_order, x, y,
                node_sizes=node_sizes_map, candidates=node_candidates, order_map=order_map,
            )
            edge_candidates: set[int] | None = None
            if node is None and eg is not None:
                edge_candidates = eg.query(x, y)
            elif node is None and edges:
                eg_built = IndexGrid(cell_size=GRID_DEFAULT_CELL_SIZE)
                for i, edge in enumerate(edges):
                    from_id, to_id = edge[0], edge[1]
                    fp, tp = vp[i] if i < len(vp) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
                    from_sz = node_sizes_map.get(from_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
                    to_sz = node_sizes_map.get(to_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))
                    bbox = _edge_bbox(
                        positions, from_id, to_id,
                        from_port=fp, to_port=tp,
                        from_size=from_sz, to_size=to_sz,
                        port_layout=port_layout,
                    )
                    if bbox is not None:
                        min_x, min_y, max_x, max_y = bbox
                        eg_built.insert(i, min_x, min_y, max_x, max_y, expand_by=EDGE_HOVER_THRESHOLD)
                edge_candidates = eg_built.query(x, y)
            edge = (
                _edge_at_point(
                    positions, edges, x, y,
                    node_sizes=node_sizes_map, port_layout=port_layout, visual_ports=vp,
                    candidate_indices=edge_candidates,
                )
                if node is None
                else None
            )
            _apply_hover_result(node, edge, hovered_node_ref[0])
            return

        hover_request_id[0] += 1
        my_id = hover_request_id[0]
        positions_snapshot = dict(positions)
        edges_snapshot = list(edges)
        node_ids_snapshot = list(node_ids_order)
        idx = index_ref[0]
        vp_snapshot = idx.visual_ports if idx is not None else compute_visual_ports(edges_snapshot, port_layout)

        async def _hover_task() -> None:
            node, edge = await asyncio.to_thread(
                _hover_hit_test_thread,
                positions_snapshot,
                edges_snapshot,
                node_ids_snapshot,
                node_sizes_map,
                port_layout,
                vp_snapshot,
                x,
                y,
                node_grid=idx.node_grid if idx is not None else None,
                edge_grid=idx.edge_grid if idx is not None else None,
                node_order_map=idx.node_order_map if idx is not None else None,
            )
            if my_id != hover_request_id[0]:
                return
            prev_node = hovered_node_ref[0]
            _apply_hover_result(node, edge, prev_node)

        page.run_task(_hover_task)

    def on_canvas_exit() -> None:
        prev_node = hovered_node_ref[0]
        had_edge = hovered_edge_ref[0] is not None
        if had_edge:
            prev_visual_key = hovered_edge_ref[0][1]
            hovered_edge_ref[0] = None
            refresh_edges_hover_only(prev_visual_key, None)
        if prev_node is not None:
            hovered_node_ref[0] = None
            update_node_highlight(None, prev_hovered_id=prev_node)
        if had_edge or prev_node is not None:
            try:
                page.update(canvas_ref[0])
            except RuntimeError:
                pass

    # Wrap canvas (and nodes) in hover detector; nodes are inside so they still get pan/drag first.
    canvas_with_hover = wrap_hover(
        canvas_container,
        on_canvas_hover_xy,
        on_exit=on_canvas_exit,
        hover_interval=CANVAS_HOVER_INTERVAL_MS,
    )

    # Stack: grid (back) -> canvas with hover (front). Nodes inside canvas get hit first for drag.
    canvas_with_grid = ft.Stack(
        controls=[grid_layer, canvas_with_hover],
        width=canvas_w,
        height=canvas_h,
    )

    # Pan/scroll (and zoom) via InteractiveViewer
    viewer = ft.InteractiveViewer(
        content=ft.Container(
            content=canvas_with_grid,
            width=canvas_w,
            height=canvas_h,
            bgcolor=CANVAS_BG,
        ),
        constrained=False,
        pan_enabled=True,
        scale_enabled=True,
        min_scale=0.5,
        max_scale=3.0,
    )
    # Right-click over node -> on_right_click_node(uid); over link -> on_right_click_link(edge)
    result_content: ft.Control = viewer
    if on_right_click_node is not None or on_right_click_link is not None:
        def _on_secondary_tap(_e: ft.ControlEvent) -> None:
            if hovered_node_ref[0] is not None and on_right_click_node is not None:
                on_right_click_node(hovered_node_ref[0])
            elif hovered_edge_ref[0] is not None and on_right_click_link is not None:
                on_right_click_link(hovered_edge_ref[0][0])
        result_content = ft.GestureDetector(
            content=viewer,
            on_secondary_tap_down=_on_secondary_tap,
        )
    return ft.Container(
        content=result_content,
        expand=True,
        bgcolor=CANVAS_BG,
    )


# Alias for callers that expect a "GraphCanvas" name
GraphCanvas = build_graph_canvas
