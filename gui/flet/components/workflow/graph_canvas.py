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

from schemas.process_graph import NodePosition, ProcessGraph, Unit

from gui.flet.components.workflow.flow_layout import EdgeTuple, get_graph_layout_for_canvas
from gui.flet.components.workflow.graph_style_config import (
    DEFAULT_NODE_HEIGHT,
    DEFAULT_NODE_WIDTH,
    PORT_DOT_RADIUS,
    PORT_ROW_HEIGHT,
    get_default_style_config,
    get_link_style,
    get_node_style,
    GraphStyleConfig,
    LINK_TYPE_INCOMING_RL,
    LINK_TYPE_OUTGOING_CONTROL,
    ResolvedLinkStyle,
    ResolvedNodeStyle,
)
from gui.flet.tools.gestures import wrap_hover

# Canvas size for scroll/pan (fixed so InteractiveViewer can pan)
CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 1200
GRID_SPACING = 56  # Sparse grid for performance (~600 dots)
DOT_RADIUS = 0.8  # Smaller = 1.0 or 0.75; larger = 1.5 or 2
DRAG_UPDATE_INTERVAL_S = 1 / 10  # Throttle node redraws during drag to reduce lag
# Run hover hit-test in a thread so UI doesn't block (disable if no threads, e.g. Pyodide)
HOVER_HIT_TEST_IN_THREAD = True
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
    body_height = max(style.height, port_rows * PORT_ROW_HEIGHT)
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
            alignment=ft.MainAxisAlignment.CENTER,
        )
        if margin_left or margin_right:
            return ft.Container(
                content=col,
                margin=ft.Margin.only(left=margin_left, right=margin_right),
            )
        return col

    # Position port columns so dots straddle the border (half inside, half outside)
    left_col = _port_column(n_inputs, connected_in, margin_left=-PORT_DOT_RADIUS)
    right_col = _port_column(n_outputs, connected_out, margin_right=-PORT_DOT_RADIUS)
    inner = ft.Row(
        [left_col, content, right_col],
        spacing=4,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    control = ft.Container(
        content=inner,
        width=style.width,
        height=body_height,
        padding=8,
        border=ft.border.all(1, style.border_color),
        border_radius=style.border_radius,
        bgcolor=style.bgcolor,
        clip_behavior=ft.ClipBehavior.NONE,  # Let port dots overflow the border
    )
    return control, style.width, body_height


def _port_y_offset(port_index: int, port_count: int, node_height: int) -> float:
    """Return Y offset from node top to center of port (port_index 0-based)."""
    if port_count <= 0:
        return node_height / 2
    return (port_index + 0.5) * (node_height / port_count)


def _is_hidden_unit_type(unit_type: str) -> bool:
    return str(unit_type).lower() in _HIDDEN_UNIT_TYPES


def _build_dot_grid_svg(
    width: int,
    height: int,
    spacing: int,
    radius: float = DOT_RADIUS,
    fill: str = GRID_DOT_COLOR_HEX,
) -> str:
    """Dot grid as SVG string (one asset, no canvas shapes). Reduces canvas redraw load."""
    circles: list[str] = []
    x = spacing // 2
    while x < width:
        y = spacing // 2
        while y < height:
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
) -> tuple[str | None, EdgeTuple | None]:
    """Run in a thread: return (node_id, edge_key) for hover at (x, y). Uses only passed-in data."""
    node = _node_at_point(
        positions_snapshot, node_ids_order, x, y, node_sizes=node_sizes_map
    )
    edge = (
        _edge_at_point(
            positions_snapshot, edges, x, y,
            node_sizes=node_sizes_map, port_layout=port_layout, visual_ports=visual_ports,
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
) -> str | None:
    """Return the topmost node id that contains (px, py), or None. node_ids_order = draw order (last = top)."""
    for uid in reversed(node_ids_order):
        if uid not in positions:
            continue
        left, top = positions[uid]
        w, h = (node_sizes.get(uid, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT))) if node_sizes else (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)
        if left <= px <= left + w and top <= py <= top + h:
            return uid
    return None


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
) -> tuple[EdgeTuple, EdgeTuple] | None:
    """Return ((edge_for_callback, visual_key_for_highlight)) of nearest edge, or None.
    edge_for_callback: actual (from_id, to_id, from_port, to_port) for remove dialog.
    visual_key_for_highlight: (from_id, to_id, vfp, vtp) for highlight comparison."""
    def size(uid: str) -> tuple[int, int]:
        return node_sizes.get(uid, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)) if node_sizes else (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)

    best_result: tuple[EdgeTuple, EdgeTuple] | None = None
    best_d = threshold + 1.0
    pl = port_layout or {}
    vp = visual_ports or []
    for i, edge in enumerate(edges):
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


def _compute_visual_ports(
    edges: list[EdgeTuple],
    port_layout: dict[str, tuple[int, int]],
) -> list[tuple[str, str]]:
    """Assign visual port indices. Single edge: use its actual ports. Multiple between same pair: spread across slots."""
    from collections import defaultdict

    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, edge in enumerate(edges):
        groups[(edge[0], edge[1])].append(i)

    result: list[tuple[str, str]] = [("0", "0")] * len(edges)
    for (from_id, to_id), indices in groups.items():
        n_out = port_layout.get(from_id, (1, 1))[1]
        n_in = port_layout.get(to_id, (1, 1))[0]
        if len(indices) == 1:
            # Single edge: use actual ports (clamped to available)
            idx = indices[0]
            e = edges[idx]
            fp = e[2] if len(e) > 2 else "0"
            tp = e[3] if len(e) > 3 else "0"
            try:
                fi = min(int(fp), n_out - 1) if n_out else 0
                ti = min(int(tp), n_in - 1) if n_in else 0
                result[idx] = (str(fi), str(ti))
            except (ValueError, TypeError):
                result[idx] = ("0", "0")
        else:
            # Multiple edges: spread across slots
            for slot, idx in enumerate(indices):
                vfp = str(slot % n_out) if n_out else "0"
                vtp = str(slot % n_in) if n_in else "0"
                result[idx] = (vfp, vtp)
    return result


def _link_type_for_edge(graph: ProcessGraph, from_id: str, to_id: str) -> str:
    """Return link type for styling: incoming to RL Agent (green), outgoing to control (orange), else default."""
    to_unit = graph.get_unit(to_id)
    from_unit = graph.get_unit(from_id)
    if to_unit and to_unit.type == "RLAgent":
        return LINK_TYPE_INCOMING_RL
    if from_unit and from_unit.type == "RLAgent" and to_unit and to_unit.controllable:
        return LINK_TYPE_OUTGOING_CONTROL
    return "default"


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
    node_styles, link_styles = style_config or get_default_style_config()
    node_containers: dict[str, ft.Container] = {}
    canvas_ref: list[cv.Canvas] = []
    drag_start: dict[str, tuple[float, float, float, float]] = {}
    last_drag_update_time: list[float] = [0.0]
    edge_shapes_cache: dict[EdgeTuple, list[cv.Shape]] = {}
    port_layout: dict[str, tuple[int, int]] = {}
    node_sizes_map: dict[str, tuple[int, int]] = {}

    def get_all_edge_shapes(
        arrows: bool,
        invalidate_node_id: str | None = None,
        no_arrows_for_node_id: str | None = None,
        hovered_edge: EdgeTuple | None = None,
    ) -> list[cv.Shape]:
        """Build full list of edge shapes. Visual ports spread multiple edges across slots."""
        link_type_cache = {(e[0], e[1]): _link_type_for_edge(graph, e[0], e[1]) for e in edges}
        visual_ports = _compute_visual_ports(edges, port_layout)

        for i, edge in enumerate(edges):
            from_id, to_id = edge[0], edge[1]
            vfp, vtp = visual_ports[i] if i < len(visual_ports) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
            if from_id not in positions or to_id not in positions:
                continue
            if invalidate_node_id is not None and from_id != invalidate_node_id and to_id != invalidate_node_id:
                continue
            key: EdgeTuple = (from_id, to_id, vfp, vtp)
            edge_link_style = get_link_style(link_styles, link_type_cache[(from_id, to_id)])
            edge_shapes_cache[key] = _build_single_edge_shapes(
                positions, from_id, to_id,
                from_port=vfp, to_port=vtp,
                arrows=True, highlight=False, link_style=edge_link_style,
                from_size=node_sizes_map.get(from_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)),
                to_size=node_sizes_map.get(to_id, (DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT)),
                port_layout=port_layout,
            )
        out: list[cv.Shape] = []
        for i, edge in enumerate(edges):
            from_id, to_id = edge[0], edge[1]
            vfp, vtp = visual_ports[i] if i < len(visual_ports) else (edge[2] if len(edge) > 2 else "0", edge[3] if len(edge) > 3 else "0")
            key = (from_id, to_id, vfp, vtp)
            edge_link_style = get_link_style(link_styles, link_type_cache[(from_id, to_id)])
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
            if highlight:
                shapes = _build_single_edge_shapes(
                    positions, from_id, to_id,
                    from_port=vfp, to_port=vtp,
                    arrows=True, highlight=True, link_style=edge_link_style,
                    from_size=from_sz, to_size=to_sz, port_layout=port_layout,
                )
            else:
                shapes = edge_shapes_cache[key]
            if no_arrows_for_node_id is not None and (from_id == no_arrows_for_node_id or to_id == no_arrows_for_node_id):
                out.extend(shapes[:1])
            else:
                out.extend(shapes if arrows else shapes[:1])
        return out

    hovered_edge_ref: list[tuple[EdgeTuple, EdgeTuple] | None] = [None]  # (edge_for_callback, visual_key_for_highlight)
    hovered_node_ref: list[str | None] = [None]
    hover_request_id: list[int] = [0]

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
        canvas_ref[0].shapes = get_all_edge_shapes(
            arrows=True,
            invalidate_node_id=invalidate_node_id,
            hovered_edge=hovered_edge_ref[0][1] if hovered_edge_ref[0] else None,
        )
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
        if canvas_ref:
            # Keep arrows for all edges except those connected to the dragged node
            canvas_ref[0].shapes = get_all_edge_shapes(
                arrows=True,
                invalidate_node_id=None,
                no_arrows_for_node_id=unit_id,
                hovered_edge=hovered_edge_ref[0][1] if hovered_edge_ref[0] else None,
            )
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
                drag_interval=80,  # Fewer pan_update events = less Python/layout work during drag
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
    initial_edge_shapes = get_all_edge_shapes(arrows=True, invalidate_node_id=None)
    stack = ft.Stack(controls=node_controls, expand=True)
    canvas = cv.Canvas(
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
        shapes=initial_edge_shapes,
        content=stack,
    )
    canvas_ref.append(canvas)

    # Grid as background SVG (one static layer) so canvas only redraws edges
    grid_svg = _build_dot_grid_svg(CANVAS_WIDTH, CANVAS_HEIGHT, GRID_SPACING, radius=DOT_RADIUS)
    grid_b64 = base64.b64encode(grid_svg.encode()).decode()
    grid_image = ft.Image(
        src=f"data:image/svg+xml;base64,{grid_b64}",
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
    )
    grid_layer = ft.Container(content=grid_image, width=CANVAS_WIDTH, height=CANVAS_HEIGHT)
    canvas_container = ft.Container(
        content=canvas,
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
        bgcolor=None,
    )

    def _apply_hover_result(
        node: str | None,
        edge: tuple[str, str] | None,
        prev_node: str | None,
    ) -> None:
        changed = (edge != hovered_edge_ref[0]) or (node != prev_node)
        if edge != hovered_edge_ref[0]:
            hovered_edge_ref[0] = edge
            refresh_edges()
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
            vp = _compute_visual_ports(edges, port_layout)
            node = _node_at_point(positions, node_ids_order, x, y, node_sizes=node_sizes_map)
            edge = (
                _edge_at_point(
                    positions, edges, x, y,
                    node_sizes=node_sizes_map, port_layout=port_layout, visual_ports=vp,
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

        async def _hover_task() -> None:
            node, edge = await asyncio.to_thread(
                _hover_hit_test_thread,
                positions_snapshot,
                edges_snapshot,
                node_ids_snapshot,
        node_sizes_map,
        port_layout,
        _compute_visual_ports(edges_snapshot, port_layout),
        x,
        y,
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
            hovered_edge_ref[0] = None
            refresh_edges()
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
        hover_interval=50,
    )

    # Stack: grid (back) -> canvas with hover (front). Nodes inside canvas get hit first for drag.
    canvas_with_grid = ft.Stack(
        controls=[grid_layer, canvas_with_hover],
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
    )

    # Pan/scroll (and zoom) via InteractiveViewer
    viewer = ft.InteractiveViewer(
        content=ft.Container(
            content=canvas_with_grid,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
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
