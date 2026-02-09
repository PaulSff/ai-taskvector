# Graph canvas performance research

Research and applied optimizations for the Flet process graph (preview, dragging nodes, hover).

## Current architecture

- **Edges**: Flet `Canvas` with Bézier paths + arrow heads (one shape per edge).
- **Nodes**: Flet `Stack` of `Container` + `GestureDetector` + inner content; positions via `left`/`top`.
- **Grid**: Single SVG (base64) behind the canvas to avoid drawing grid on the canvas.
- **Pan/zoom**: `InteractiveViewer` around the graph.

## Findings

### 1. Flet / Flutter

- **Scoped updates**: Prefer `control.update()` and `page.update(control)` over `page.update()` so only the graph region is repainted, not the whole page (toolbar, nav, etc.).
- **Flutter (Flet backend)**: RepaintBoundary and `shouldRepaint` limit repaints; Flet’s Canvas doesn’t expose these directly, so minimizing how often we change `canvas.shapes` and how much we call `page.update()` matters.
- **Canvas docs**: The free-hand drawing example uses `ft.context.disable_auto_update()` and only `canvas.update()` during rapid updates to avoid full-page syncs.

### 2. What was already in place

- **Grid**: Grid is a separate SVG asset, so the canvas only holds edges (good).
- **Drag throttling**: Node repaint during drag is throttled (`DRAG_UPDATE_INTERVAL_S = 1/10`, ~10 fps).
- **Pan event rate**: `drag_interval=80` on `GestureDetector` reduces `on_pan_update` frequency.
- **Edge cache**: `get_all_edge_shapes` caches edge shapes; only edges incident to a moved node are recomputed when `invalidate_node_id` is set.
- **Drag**: `page.update(cont)` is used during drag so only the dragged node is updated.

### 3. Identified improvements

| Area | Issue | Change |
|------|--------|--------|
| Hover | `page.update()` on every hover/exit caused full-page repaint. | Use scoped update: `page.update(canvas_ref[0])` (or the graph container) so only the graph area is updated. |
| Node highlight | `update_node_highlight()` mutates all node inners and calls `inner.update()` for every node. | Only update the previous and current hovered node containers (at most two). |
| Hover hit-test | `_edge_at_point` sampled 24 points per edge on every hover. | Reduced to 12 samples; run edge hit-test only when no node is under the pointer (node takes precedence). |
| Hover rate | `hover_interval=30` (~33 Hz). | Increased to 50 ms to reduce CPU. |
| Node sizes / link types | `get_all_edge_shapes` recomputed `node_size()` and `_link_type_for_edge` per edge every time. | Precompute `node_sizes` and `link_type_cache` once per call and reuse. |

### 4. Optional / future

- **Drag smoothness**: Increase throttle from 10 fps to 15–20 fps if needed (trade CPU for smoother motion).
- **Layout**: `flow_layout._layered_layout` is pure Python; for very large graphs, consider caching or a faster layout implementation.
- **Workflow tab**: `refresh_process_tab()` rebuilds the entire graph; avoid full rebuild when only data (not structure) changes if we add incremental updates later.

## References

- [Flet Canvas](https://docs.flet.dev/controls/canvas/)
- [Flet Context / control.update](https://docs.flet.dev/types/context/) (scoped updates)
- Flutter: RepaintBoundary, CustomPainter `shouldRepaint` (conceptual; Flet abstracts the backend)
