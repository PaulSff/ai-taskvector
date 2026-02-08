"""
Pure Flet process graph: Canvas for edges + draggable Node controls.
Grid is drawn as a background SVG (one asset) to reduce canvas load; canvas holds only edges.
"""
from __future__ import annotations

import base64
import time
from typing import Callable, Optional

import flet as ft
import flet.canvas as cv

from schemas.process_graph import ProcessGraph, Unit

from gui.flet.components.workflow.flow_layout import get_graph_layout_for_canvas
from gui.flet.tools.gestures import wrap_hover

NODE_WIDTH = 120
NODE_HEIGHT = 50
# Canvas size for scroll/pan (fixed so InteractiveViewer can pan)
CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 1200
GRID_SPACING = 56  # Sparse grid for performance (~600 dots)
DOT_RADIUS = 0.8  # Smaller = 1.0 or 0.75; larger = 1.5 or 2
DRAG_UPDATE_INTERVAL_S = 1 / 10  # Throttle node redraws during drag to reduce lag
# Dark theme: edges and node styling
EDGE_STROKE_WIDTH = 1  # Connector lines; use 1 for thinner, 3 for thicker
EDGE_PAINT = ft.Paint(stroke_width=EDGE_STROKE_WIDTH, color=ft.Colors.GREY_500, style=ft.PaintingStyle.STROKE)
ARROW_PAINT = ft.Paint(style=ft.PaintingStyle.FILL, color=ft.Colors.GREY_500)
EDGE_PAINT_HIGHLIGHT = ft.Paint(stroke_width=EDGE_STROKE_WIDTH, color=ft.Colors.BLUE_400, style=ft.PaintingStyle.STROKE)
ARROW_PAINT_HIGHLIGHT = ft.Paint(style=ft.PaintingStyle.FILL, color=ft.Colors.BLUE_400)
ARROW_LENGTH = 12
ARROW_HALF_WIDTH = 5
# Grid: drawn as background SVG (not canvas shapes) to reduce redraw cost
GRID_DOT_COLOR_HEX = "#616161"  # Material grey 700, matches ft.Colors.GREY_700
NODE_BG = ft.Colors.GREY_800
NODE_BORDER = ft.Colors.GREY_600
NODE_BG_HIGHLIGHT = ft.Colors.GREY_700
NODE_BORDER_HIGHLIGHT = ft.Colors.BLUE_400
NODE_TEXT = ft.Colors.WHITE
NODE_TEXT_SECONDARY = ft.Colors.GREY_400
CANVAS_BG = ft.Colors.GREY_900


def _build_node_content(unit: Unit) -> ft.Control:
    """Build the inner content for one process unit (type, id, optional control badge)."""
    controls = [
        ft.Text(unit.type, size=14, weight=ft.FontWeight.BOLD, color=NODE_TEXT),
        ft.Text(unit.id, size=11, color=NODE_TEXT_SECONDARY),
    ]
    if unit.controllable:
        controls.append(ft.Text("(control)", size=10, color=ft.Colors.BLUE_300))
    return ft.Container(
        content=ft.Column(controls, tight=True, spacing=2),
        width=NODE_WIDTH,
        height=NODE_HEIGHT,
        padding=8,
        border=ft.border.all(1, NODE_BORDER),
        border_radius=6,
        bgcolor=NODE_BG,
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
) -> tuple[float, float, float, float, float, float, float, float] | None:
    """Return (sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty) for the edge curve, or None."""
    if from_id not in positions or to_id not in positions:
        return None
    x1, y1 = positions[from_id]
    x2, y2 = positions[to_id]
    sx = x1 + NODE_WIDTH
    sy = y1 + NODE_HEIGHT / 2
    tx = x2
    ty = y2 + NODE_HEIGHT / 2
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
    samples: int = 24,
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


def _node_at_point(
    positions: dict[str, tuple[float, float]],
    node_ids_order: list[str],
    px: float,
    py: float,
) -> str | None:
    """Return the topmost node id that contains (px, py), or None. node_ids_order = draw order (last = top)."""
    for uid in reversed(node_ids_order):
        if uid not in positions:
            continue
        left, top = positions[uid]
        if left <= px <= left + NODE_WIDTH and top <= py <= top + NODE_HEIGHT:
            return uid
    return None


def _edge_at_point(
    positions: dict[str, tuple[float, float]],
    edges: list[tuple[str, str]],
    px: float,
    py: float,
    threshold: float = EDGE_HOVER_THRESHOLD,
) -> tuple[str, str] | None:
    """Return (from_id, to_id) of the edge nearest to (px, py) within threshold, or None."""
    best_key: tuple[str, str] | None = None
    best_d = threshold + 1.0
    for from_id, to_id in edges:
        pts = _edge_bezier_points(positions, from_id, to_id)
        if pts is None:
            continue
        sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty = pts
        d = _point_to_bezier_distance(px, py, sx, sy, cp1x, cp1y, cp2x, cp2y, tx, ty)
        if d < best_d:
            best_d = d
            best_key = (from_id, to_id)
    return best_key


def _arrow_head(
    tip_x: float, tip_y: float, from_x: float, from_y: float, *, highlight: bool = False
) -> cv.Path:
    """Filled triangle arrow at (tip_x, tip_y) pointing in direction from (from_x, from_y) toward tip."""
    paint = ARROW_PAINT_HIGHLIGHT if highlight else ARROW_PAINT
    dx = tip_x - from_x
    dy = tip_y - from_y
    dist = (dx * dx + dy * dy) ** 0.5 or 1
    fx = dx / dist
    fy = dy / dist
    # Perpendicular (right-hand side)
    px = -fy
    py = fx
    # Base corners: tip - length*forward ± half_width*perp
    bx = tip_x - ARROW_LENGTH * fx
    by = tip_y - ARROW_LENGTH * fy
    left_x = bx + ARROW_HALF_WIDTH * px
    left_y = by + ARROW_HALF_WIDTH * py
    right_x = bx - ARROW_HALF_WIDTH * px
    right_y = by - ARROW_HALF_WIDTH * py
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
) -> list[cv.Shape]:
    """Build path + optional arrow for one edge. Returns [path_shape] or [path_shape, arrow_shape]."""
    if from_id not in positions or to_id not in positions:
        return []
    x1, y1 = positions[from_id]
    x2, y2 = positions[to_id]
    sx = x1 + NODE_WIDTH
    sy = y1 + NODE_HEIGHT / 2
    tx = x2
    ty = y2 + NODE_HEIGHT / 2
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
    path_paint = EDGE_PAINT_HIGHLIGHT if highlight else EDGE_PAINT
    path_shape = cv.Path(
        paint=path_paint,
        elements=[
            cv.Path.MoveTo(x=sx, y=sy),
            cv.Path.CubicTo(cp1x=cp1x, cp1y=cp1y, cp2x=cp2x, cp2y=cp2y, x=tx, y=ty),
        ],
    )
    shapes = [path_shape]
    if arrows:
        shapes.append(_arrow_head(tx, ty, cp2x, cp2y, highlight=highlight))
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


def build_graph_canvas(
    page: ft.Page,
    graph: ProcessGraph,
    *,
    on_right_click: Optional[Callable[[], None]] = None,
) -> ft.Control:
    """
    Build the process graph: Canvas (edges) + Stack of draggable nodes.
    Returns a Container. State is held in closures for drag/refresh.
    """
    positions, edges = get_graph_layout_for_canvas(graph)
    node_containers: dict[str, ft.Container] = {}
    canvas_ref: list[cv.Canvas] = []  # single-element list so we can assign in closure
    drag_start: dict[str, tuple[float, float, float, float]] = {}
    last_drag_update_time: list[float] = [0.0]  # throttle: only redraw node at ~60fps
    # Cache: (from_id, to_id) -> [path_shape, arrow_shape]. Only edges connected to dragged node are recomputed.
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
        for from_id, to_id in edges:
            if from_id not in positions or to_id not in positions:
                continue
            if invalidate_node_id is not None and from_id != invalidate_node_id and to_id != invalidate_node_id:
                continue
            edge_shapes_cache[(from_id, to_id)] = _build_single_edge_shapes(
                positions, from_id, to_id, arrows=True, highlight=False
            )
        out: list[cv.Shape] = []
        for from_id, to_id in edges:
            key = (from_id, to_id)
            if key not in edge_shapes_cache:
                edge_shapes_cache[key] = _build_single_edge_shapes(
                    positions, from_id, to_id, arrows=True, highlight=False
                )
            highlight = key == hovered_edge
            if highlight:
                shapes = _build_single_edge_shapes(
                    positions, from_id, to_id, arrows=True, highlight=True
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

    def update_node_highlight(hovered_id: str | None) -> None:
        for uid, inner in node_inner_containers.items():
            if uid == hovered_id:
                inner.bgcolor = NODE_BG_HIGHLIGHT
                inner.border = ft.border.all(1, NODE_BORDER_HIGHLIGHT)
            else:
                inner.bgcolor = NODE_BG
                inner.border = ft.border.all(1, NODE_BORDER)
        for inner in node_inner_containers.values():
            inner.update()

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

    node_inner_containers: dict[str, ft.Container] = {}
    node_ids_order = [u.id for u in graph.units]
    node_controls: list[ft.Control] = []
    for u in graph.units:
        uid = u.id
        left, top = positions.get(uid, (0.0, 0.0))
        inner = _build_node_content(u)
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

    def on_canvas_hover_xy(x: float, y: float) -> None:
        edge = _edge_at_point(positions, edges, x, y)
        node = _node_at_point(positions, node_ids_order, x, y)
        if edge != hovered_edge_ref[0]:
            hovered_edge_ref[0] = edge
            refresh_edges()
        if node != hovered_node_ref[0]:
            hovered_node_ref[0] = node
            update_node_highlight(node)
            page.update()

    def on_canvas_exit() -> None:
        if hovered_edge_ref[0] is not None:
            hovered_edge_ref[0] = None
            refresh_edges()
        if hovered_node_ref[0] is not None:
            hovered_node_ref[0] = None
            update_node_highlight(None)
            page.update()

    # Wrap canvas (and nodes) in hover detector; nodes are inside so they still get pan/drag first.
    canvas_with_hover = wrap_hover(
        canvas_container,
        on_canvas_hover_xy,
        on_exit=on_canvas_exit,
        hover_interval=30,
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
    # Right-click: wrap so secondary tap is handled outside viewer content (reduces lag)
    result_content: ft.Control = viewer
    if on_right_click is not None:
        result_content = ft.GestureDetector(
            content=viewer,
            on_secondary_tap_down=lambda e: on_right_click(),
        )
    return ft.Container(
        content=result_content,
        expand=True,
        bgcolor=CANVAS_BG,
    )


# Alias for callers that expect a "GraphCanvas" name
GraphCanvas = build_graph_canvas
