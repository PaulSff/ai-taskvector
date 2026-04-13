"""
Graph index for fast hover/gesture: node and edge spatial grids, draw order, and cached visual ports.
Built once at canvas build (and rebuilt on drag_end); hover only does O(1) cell query + O(k) checks.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from gui.components.workflow.flow_layout import EdgeTuple
from gui.components.workflow.grid import (
    DEFAULT_CELL_SIZE,
    IndexGrid,
    NodeGrid,
    build_node_grid,
)


def compute_visual_ports(
    edges: list[EdgeTuple],
    port_layout: dict[str, tuple[int, int]],
) -> list[tuple[str, str]]:
    """Assign visual port indices per edge. Single edge: use its ports; multiple between same pair: spread across slots."""
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, edge in enumerate(edges):
        groups[(edge[0], edge[1])].append(i)

    result: list[tuple[str, str]] = [("0", "0")] * len(edges)
    for (from_id, to_id), indices in groups.items():
        n_out = port_layout.get(from_id, (1, 1))[1]
        n_in = port_layout.get(to_id, (1, 1))[0]
        if len(indices) == 1:
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
            for slot, idx in enumerate(indices):
                vfp = str(slot % n_out) if n_out else "0"
                vtp = str(slot % n_in) if n_in else "0"
                result[idx] = (vfp, vtp)
    return result


# Visual key for an edge: (from_id, to_id, from_port, to_port) used for highlight/callback.
VisualKey = tuple[str, str, str, str]


class GraphIndex:
    """Holds spatial grids, node order map, cached visual ports, and O(1) edge visual key -> index."""

    __slots__ = (
        "node_grid",
        "edge_grid",
        "node_order_map",
        "visual_ports",
        "visual_key_to_edge_index",
    )

    def __init__(
        self,
        *,
        node_grid: NodeGrid,
        edge_grid: IndexGrid,
        node_order_map: dict[str, int],
        visual_ports: list[tuple[str, str]],
        visual_key_to_edge_index: dict[VisualKey, int],
    ) -> None:
        self.node_grid = node_grid
        self.edge_grid = edge_grid
        self.node_order_map = node_order_map
        self.visual_ports = visual_ports
        self.visual_key_to_edge_index = visual_key_to_edge_index

    def edge_index_for_visual_key(self, visual_key: VisualKey | None) -> int | None:
        """O(1) lookup for edge index from (from_id, to_id, from_port, to_port)."""
        if visual_key is None:
            return None
        return self.visual_key_to_edge_index.get(visual_key)


# Callback: (edge_index, from_id, to_id, from_port, to_port) -> (min_x, min_y, max_x, max_y) or None
GetEdgeBbox = Callable[[int, str, str, str, str], tuple[float, float, float, float] | None]


def build_graph_index(
    positions: dict[str, tuple[float, float]],
    node_ids_order: list[str],
    node_sizes_map: dict[str, tuple[int, int]],
    edges: list[EdgeTuple],
    port_layout: dict[str, tuple[int, int]],
    get_edge_bbox: GetEdgeBbox,
    *,
    cell_size: int | float = DEFAULT_CELL_SIZE,
    default_width: int = 200,
    default_height: int = 60,
    edge_hover_threshold: float = 20.0,
) -> GraphIndex:
    """Build node grid, edge grid, order map, cached visual ports, and visual_key -> edge index."""
    node_order_map = {uid: i for i, uid in enumerate(node_ids_order)}
    node_grid = build_node_grid(
        positions,
        node_sizes_map,
        cell_size=cell_size,
        default_width=default_width,
        default_height=default_height,
    )
    visual_ports = compute_visual_ports(edges, port_layout)
    edge_grid = IndexGrid(cell_size=cell_size)
    visual_key_to_edge_index: dict[VisualKey, int] = {}
    for i, edge in enumerate(edges):
        from_id, to_id = edge[0], edge[1]
        fp = visual_ports[i][0] if i < len(visual_ports) else (edge[2] if len(edge) > 2 else "0")
        tp = visual_ports[i][1] if i < len(visual_ports) else (edge[3] if len(edge) > 3 else "0")
        bbox = get_edge_bbox(i, from_id, to_id, fp, tp)
        if bbox is not None:
            min_x, min_y, max_x, max_y = bbox
            edge_grid.insert(i, min_x, min_y, max_x, max_y, expand_by=edge_hover_threshold)
        if from_id in positions and to_id in positions:
            visual_key_to_edge_index[(from_id, to_id, fp, tp)] = i
    return GraphIndex(
        node_grid=node_grid,
        edge_grid=edge_grid,
        node_order_map=node_order_map,
        visual_ports=visual_ports,
        visual_key_to_edge_index=visual_key_to_edge_index,
    )
