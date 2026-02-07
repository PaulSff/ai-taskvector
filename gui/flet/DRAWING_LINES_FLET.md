# Drawing lines in Flet (research summary)

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
   - Rebuild the edge shapes from current positions:  
     `edge_shapes = [cv.Line(x1=sx, y1=sy, x2=tx, y2=ty, paint=...) for (sx,sy), (tx,ty) in ...]`
   - Assign: `canvas.shapes = edge_shapes` (or `canvas.shapes.clear()` then `canvas.shapes.extend(edge_shapes)`).
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

## 6. Optional: arrowheads

There is no built-in “arrow” shape. You can:

- **Straight line only:** use `cv.Line` from source edge to target edge (no arrowhead).
- **Arrowhead:** draw a small triangle at the target point using **`cv.Path`**: e.g. `MoveTo` at tip, `LineTo` to two corners of the triangle, `Close()`, filled with the same color as the line. Compute the tip and corners from the line angle (e.g. `atan2(y2 - y1, x2 - x1)`).

---

## 7. Suggested structure for the process graph

1. **Data:** From `ProcessGraph` you have units and connections. Use your existing **layered layout** (e.g. `flow_layout._layered_layout`) to get `(x, y)` for each unit.
2. **Canvas:** One `cv.Canvas` with:
   - `shapes` = list of `cv.Line` (or `cv.Path`) for each connection, computed from node positions.
   - `content` = `ft.Stack` with **positioned nodes** (e.g. `ft.Container(content=Node(...), left=x, top=y)` for each unit).
3. **Nodes:** Each node is a `ft.UserControl` (e.g. your `Node` with title + Edit), placed in the Stack with `left`/`top` from the layout (or from drag state).
4. **Drag:** When a node is dragged, update its `left`/`top`, then **recompute** all edge shapes from current node positions and set `canvas.shapes = new_edges`, then `canvas.update()`.
5. **Resize:** Canvas supports `on_resize`; you can use it to recenter or scale the graph if needed.

---

## 8. References

- [Flet Canvas](https://docs.flet.dev/controls/canvas/)
- [Flet Line](https://docs.flet.dev/controls/canvas/line)
- [Flet Path](https://docs.flet.dev/controls/canvas/path)
- [Flet Paint](https://docs.flet.dev/types/paint)
- Free-hand drawing example (Canvas page): shows `canvas.shapes.append(cv.Line(...))` and `canvas.update()` for dynamic lines.
