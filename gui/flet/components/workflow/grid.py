"""
Spatial grid for fast node hit-test during hover.
Reduces node lookups from O(n) to O(1) cell lookup + O(k) rect checks where k = nodes in cell.
"""
from __future__ import annotations

# Default cell size; should be on the order of typical node size so most cells contain few nodes.
DEFAULT_CELL_SIZE = 40


class NodeGrid:
    """
    2D grid mapping (x, y) to node IDs that overlap that cell.
    Used to restrict hover hit-test to only nodes in the cell under the pointer.
    """

    __slots__ = ("_cell_size", "_cells")

    def __init__(self, cell_size: int | float = DEFAULT_CELL_SIZE) -> None:
        self._cell_size = float(cell_size)
        # (cell_x, cell_y) -> set of node ids
        self._cells: dict[tuple[int, int], set[str]] = {}

    def clear(self) -> None:
        """Remove all nodes from the grid."""
        self._cells.clear()

    def insert(self, uid: str, left: float, top: float, width: float, height: float) -> None:
        """Add a node's bounding box to all cells it overlaps."""
        if width <= 0 or height <= 0:
            return
        cs = self._cell_size
        cx_lo = int(left // cs)
        cx_hi = int((left + width) // cs)
        cy_lo = int(top // cs)
        cy_hi = int((top + height) // cs)
        for cx in range(cx_lo, cx_hi + 1):
            for cy in range(cy_lo, cy_hi + 1):
                key = (cx, cy)
                if key not in self._cells:
                    self._cells[key] = set()
                self._cells[key].add(uid)

    def query(self, px: float, py: float) -> set[str]:
        """Return node IDs in the cell containing (px, py). May be empty."""
        cx = int(px // self._cell_size)
        cy = int(py // self._cell_size)
        return self._cells.get((cx, cy), set()).copy()


def build_node_grid(
    positions: dict[str, tuple[float, float]],
    node_sizes: dict[str, tuple[int, int]],
    *,
    cell_size: int | float = DEFAULT_CELL_SIZE,
    default_width: int = 200,
    default_height: int = 60,
) -> NodeGrid:
    """Build a NodeGrid from positions and node sizes. Use for hover hit-test."""
    grid = NodeGrid(cell_size=cell_size)
    for uid, (left, top) in positions.items():
        w, h = node_sizes.get(uid, (default_width, default_height))
        grid.insert(uid, left, top, float(w), float(h))
    return grid


class IndexGrid:
    """
    2D grid mapping (x, y) to integer indices (e.g. edge indices) that overlap that cell.
    Bboxes can be expanded by expand_by so nearby cells are included (e.g. for edge hover threshold).
    """

    __slots__ = ("_cell_size", "_cells")

    def __init__(self, cell_size: int | float = DEFAULT_CELL_SIZE) -> None:
        self._cell_size = float(cell_size)
        self._cells: dict[tuple[int, int], set[int]] = {}

    def insert(
        self,
        index: int,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        *,
        expand_by: float = 0,
    ) -> None:
        """Add a bbox (min_x, min_y, max_x, max_y) to all cells it overlaps. expand_by expands the bbox."""
        if expand_by != 0:
            min_x -= expand_by
            min_y -= expand_by
            max_x += expand_by
            max_y += expand_by
        width = max_x - min_x
        height = max_y - min_y
        if width <= 0 or height <= 0:
            return
        cs = self._cell_size
        cx_lo = int(min_x // cs)
        cx_hi = int(max_x // cs)
        cy_lo = int(min_y // cs)
        cy_hi = int(max_y // cs)
        for cx in range(cx_lo, cx_hi + 1):
            for cy in range(cy_lo, cy_hi + 1):
                key = (cx, cy)
                if key not in self._cells:
                    self._cells[key] = set()
                self._cells[key].add(index)

    def query(self, px: float, py: float) -> set[int]:
        """Return indices in the cell containing (px, py). May be empty."""
        cx = int(px // self._cell_size)
        cy = int(py // self._cell_size)
        return self._cells.get((cx, cy), set()).copy()
