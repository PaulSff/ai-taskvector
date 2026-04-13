# Constructor GUI (Flet)

Desktop UI for the Process RL Constructor: workflow graph (canvas), training config, run/test, RAG, and AI chat (Workflow Designer / RL Coach).

**Framework:** [Flet](https://flet.dev) (cross-platform desktop). Run from **repo root**:

```bash
pip install -r gui/requirements.txt
python -m gui.main
```

Or: `flet run gui/main.py`

## Building with `flet build`

From the **repo root**, build a standalone desktop app ([flet build docs](https://docs.flet.dev/cli/flet-build/)):

```bash
# macOS
flet build macos --module-name gui.main

# Linux
flet build linux --module-name gui.main

# Windows
flet build windows --module-name gui.main
```

Optional: output directory and display name:

```bash
flet build macos -o ./dist --project ai-taskvector --product "AI TaskVector" --module-name gui.main
```

Flutter SDK is required (downloaded automatically on first build). Build on the target OS. For what the built app still needs (config, units, Ollama, etc.), see the main **README.md** → “Building the Flet GUI with flet build”.

## Layout

- **Left:** Workflow tab (canvas with draggable nodes, import/export, run workflow), Training tab (config, run RL training, test model), RAG tab, Settings.
- **Right:** AI Chat — Workflow Designer (graph edits) or RL Coach (training config). Uses Ollama or configured LLM; chat runs workflows and applies edits.

## Tabs

- **Workflow** — Load/save process graph (YAML/JSON, Node-RED, PyFlow, n8n). Canvas shows units and connections; edit nodes and links. Run workflow, report, grep, GitHub, etc. via assistant.
- **Training** — Load/edit training config (goal, rewards, callbacks). Run training (via run_rl_training workflow) or test policy (`scripts/test_model.py`).
- **RAG** — Index documents and workflows for assistant context.
- **Settings** — Paths, LLM provider/config, workflow and prompt paths.

## Process graph

Import from file (YAML/JSON), Node-RED/PyFlow/n8n JSON, or paste. See **gui/node-red/README.md** for Node-RED flow format and **gui/node-red/example_flow.json**.

## Requirements

- **Python 3.10–3.12**
- **Virtual environment** recommended. From repo root: `pip install -r requirements.txt` and `pip install -r gui/requirements.txt` for Flet GUI deps.

Optional deployment and stack notes are in the repository root **README.md**.
