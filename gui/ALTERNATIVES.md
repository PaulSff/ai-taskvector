# GUI framework alternatives and PyFlow for the graph editor

This doc covers: **alternatives to Streamlit** (privacy / no telemetry) and whether **integrating PyFlow** for display/edit of the language-agnostic graph flow is a good move.

**Current choice:** Keep **Streamlit** for now. A **React-Flow-based flow visualization** (via `streamlit-flow-component`) is shown in the **Flow** tab after importing a process graph.

**Target for desktop:** A **cross-platform desktop GUI** (Windows, macOS, Linux) is the goal—no need for Electron or a web stack. Preferred options: **Flet + React Flow** (graph in WebView; see §2.2) or **PyQt/PySide + PyFlow** (see §3).

---

## 1. Streamlit and user data

When you **run Streamlit locally** (`streamlit run gui/app.py`), your data stays on your machine. Streamlit Cloud and some deployment setups may collect usage/analytics; running on localhost does not send your process graphs or configs to Streamlit by default. You can disable analytics in Streamlit config if desired (`~/.streamlit/config.toml` or project config).

If you prefer to **avoid any framework telemetry** or want a **desktop-only** app with no web stack, the alternatives below are options.

---

## 2. Alternatives to Streamlit

| Framework | Stack | Privacy / data | Notes |
|-----------|--------|----------------|--------|
| **NiceGUI** | Python, Vue-based, runs in browser or native window | Open source; runs locally; no built-in telemetry | [NiceGUI](https://nicegui.io). Good for dashboards and tools; can run as web server or desktop (native window). Same “Python script → UI” model as Streamlit. |
| **Panel (HoloViz)** | Python, Bokeh/Param, runs in browser | Open source; self-hosted; no telemetry by default | [Panel](https://panel.holoviz.org). Dashboards and apps; works with Jupyter or server. |
| **Dash (Plotly)** | Python, React-based, runs in browser | Open source; self-hosted; no data sent unless you add analytics | [Dash](https://dash.plotly.com). More structure than Streamlit; good for data apps. |
| **Gradio** | Python, quick ML/demo UIs | Open source; can run fully local; Gradio’s hosted option has their terms | [Gradio](https://gradio.app). Similar to Streamlit for quick UIs; run locally to keep data local. |
| **Flet** | Python, Flutter-based UI | Open source; can run as desktop or web | [Flet](https://flet.dev). Single codebase for desktop and web; no framework telemetry. |
| **PyQt / PySide** | Python, Qt widgets | Desktop only; all local; no web stack | Full desktop app; process graph could be a custom Qt canvas or embed PyFlow (see below). |

### Sim — full-stack web replacement

**[Sim](https://github.com/simstudioai/sim)** (Apache-2.0) is an open-source platform to build and deploy AI agent workflows. It could replace our current **web GUI** (Streamlit) with a more capable stack:

- **Visual workflow builder** — Canvas with ReactFlow; connect agents, tools, and blocks; run from the UI.
- **Copilot** — Generate/fix nodes and iterate on flows from natural language (optional; uses Sim-managed or self-hosted API key).
- **Self-hosted** — `npx simstudio`, Docker Compose, or manual (Next.js + Bun + PostgreSQL/pgvector); no lock-in to their cloud.
- **Stack:** Next.js, ReactFlow, Shadcn, Tailwind, Zustand; optional vector DB, Trigger.dev, E2B.

**Fit for our constructor:** Our backend (normalizer, env factory, train/test, assistants) would stay in Python; Sim would be the **web front-end**. We’d either (a) add custom “process graph” and “training” blocks/nodes that call our APIs, or (b) fork Sim and tailor the canvas + blocks to process graph + RL training + assistant. Sim is generic AI workflows; we’d map our ProcessGraph and TrainingConfig into its node/flow model.

**Recommendation:** For a **web** constructor with minimal telemetry concern: **NiceGUI** or **Panel** are close to Streamlit (Python-first, local). For a **richer web replacement** (visual flow editor, Copilot-style help, self-hosted): consider **Sim** and wire our Python backend as the execution layer. For a **desktop** constructor: **PyQt/PySide** (embed PyFlow) or **Flet** (desktop mode) with **React Flow** in a WebView (see §2.2).

### Flet + React Flow (graph viewer)

**Yes, it makes sense** to use **Flet for the app shell** and **React Flow for the process graph** in the same desktop app:

- **Flet** — Tabs, training config, run/test buttons, assistant panel, layout. All in Python; one codebase for desktop (and optional web).
- **React Flow** — Rendered inside a **WebView** (or similar) control in Flet. You already use React Flow in the Streamlit GUI (streamlit-flow-component) and have a ProcessGraph → nodes/edges mapping and layout; the same logic can live in a small bundled HTML/JS (or minimal React) app that the WebView loads.

**How it works:** The Flet window has one panel that hosts a WebView. The WebView loads a local page (e.g. a packaged `graph_viewer.html` + JS bundle) that runs React Flow. Flet sends the current ProcessGraph (as JSON) into the WebView (e.g. via `postMessage` or injected script); the viewer draws nodes and edges. Optionally, the viewer sends back edits (e.g. connection changes) so Flet can update the canonical graph.

**Pros:** Rich, proven graph UI without building a custom Flet canvas; reuse of your existing React Flow format and layout; rest of the app stays Python-only. **Cons:** One hybrid piece (small JS bundle to build and ship with the app); need to maintain the Flet ↔ WebView bridge.

**Conclusion:** Flet + React Flow in a WebView is a practical and sensible choice for a cross-platform desktop constructor when you want a single Python-led codebase but don’t want to reimplement a node graph in Flet or adopt full PyQt/PySide + PyFlow.

### PyFlowUI (ImGui + OpenGL) — alternative to PyFlow

**[PyFlowUI](https://github.com/msfocus/PyFlowUI)** (GPL-3.0) is a **different project** from [PyFlow](https://github.com/pedroCabrera/PyFlow) (the Qt-based node editor we reference in §3).

| | **PyFlow** (pedroCabrera) | **PyFlowUI** (msfocus) |
|--|---------------------------|-------------------------|
| **Stack** | Python, **Qt** (PyQt/PySide) | Python, **ImGui**, **OpenGL**, GLFW |
| **Purpose** | Node-based visual scripting, Python execution, script export | Tiny workflow UI: modules, input/output slots, connections |
| **Our support** | Normalizer `format="pyflow"`, pyflow_adapter, inject_agent_into_pyflow_flow | **None** — we have no adapter or import for PyFlowUI |
| **Maturity** | Established; we already import/run PyFlow JSON | Very early (0 stars, 5 commits); SQLite + JSON config |

**Why PyFlowUI could be interesting:** It’s a **Python-native** node-style editor **without Qt** (ImGui + OpenGL). So if you want an embeddable graph UI in a **non-Qt** Python app (e.g. a game or custom OpenGL host), PyFlowUI might be easier to integrate than PyFlow. It’s generic (modules, slots, connections), so in principle it could **preview** a language-agnostic graph if we wrote an adapter (ProcessGraph ↔ PyFlowUI’s format). The README mentions ComfyUI-style integration.

**Caveats:** Early-stage; no ecosystem yet. We’d need to (1) confirm its data format (e.g. `modules_config.json`) and whether it can represent our units/connections, (2) check if it’s embeddable as a widget or runs as a standalone window, and (3) consider **GPL-3.0** if we link or embed it.

**Summary:** For our **desktop constructor**, **PyFlow** (Qt) remains the documented choice because we already have import/runtime/adapter. **PyFlowUI** is worth a look if we later want a Qt-free, ImGui/OpenGL-based graph editor and are willing to add an adapter and accept its license and maturity.

---

## 3. Integrating PyFlow for display/edit of the graph flow

**Would it be a right move to integrate PyFlow to display/edit our language-agnostic graph flow visually?**

**Yes, for a desktop constructor.** PyFlow is a **Python-native node editor** (canvas, nodes, pins, connections). Using it as the **graph editor** in the constructor would give:

- **Visual edit** of the process graph (units + connections) in the same language-agnostic way we already model it (ProcessGraph + optional code_blocks).
- **One stack:** Python + PyFlow for both design and (via pyflow_adapter) runtime.
- **Roundtrip:** Our canonical format ↔ PyFlow graph via an adapter; train from the graph; optionally inject the trained model as a node back into the flow (see docs/WORKFLOW_EDITORS_AND_CODE.md and docs/DEPLOYMENT_NODERED.md).

**Two integration paths:**

| Path | Use case | How |
|------|----------|-----|
| **Desktop (PyQt/PySide)** | Desktop app, **Python-only** graph editor | Build the GUI with **PyQt/PySide**. Embed **PyFlow** as the central widget for the process graph; side panels for training config, run/test, assistant. Adapter: PyFlow graph ↔ our ProcessGraph (and code_blocks). |
| **Desktop (Flet)** | Desktop app, **rich graph** without Qt | Build the GUI with **Flet** (desktop mode). Embed a **WebView** that loads **React Flow** (same format as Streamlit flow tab); Flet sends ProcessGraph JSON to the WebView, optional edit callbacks back. See §2.2. |
| **Web app** | Constructor stays **web** (browser) | PyFlow is Qt/desktop and is not straightforward to embed in a browser. Use a **web-based node editor** (e.g. **React Flow**, **Rete.js**) that loads/saves our canonical format (units, connections, optional code_blocks). Same schema; different UI stack. |

So: **integrating PyFlow for display/edit is the right move for a desktop constructor.** For a web constructor, use a **web-based node editor** (React Flow, etc.) that speaks our canonical format; PyFlow remains the right choice for the **Python-native / desktop** path and for the runtime adapter (pyflow_adapter).

### PyFlow: native format vs language-agnostic workflow

**Out of the box,** PyFlow only edits and saves **its own format** (PyFlow JSON: nodes, pins, connections, Python-oriented code in nodes). So the PyFlow **editor** is “for PyFlow” in that sense.

**It can still preview and edit language-agnostic workflows** if we use it as a **view/editor over our canonical ProcessGraph** via adapters:

- **Preview:** We convert our **ProcessGraph** (units, connections, optional code_blocks) **into** PyFlow-shaped JSON (one node per unit, edges from connections). Load that in PyFlow → it **displays** our topology. So PyFlow can **preview** any workflow we represent in the canonical format; the data is language-agnostic, we just feed it into PyFlow’s structure.
- **Edit:** User edits in PyFlow (add/remove nodes, reconnect). On save/export we run **PyFlow JSON → normalizer (format=pyflow)** (already implemented) and get back the **canonical ProcessGraph**. So PyFlow **can** serve as the editor UI for our language-agnostic workflow; the roundtrip is **canonical ↔ PyFlow format** in both directions. We have **PyFlow → canonical**; we’d need **canonical → PyFlow** (export) to push our graph into PyFlow for display/edit.
- **Code:** Our canonical format is language-agnostic (e.g. `code_blocks` with `language: "python"` or `"javascript"`). PyFlow’s code nodes are Python-oriented. So topology and node types stay agnostic; **editing code** in PyFlow will be Python-centric; other languages can be stored and roundtripped as opaque blobs.

**Summary:** PyFlow is not “only for PyFlow workflows.” With a **canonical ↔ PyFlow adapter** (import exists; export would be added), PyFlow can **preview and edit** our language-agnostic ProcessGraph; only in-code editing is naturally Python-focused.

---

## 4. Summary

| Question | Answer |
|----------|--------|
| **Desktop target?** | **Cross-platform desktop** (Windows, macOS, Linux). **Flet + React Flow** (WebView) or **PyQt/PySide + PyFlow** for the process graph. |
| **Web GUI replacement?** | **Sim** ([simstudioai/sim](https://github.com/simstudioai/sim)) — visual workflow builder (ReactFlow), Copilot, self-hosted; wire our Python backend as execution layer. |
| **Streamlit alternatives (privacy)?** | NiceGUI, Panel, Dash (self-hosted), Flet, PyQt/PySide. Run any web framework locally to keep data local. |
| **Integrate PyFlow for graph edit?** | **Yes** for a **desktop** app: embed PyFlow as the graph editor; adapter PyFlow ↔ ProcessGraph + code_blocks. For **web**, use a web-based node editor (React Flow, etc.) with the same canonical format. |
| **PyFlow only for PyFlow workflows?** | **No.** With canonical ↔ PyFlow adapter it can **preview and edit** our language-agnostic ProcessGraph; code editing in PyFlow is Python-centric. See §3.1. |
