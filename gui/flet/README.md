# Flet constructor GUI (Canvas graph)

Cross-platform desktop GUI for the constructor: **process graph** (pure Flet Canvas + draggable Node controls), training config, run/test, and assistant (placeholders for now). No WebView or HTTP server.

## Run

From the **repo root** (with the project venv activated):

```bash
pip install -r requirements.txt   # main deps
pip install -r gui/flet/requirements.txt   # flet
python -m gui.flet.main
```

Or with Flet CLI:

```bash
flet run gui/flet/main.py
```

- The **Process** tab shows the process graph: nodes (units) and edges (connections) drawn with Flet Canvas; nodes are draggable and edges redraw on drag.
- **Training**, **Run/Test**, and **Assistant** are placeholders.

## Layout

- **Process**: `GraphCanvas` — one `cv.Canvas` with edge lines and a `Stack` of draggable `Node` controls (one per unit). Same layered layout as the Streamlit GUI; lines connect node right-edge to node left-edge.
- **Training / Run/Test / Assistant**: Stub panels for later implementation.

## Files

- `main.py` — Flet app: nav rail, Process tab with `GraphCanvas`, load example `temperature_process.yaml`.
- `graph_canvas.py` — `Node` (unit card) and `GraphCanvas` (Canvas edges + Stack of nodes, drag updates positions and redraws lines).
- `flow_layout.py` — Layered layout and `get_graph_layout_for_canvas()` (positions + edges for Canvas).
- `DRAWING_LINES_FLET.md` — Notes on Flet Canvas line drawing and dynamic updates.
- `requirements.txt` — `flet` only (no flet-webview).

Optional/legacy:

- `graph_viewer.html` — Standalone React Flow viewer (CDN); not used by the app anymore. Kept for reference or if you want to serve it separately.

## Dependencies

- **flet** — Desktop (and web) UI; Canvas for drawing edges.
