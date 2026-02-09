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

from schemas.process_graph import ProcessGraph, Unit

from gui.flet.components.workflow.flow_layout import get_graph_layout_for_canvas
from gui.flet.components.workflow.graph_style_config import (
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

NODE_WIDTH = 120
NODE_HEIGHT = 50
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


def _build_node_content(unit: Unit, style: ResolvedNodeStyle) -> ft.Control:
    """Build the inner content for one process unit (type, id, optional control badge)."""
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
    return ft.Container(
        content=content,
        width=style.width,
        height=style.height,
        padding=8,
        border=ft.border.all(1, style.border_color),
        border_radius=style.border_radius,
        bgcolor=style.bgcolor,
    )


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
    from_size: tuple[int, int] = (NODE_WIDTH, NODE_HEIGHT),
    to_size: tuple[int, int] = (NODE_WIDTH, NODE_HEIGHT),
) -> tuple[float, float, float, float, float, float, float, float] | None:
    """Return (sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty) for the edge curve, or None."""
    if from_id not in positions or to_id not in positions:
        return None
    x1, y1 = positions[from_id]
    x2, y2 = positions[to_id]
    fw, fh = from_size
    tw, th = to_size
    sx = x1 + fw
    sy = y1 + fh / 2
    tx = x2
    ty = y2 + th / 2
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
    edges: list[tuple[str, str]],
    node_ids_order: list[str],
    node_sizes_map: dict[str, tuple[int, int]],
    x: float,
    y: float,
) -> tuple[str | None, tuple[str, str] | None]:
    """Run in a thread: return (node_id, edge_key) for hover at (x, y). Uses only passed-in data."""
    node = _node_at_point(
        positions_snapshot, node_ids_order, x, y, node_sizes=node_sizes_map
    )
    edge = (
        _edge_at_point(positions_snapshot, edges, x, y, node_sizes=node_sizes_map)
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
        w, h = (node_sizes.get(uid, (NODE_WIDTH, NODE_HEIGHT))) if node_sizes else (NODE_WIDTH, NODE_HEIGHT)
        if left <= px <= left + w and top <= py <= top + h:
            return uid
    return None


def _edge_at_point(
    positions: dict[str, tuple[float, float]],
    edges: list[tuple[str, str]],
    px: float,
    py: float,
    threshold: float = EDGE_HOVER_THRESHOLD,
    *,
    node_sizes: dict[str, tuple[int, int]] | None = None,
) -> tuple[str, str] | None:
    """Return (from_id, to_id) of the edge nearest to (px, py) within threshold, or None."""
    def size(uid: str) -> tuple[int, int]:
        return node_sizes.get(uid, (NODE_WIDTH, NODE_HEIGHT)) if node_sizes else (NODE_WIDTH, NODE_HEIGHT)

    best_key: tuple[str, str] | None = None
    best_d = threshold + 1.0
    for from_id, to_id in edges:
        pts = _edge_bezier_points(
            positions, from_id, to_id,
            from_size=size(from_id), to_size=size(to_id),
        )
        if pts is None:
            continue
        sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty = pts
        d = _point_to_bezier_distance(px, py, sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty)
        if d < best_d:
            best_d = d
            best_key = (from_id, to_id)
    return best_key


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
    arrows: bool = True,
    highlight: bool = False,
    link_style: ResolvedLinkStyle | None = None,
    from_size: tuple[int, int] = (NODE_WIDTH, NODE_HEIGHT),
    to_size: tuple[int, int] = (NODE_WIDTH, NODE_HEIGHT),
) -> list[cv.Shape]:
    """Build path + optional arrow for one edge. Returns [path_shape] or [path_shape, arrow_shape]."""
    if link_style is None:
        link_style = get_link_style(get_default_style_config()[1], "default")
    if from_id not in positions or to_id not in positions:
        return []
    x1, y1 = positions[from_id]
    x2, y2 = positions[to_id]
    fw, fh = from_size
    tw, th = to_size
    sx = x1 + fw
    sy = y1 + fh / 2
    tx = x2
    ty = y2 + th / 2
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
        shapes.append(
            _arrow_head(tx, ty, cp2x, cp2y, highlight=highlight, link_style=link_style)
        )
    return shapes


def _build_edge_shapes(
    positions: dict[str, tuple[float, float]],
    edges: list[tuple[str, str]],
    *,
    arrows: bool = True,
) -> list[cv.Shape]:
    """Build edge paths and optionally arrowheads for all edges."""
    out: list[cv.Shape] = []
    for from_id, to_id in edges:
        out.extend(_build_single_edge_shapes(positions, from_id, to_id, arrows=arrows))
    return out


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
    on_right_click_link: Optional[Callable[[tuple[str, str]], None]] = None,
    on_right_click_node: Optional[Callable[[str], None]] = None,
) -> ft.Control:
    """
    Build the process graph: Canvas (edges) + Stack of draggable nodes.
    style_config: (node_styles, link_styles) for per-type styling; None = defaults.
    on_right_click_link: called with (from_id, to_id) when right-click over a link.
    on_right_click_node: called with unit_id when right-click over a node.
    Returns a Container. State is held in closures for drag/refresh.
    """
    positions, edges = get_graph_layout_for_canvas(graph)
    node_styles, link_styles = style_config or get_default_style_config()
    node_containers: dict[str, ft.Container] = {}
    canvas_ref: list[cv.Canvas] = []  # single-element list so we can assign in closure
    drag_start: dict[str, tuple[float, float, float, float]] = {}
    last_drag_update_time: list[float] = [0.0]  # throttle: only redraw node at ~60fps
    edge_shapes_cache: dict[tuple[str, str], list[cv.Shape]] = {}

    def get_all_edge_shapes(
        arrows: bool,
        invalidate_node_id: str | None = None,
        no_arrows_for_node_id: str | None = None,
        hovered_edge: tuple[str, str] | None = None,
    ) -> list[cv.Shape]:
        """Build full list of edge shapes; only recompute edges incident to invalidate_node_id.
        Cache always stores [path, arrow]. no_arrows_for_node_id: omit arrows only for edges connected to that node (e.g. during drag).
        hovered_edge: (from_id, to_id) to draw with highlight paint."""
        node_sizes = {uid: (s.width, s.height) for uid, s in node_style_by_id.items()}
        link_type_cache = {(_f, _t): _link_type_for_edge(graph, _f, _t) for _f, _t in edges}

        for from_id, to_id in edges:
            if from_id not in positions or to_id not in positions:
                continue
            if invalidate_node_id is not None and from_id != invalidate_node_id and to_id != invalidate_node_id:
                continue
            edge_link_style = get_link_style(link_styles, link_type_cache[(from_id, to_id)])
            edge_shapes_cache[(from_id, to_id)] = _build_single_edge_shapes(
                positions, from_id, to_id,
                arrows=True, highlight=False, link_style=edge_link_style,
                from_size=node_sizes.get(from_id, (NODE_WIDTH, NODE_HEIGHT)),
                to_size=node_sizes.get(to_id, (NODE_WIDTH, NODE_HEIGHT)),
            )
        out: list[cv.Shape] = []
        for from_id, to_id in edges:
            key = (from_id, to_id)
            edge_link_style = get_link_style(link_styles, link_type_cache[key])
            from_sz = node_sizes.get(from_id, (NODE_WIDTH, NODE_HEIGHT))
            to_sz = node_sizes.get(to_id, (NODE_WIDTH, NODE_HEIGHT))
            if key not in edge_shapes_cache:
                edge_shapes_cache[key] = _build_single_edge_shapes(
                    positions, from_id, to_id,
                    arrows=True, highlight=False, link_style=edge_link_style,
                    from_size=from_sz, to_size=to_sz,
                )
            highlight = key == hovered_edge
            if highlight:
                shapes = _build_single_edge_shapes(
                    positions, from_id, to_id,
                    arrows=True, highlight=True, link_style=edge_link_style,
                    from_size=from_sz, to_size=to_sz,
                )
            else:
                shapes = edge_shapes_cache[key]
            if no_arrows_for_node_id is not None and (from_id == no_arrows_for_node_id or to_id == no_arrows_for_node_id):
                out.extend(shapes[:1])  # path only for edges connected to dragged node
            else:
                out.extend(shapes if arrows else shapes[:1])
        return out

    hovered_edge_ref: list[tuple[str, str] | None] = [None]
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

    def refresh_edges(invalidate_node_id: str | None = None) -> None:
        if not canvas_ref:
            return
        canvas_ref[0].shapes = get_all_edge_shapes(
            arrows=True,
            invalidate_node_id=invalidate_node_id,
            hovered_edge=hovered_edge_ref[0],
        )
        canvas_ref[0].update()

    def on_drag_start(unit_id: str, e: ft.DragStartEvent) -> None:
        cont = node_containers.get(unit_id)
        if cont is not None:
            drag_start[unit_id] = (
                cont.left or 0,
                cont.top or 0,
                e.global_position.x,
                e.global_position.y,
            )
        if canvas_ref:
            # Keep arrows for all edges except those connected to the dragged node
            canvas_ref[0].shapes = get_all_edge_shapes(
                arrows=True,
                invalidate_node_id=None,
                no_arrows_for_node_id=unit_id,
                hovered_edge=hovered_edge_ref[0],
            )
            canvas_ref[0].update()

    def on_drag_end(unit_id: str) -> None:
        if cont := node_containers.get(unit_id):
            cont.update()
        refresh_edges(invalidate_node_id=unit_id)
        page.update(canvas_ref[0])

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
    node_ids_order = [u.id for u in graph.units]
    node_controls: list[ft.Control] = []
    for u in graph.units:
        uid = u.id
        left, top = positions.get(uid, (0.0, 0.0))
        style = get_node_style(node_styles, u.type)
        node_style_by_id[uid] = style
        inner = _build_node_content(u, style)
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
            page.update(canvas_ref[0])

    def on_canvas_hover_xy(x: float, y: float) -> None:
        if not HOVER_HIT_TEST_IN_THREAD:
            node_sizes_map = {uid: (s.width, s.height) for uid, s in node_style_by_id.items()}
            node = _node_at_point(positions, node_ids_order, x, y, node_sizes=node_sizes_map)
            edge = (
                _edge_at_point(positions, edges, x, y, node_sizes=node_sizes_map)
                if node is None
                else None
            )
            _apply_hover_result(node, edge, hovered_node_ref[0])
            return

        node_sizes_map = {uid: (s.width, s.height) for uid, s in node_style_by_id.items()}
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
            page.update(canvas_ref[0])

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
                on_right_click_link(hovered_edge_ref[0])
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
