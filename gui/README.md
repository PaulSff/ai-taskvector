# Constructor GUI

Web UI for the Process RL Constructor: load process graph (Node-RED or YAML), edit training config, run training / test policy, and apply assistant edits.

**Framework:** Currently Streamlit. A **Flet** desktop GUI (Canvas graph + draggable nodes) is in **gui/flet/** (see **gui/flet/README.md**). For other alternatives and PyFlow, see **gui/ALTERNATIVES.md**.

## Run the GUI

Use a **virtual environment** (macOS/Homebrew and many Linux setups require it; do not install into system Python).

From the **repo root**:

```bash
# Create a venv if you don't have one (use Python 3.10–3.12; PyTorch has no wheels for 3.13)
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Run Streamlit app (must run from repo root so imports resolve)
streamlit run gui/app.py
```

The app opens in your browser (default http://localhost:8501).

## Layout

- **Left (main):** Tabs — Flow, Training config, Run / Test, Assistant (paste-edit).
- **Right:** **AI Chat** — Talk to **Workflow Designer** (process graph) or **RL Coach** (training config). Requires Ollama (`pip install ollama`, then `ollama pull llama3.2`). The assistant’s suggested edit is applied to the current graph or config when valid.

## Tabs

- **Flow** — Process topology (React Flow). Load a graph from the sidebar first.
- **Training config** — Load example or upload training config YAML. Edit goal, model dir, timesteps, hyperparameters. Save to file.
- **Run / Test** — Run training (`train.py`) or test policy (`test_model.py`).
- **Assistant** — Paste a Workflow Designer or RL Coach edit (JSON) and apply; or use the **AI Chat** panel on the right.

## Process graph (sidebar)

Load process graph from:

- **Example (temperature)** — uses `config/examples/temperature_process.yaml`.
- **Upload Node-RED JSON** — upload a Node-RED–style flow (see `gui/node-red/README.md` and `gui/node-red/example_flow.json`).
- **Upload YAML** — upload canonical process graph YAML.
- **Paste JSON** — paste Node-RED flow JSON.

The normalizer converts Node-RED or YAML to canonical process graph. Units and connection count are shown in the sidebar.

## Node-RED

- **Flow format**: See **gui/node-red/README.md** for the exact JSON shape (id, type, wires, params, controllable) and unit types (Source, Valve, Tank, Sensor).
- **Example flow**: **gui/node-red/example_flow.json** — temperature mixing (2 sources, 3 valves, 1 tank, 1 sensor). Import this in the GUI (Upload Node-RED JSON) or use it as a template in Node-RED.
- **Using Node-RED**: Run Node-RED (e.g. `npx node-red` or Docker). Create custom nodes that output the same JSON shape, or build the flow manually and export. Then load the exported JSON in the Constructor GUI.

## Requirements

- **Python 3.10–3.12** (PyTorch does not yet ship wheels for 3.13).
- **Virtual environment** — use a venv (e.g. `python3 -m venv .venv` then `source .venv/bin/activate`). Do not install into system Python on macOS/Homebrew (externally-managed-environment).
- **Dependencies**: `pip install -r requirements.txt` (gymnasium, stable-baselines3, torch, streamlit, etc.).

Optional: Node-RED (npm or Docker) if you want to design flows in Node-RED and export for the GUI.

## Flet desktop GUI

A cross-platform **desktop** constructor UI (Flet Canvas graph + draggable nodes, no WebView) is in **gui/flet/**. From repo root:

```bash
pip install -r gui/flet/requirements.txt
python -m gui.flet.main
```

See **gui/flet/README.md** for details.
