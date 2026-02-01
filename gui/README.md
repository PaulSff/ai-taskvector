# Constructor GUI

Web UI for the Process RL Constructor: load process graph (Node-RED or YAML), edit training config, run training / test policy, and apply assistant edits.

## Run the GUI

Use a **virtual environment** (macOS/Homebrew and many Linux setups require it; do not install into system Python).

From the **repo root**:

```bash
# Create a venv if you don't have one
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Option A — GUI only (works on Python 3.13; no training)
pip install -r requirements-gui.txt

# Option B — Full stack (training + GUI; needs Python 3.10–3.12; PyTorch has no 3.13 wheels yet)
pip install -r requirements.txt

# Run Streamlit app (must run from repo root so imports resolve)
streamlit run gui/app.py
```

The app opens in your browser (default http://localhost:8501). With **Option A**, Run / Test will only work if you install the full stack in another venv and run `train.py` / `test_model.py` yourself; the GUI still edits configs and applies assistant edits.

## Tabs

- **Training config** — Load example or upload training config YAML. Edit goal (target temp, volume range), model directory, timesteps, hyperparameters. Save to file.
- **Run / Test** — Run training (`train.py`) or test policy (`test_model.py`) with config and process paths. Uses paths you provide; ensure training config and process graph are loaded in the other tabs or on disk.
- **Assistant** — Paste a Process Assistant or Training Assistant edit (JSON). Apply edit; result is normalized to canonical and shown.

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

- **Python 3.10+** for full stack (training + GUI). **Python 3.13** is supported for GUI-only via `requirements-gui.txt` (PyTorch does not yet ship wheels for 3.13).
- **Virtual environment** — use a venv (e.g. `python3 -m venv .venv` then `source .venv/bin/activate`). Do not install into system Python on macOS/Homebrew (externally-managed-environment).
- **GUI-only**: `pip install -r requirements-gui.txt` (pydantic, pyyaml, streamlit).
- **Full stack** (training + GUI): `pip install -r requirements.txt` (adds gymnasium, stable-baselines3, torch, etc.; use Python 3.10–3.12).

Optional: Node-RED (npm or Docker) if you want to design flows in Node-RED and export for the GUI.
