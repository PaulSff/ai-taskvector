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

### 5. Parallel work (threading / async)

**Is it possible?** Yes, in a limited way.

- **Flet**: Use `page.run_task(async_coro)` to run an async task in the background. Use `asyncio.to_thread(fn, ...)` inside that coroutine to run CPU-bound work (e.g. hit-test or shape building) in a thread pool so the UI thread doesn’t block. When the thread returns, the rest of the coroutine runs in Flet’s context and can safely call `control.update()` / `page.update(control)`.

- **What we can offload**:
  - **Hover hit-test**: Run `_node_at_point` + `_edge_at_point` in a thread with a snapshot of `positions`, `edges`, `node_ids_order`, `node_sizes`. When the result comes back, if it’s still the latest request (generation id), apply it and refresh. Keeps hover from blocking the UI on large graphs.
  - **Edge shape building**: Running `get_all_edge_shapes` in a thread is tricky because it mutates `edge_shapes_cache`. Two concurrent calls would race. Options: (1) run it in a single thread and only assign `canvas.shapes` on the main side after it returns (still blocks that thread), or (2) add a pure “compute shapes from positions only” path that doesn’t touch the cache, run that in a thread, then on main assign to canvas (and optionally merge into cache). (2) avoids races but duplicates logic or adds a no-cache code path.

- **Tradeoffs**:
  - **Hover offload**: Small graphs see little benefit; thread and snapshot overhead can outweigh gains. Helps when there are many nodes/edges and hit-test is slow.
  - **Edge build offload**: Cache mutation forces either serialized use of the cache or a cache-free path; implementation is more involved.
  - **Pyodide / web**: `asyncio.to_thread` uses a thread pool; Pyodide doesn’t support threads, so this pattern would need an async-only path (e.g. chunked work with `await asyncio.sleep(0)`) for static web.

**Implemented**: Optional hover hit-test offload via `page.run_task` + `asyncio.to_thread`, with a request generation id so only the latest hover result is applied.

## References

- [Flet Canvas](https://docs.flet.dev/controls/canvas/)
- [Flet Context / control.update](https://docs.flet.dev/types/context/) (scoped updates)
- Flutter: RepaintBoundary, CustomPainter `shouldRepaint` (conceptual; Flet abstracts the backend)
