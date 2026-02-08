# Drawing lines in Flet (research summary + current implementation)

How to draw **connection lines between nodes** in a pure Flet process graph (no WebView). Flet provides a **Canvas** API that supports lines and paths; shapes can be updated dynamically.

---

## 1. Flet Canvas and shapes

- **Module:** `import flet.canvas as cv` (and `import flet as ft`).
- **Control:** `cv.Canvas(width=..., height=..., shapes=[...])` — draws a list of shapes.
- **Key:** The `shapes` list is mutable. Change it and call `canvas.update()` to redraw (see [Canvas docs](https://docs.flet.dev/controls/canvas/)).

Canvas can have **content** (a child control drawn on top of the shapes), so you can use:

```text
Canvas(shapes=[...edges...], content=Stack([...nodes...]))
```

Edges are drawn first; nodes sit on top.

---

## 2. Drawing straight lines

Use **`cv.Line`** with start and end coordinates:

```python
import flet as ft
import flet.canvas as cv

cv.Line(
    x1=50, y1=50,   # start
    x2=200, y2=150, # end
    paint=ft.Paint(stroke_width=2, color=ft.Colors.GREY_700),
)
```

- **Properties:** `x1`, `y1`, `x2`, `y2`, `paint`.
- **Paint:** `ft.Paint(stroke_width=..., color=..., stroke_cap=..., stroke_join=...)`. Lines are always stroked (fill style is ignored).
- **Docs:** [Line](https://docs.flet.dev/controls/canvas/line).

For each connection between two nodes, create one `cv.Line` from (source center or right edge) to (target center or left edge). When node positions change (e.g. after drag), rebuild the list of `cv.Line` shapes and call `canvas.update()`.

---

## 3. Curved lines and paths

For Bezier curves or multi-segment paths use **`cv.Path`** with a list of **path elements**:

- **`cv.Path.MoveTo(x, y)`** — start of path.
- **`cv.Path.LineTo(x, y)`** — straight segment to point.
- **`cv.Path.QuadraticTo(cp1x, cp1y, x, y, w=1)`** — quadratic Bezier to `(x,y)` with one control point.
- **`cv.Path.CubicTo(cp1x, cp1y, cp2x, cp2y, x, y)`** — cubic Bezier with two control points.
- **`cv.Path.Close()`** — close the current sub-path.

Example (stroke only, no fill):

```python
cv.Path(
    paint=ft.Paint(stroke_width=2, style=ft.PaintingStyle.STROKE),
    elements=[
        cv.Path.MoveTo(x=50, y=50),
        cv.Path.QuadraticTo(cp1x=125, cp1y=0, x=200, y=50, w=1),
    ],
)
```

**Docs:** [Path](https://docs.flet.dev/controls/canvas/path).

Use paths when you want curved connectors or need to draw arrowheads (e.g. a small triangle at the end of each edge).

---

## 4. Dynamic updates (redraw when nodes move)

The official **free-hand drawing** example shows the pattern:

1. Keep a reference to the canvas: `canvas = cv.Canvas(shapes=[...], content=...)`.
2. When node positions change (e.g. drag end):
   - Rebuild the edge shapes from current positions.
   - Assign: `canvas.shapes = edge_shapes`.
3. Call **`canvas.update()`** so the canvas redraws.

So: **no CustomPaint or separate painter class** — you update the `shapes` list and call `update()`.

---

## 5. Coordinate system and node positions

- Canvas coordinates are in **logical pixels**, origin top-left. So `(x, y)` is the same space you use for positioning nodes (e.g. `ft.Container(left=x, top=y, ...)` inside a `Stack`).
- For **line endpoints** you need the **edge of each node** (e.g. right edge of source, left edge of target), or the **center** of each node. If a node is a `Container` with `width=120`, `height=50`, then:
  - Center: `(left + 60, top + 25)`.
  - Right edge center: `(left + 120, top + 25)`.
  - Left edge center: `(left, top + 25)`.
- Store each node’s **current (left, top)** (or center) when building the graph and when handling drag; use those values to build the `cv.Line` (or `cv.Path`) list for the canvas.

---

## 6. Arrowheads

There is no built-in “arrow” shape. You can:

- **Straight line only:** use `cv.Line` from source edge to target edge (no arrowhead).
- **Arrowhead:** draw a small triangle at the target point using **`cv.Path`**: e.g. `MoveTo` at tip, `LineTo` to two corners of the triangle, `Close()`, filled with the same color as the line. Compute the tip and corners from the line angle (e.g. direction vector and perpendicular for the base).

---

## 7. Current implementation

The process graph is implemented under **`gui/flet/components/workflow/`**:

- **`flow_layout.py`** — Layout only (no drawing).
- **`graph_canvas.py`** — Canvas, edges, nodes, drag, pan/zoom.

### 7.1 Layout (`flow_layout.py`)

- **`_layered_layout(unit_list, conn_list)`** — Left-to-right layered layout; returns `unit_id -> (x, y)`.
- **`get_graph_layout_for_canvas(graph)`** — Returns `(positions, edges)`:
  - `positions`: `unit_id -> (left, top)` (top-left of each node), shifted so no node is above/left of `CANVAS_LAYOUT_MARGIN` (60).
  - `edges`: list of `(from_id, to_id)`.
- Node dimensions used by the canvas are fixed: **NODE_WIDTH=120**, **NODE_HEIGHT=50** (defined in `graph_canvas.py`).

### 7.2 Canvas and edges (`graph_canvas.py`)

- **Entry point:** `build_graph_canvas(page, graph, on_right_click=None)` → `ft.Container` (expand=True).
- **Canvas structure:** One `cv.Canvas` with:
  - **`shapes`** — List of `cv.Path` (one cubic Bezier per edge + one filled `cv.Path` triangle per arrowhead). Edge path goes from source right-mid `(x1+NODE_WIDTH, y1+NODE_HEIGHT/2)` to target left-mid `(x2, y2+NODE_HEIGHT/2)` with `CubicTo` and `EDGE_CURVE_FACTOR=0.25` for the control-point offset.
  - **`content`** — `ft.Stack` of positioned node `Container`s (each node: `GestureDetector` with `_build_node_content(unit)` for type, id, optional “(control)” badge).
- **Paint:** `EDGE_PAINT` (stroke, GREY_500), `ARROW_PAINT` (fill, GREY_500). Arrow: triangle at target with `ARROW_LENGTH=12`, `ARROW_HALF_WIDTH=5`.

### 7.3 Drag and redraw

- **Node drag:** Each node is a `Container` with `left`/`top` inside a `GestureDetector` (`on_pan_start`, `on_pan_update`, `on_pan_end`). Drag uses **global** position deltas so movement is correct regardless of zoom/pan.
- **`positions`** is a mutable dict; on `on_pan_update` we set `positions[unit_id] = (cont.left, cont.top)` so edge math uses the latest position.
- **Edge cache:** `edge_shapes_cache[(from_id, to_id)]` stores `[path_shape, arrow_shape]`. On **drag start** we redraw all edges but omit arrows for edges connected to the dragged node (less flicker). On **drag end** we invalidate only edges incident to that node and call `canvas.shapes = get_all_edge_shapes(...)` then `canvas.update()`.
- **Throttling:** Node position is updated at most every `DRAG_UPDATE_INTERVAL_S` (0.1s) during drag; `drag_interval=80` on `GestureDetector` reduces event rate.

### 7.4 Grid and pan/zoom

- **Grid:** Dot grid is **not** drawn with canvas shapes. It’s a single **base64 SVG** image (`_build_dot_grid_svg`) with circles (spacing `GRID_SPACING=56`, `DOT_RADIUS=0.8`). That image is placed in a bottom layer of a `Stack`; the canvas (edges + nodes) is the top layer. This keeps canvas redraws cheap (edges only).
- **Pan/zoom:** An **`InteractiveViewer`** wraps the stack (grid + canvas). `pan_enabled=True`, `scale_enabled=True`, `min_scale=0.5`, `max_scale=3.0`. Canvas has fixed size `CANVAS_WIDTH=1600`, `CANVAS_HEIGHT=1200`.
- **Right-click:** Optional `on_right_click` is handled by a `GestureDetector` wrapping the viewer (e.g. to open “Remove link” dialog), so the secondary tap is not consumed by the viewer.

### 7.5 File and constant summary

| Item | Location / value |
|------|-------------------|
| Layout | `flow_layout.py`: `_layered_layout`, `get_graph_layout_for_canvas`, `CANVAS_LAYOUT_MARGIN=60` |
| Canvas + nodes | `graph_canvas.py`: `build_graph_canvas`, `_build_node_content`, `_build_single_edge_shapes`, `_arrow_head` |
| Node size | `NODE_WIDTH=120`, `NODE_HEIGHT=50` |
| Edge curve | Cubic Bezier, `EDGE_CURVE_FACTOR=0.25` |
| Canvas size | `CANVAS_WIDTH=1600`, `CANVAS_HEIGHT=1200` |
| Grid | `_build_dot_grid_svg`, base64 SVG in separate layer |
| Drag throttle | `DRAG_UPDATE_INTERVAL_S=1/10`; `GestureDetector(drag_interval=80)` |

---

## 8. References

- [Flet Canvas](https://docs.flet.dev/controls/canvas/)
- [Flet Line](https://docs.flet.dev/controls/canvas/line)
- [Flet Path](https://docs.flet.dev/controls/canvas/path)
- [Flet Paint](https://docs.flet.dev/types/paint)
- Free-hand drawing example (Canvas page): shows `canvas.shapes.append(cv.Line(...))` and `canvas.update()` for dynamic lines.
