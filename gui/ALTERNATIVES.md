# GUI framework alternatives and PyFlow for the graph editor

This doc covers: **alternatives to Streamlit** (privacy / no telemetry) and whether **integrating PyFlow** for display/edit of the language-agnostic graph flow is a good move.

**Current choice:** Keep **Streamlit** for now. A **React-Flow-based flow visualization** (via `streamlit-flow-component`) is shown in the **Flow** tab after importing a process graph. A **desktop** constructor (e.g. PyQt/PySide + PyFlow as the graph editor) is planned for later.

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

**Recommendation:** For a **web** constructor with minimal telemetry concern: **NiceGUI** or **Panel** are close to Streamlit (Python-first, local). For a **desktop** constructor: **PyQt/PySide** or **Flet** (desktop mode); then you can embed **PyFlow** as the graph editor (see §3).

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
| **Desktop app** | Constructor as a **desktop** app (no browser) | Build the GUI with **PyQt/PySide** or **Flet** (desktop). Embed **PyFlow** as the central widget for the process graph; side panels for training config, run/test, assistant. Adapter: PyFlow graph ↔ our ProcessGraph (and code_blocks). |
| **Web app** | Constructor stays **web** (browser) | PyFlow is Qt/desktop and is not straightforward to embed in a browser. Use a **web-based node editor** instead (e.g. **React Flow**, **Rete.js**) that loads/saves our canonical format (units, connections, optional code_blocks). Same schema; different UI stack. |

So: **integrating PyFlow for display/edit is the right move for a desktop constructor.** For a web constructor, use a **web-based node editor** (React Flow, etc.) that speaks our canonical format; PyFlow remains the right choice for the **Python-native / desktop** path and for the runtime adapter (pyflow_adapter).

---

## 4. Summary

| Question | Answer |
|----------|--------|
| **Streamlit alternatives (privacy)?** | NiceGUI, Panel, Dash (self-hosted), Flet, PyQt/PySide. Run any web framework locally to keep data local. |
| **Integrate PyFlow for graph edit?** | **Yes** for a **desktop** app: embed PyFlow as the graph editor; adapter PyFlow ↔ ProcessGraph + code_blocks. For **web**, use a web-based node editor (React Flow, etc.) with the same canonical format. |
