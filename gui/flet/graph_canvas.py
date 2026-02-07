"""
Pure Flet process graph: Canvas for edges + draggable Node controls.
Replaces the React Flow WebView approach. Uses no UserControl (removed in Flet 0.26+).
"""
from __future__ import annotations

import flet as ft
import flet.canvas as cv

from schemas.process_graph import ProcessGraph, Unit

from gui.flet.flow_layout import get_graph_layout_for_canvas

NODE_WIDTH = 120
NODE_HEIGHT = 50
EDGE_PAINT = ft.Paint(stroke_width=2, color=ft.Colors.GREY_600)


def _build_node_content(unit: Unit) -> ft.Control:
    """Build the inner content for one process unit (type, id, optional control badge)."""
    controls = [
        ft.Text(unit.type, size=14, weight=ft.FontWeight.BOLD),
        ft.Text(unit.id, size=11, color=ft.Colors.GREY_700),
    ]
    if unit.controllable:
        controls.append(ft.Text("(control)", size=10, color=ft.Colors.BLUE_600))
    return ft.Container(
        content=ft.Column(controls, tight=True, spacing=2),
        width=NODE_WIDTH,
        height=NODE_HEIGHT,
        padding=8,
        border=ft.border.all(1, ft.Colors.GREY_400),
        border_radius=6,
        bgcolor=ft.Colors.WHITE,
    )


def _build_edge_shapes(positions: dict[str, tuple[float, float]], edges: list[tuple[str, str]]) -> list[cv.Shape]:
    shapes: list[cv.Shape] = []
    for from_id, to_id in edges:
        if from_id not in positions or to_id not in positions:
            continue
        x1, y1 = positions[from_id]
        x2, y2 = positions[to_id]
        shapes.append(
            cv.Line(
                x1=x1 + NODE_WIDTH,
                y1=y1 + NODE_HEIGHT / 2,
                x2=x2,
                y2=y2 + NODE_HEIGHT / 2,
                paint=EDGE_PAINT,
            )
        )
    return shapes


def build_graph_canvas(page: ft.Page, graph: ProcessGraph) -> ft.Control:
    """
    Build the process graph: Canvas (edges) + Stack of draggable nodes.
    Returns a Container. State is held in closures for drag/refresh.
    """
    positions, edges = get_graph_layout_for_canvas(graph)
    node_containers: dict[str, ft.Container] = {}
    canvas_ref: list[cv.Canvas] = []  # single-element list so we can assign in closure

    def refresh_edges() -> None:
        if not canvas_ref:
            return
        canvas_ref[0].shapes = _build_edge_shapes(positions, edges)
        canvas_ref[0].update()

    def on_node_drag(unit_id: str, e: ft.DragUpdateEvent) -> None:
        cont = node_containers.get(unit_id)
        if cont is None:
            return
        left = cont.left or 0
        top = cont.top or 0
        cont.left = left + e.delta_x
        cont.top = top + e.delta_y
        positions[unit_id] = (cont.left, cont.top)
        refresh_edges()
        page.update()

    node_controls: list[ft.Control] = []
    for u in graph.units:
        uid = u.id
        left, top = positions.get(uid, (0.0, 0.0))
        cont = ft.Container(
            content=ft.GestureDetector(
                content=_build_node_content(u),
                drag_interval=10,
                on_pan_update=lambda e, id=uid: on_node_drag(id, e),
            ),
            left=left,
            top=top,
        )
        node_containers[uid] = cont
        node_controls.append(cont)

    edge_shapes = _build_edge_shapes(positions, edges)
    stack = ft.Stack(controls=node_controls, expand=True)
    canvas = cv.Canvas(
        width=float("inf"),
        expand=True,
        shapes=edge_shapes,
        content=stack,
    )
    canvas_ref.append(canvas)

    return ft.Container(
        content=canvas,
        expand=True,
        bgcolor=ft.Colors.GREY_100,
    )


# Alias for callers that expect a "GraphCanvas" name
GraphCanvas = build_graph_canvas
