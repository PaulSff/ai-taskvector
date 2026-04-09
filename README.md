# AI TaskVector

----

**Beta version!** Use it at your own risk.

----
Core concept: AI agents creating and training AI agents for users needs.

A low-code programming **framework** and **GUI visual editor** for AI assistants to help users solve business and engineering tasks by **composing specific workflows from units/pipilines**, and **configure/perform training** via GUI and chat conversation—minimizing hand-written code.

- Language agnostic graph: the Graph is capable of carring units written in any language.
- Native runtime: Python-based graph execution.
- External runtimes (workflow conversion compatibility): Node-RED, Pyflow, ComFy, n8n, etc. You can drop in an external workflow as is, modify and export back. Use the external runtime "roundtrip" feature for RL training.

## Assistants (co-pilots)

- **Workflow Designer** to create/modify workflows, generate custom units (if allowed), make integrations.
- **RL Coach** to train/fine-tune models.

---
<img width="1339" height="807" alt="taskvecoter_demo_flow" src="https://github.com/user-attachments/assets/21a9d9f2-539c-4f9d-9eef-464729fd4b85" />



## Quick start

**1. Install (from repo root)**

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Open the Constructor GUI (Flet)**

Desktop app: workflow graph (canvas), training config, run/test, and AI chat (Workflow Designer / RL Coach).

```bash
pip install -r gui/flet/requirements.txt
python -m gui.flet.main
```

- **Workflow:** Load or paste a process graph (Node-RED/PyFlow/n8n/YAML); edit on canvas; run workflow, report, grep, GitHub from chat.
- **Training:** Load/edit training config (goal, rewards, callbacks); run training or test a saved model.
- **Chat:** Talk to Workflow Designer (graph edits) or RL Coach (training config); edits are applied to graph or config.

**3. Train from the command line (optional)**

```bash
python runtime/train.py --config config/examples/training_config.yaml
```

Use `--process-config` for a custom process graph; use `--checkpoint` to resume. All behavior is driven by the config files the assistants (or you) produce.

**4. Test a trained model**

```bash
python scripts/test_model.py ./models/temperature-control-agent/best/best_model
```

For a visual tank demo and manual sliders (thermodynamic example):

```bash
python -m environments.custom.thermodynamics.water_tank_simulator --config config/examples/training_config.yaml --model ./models/temperature-control-agent/best/best_model
```

---

## Docker

You can run the app (and optionally the Ollama LLM server) in Docker. The image includes the full stack: main app, RAG, Flet GUI, and units (e.g. web_search). Works with **classic Docker (e.g. 2022)** and newer BuildKit. If you hit *No space left on device* during build, free disk space or set `TMPDIR` or `PIP_CACHE_DIR` to a directory on a larger drive before running `docker build`.

**Build and run with Docker Compose (app + Ollama)**

From the repo root:

```bash
docker compose build
docker compose up
```

Then open the Flet GUI in your browser at **http://localhost:8550**. The app is configured to use the Ollama service automatically via `OLLAMA_HOST`.

Pull a model in Ollama (one-time):

```bash
docker compose exec ollama ollama pull llama3.2
```

Models are stored in a persistent volume (`ollama_data`).

**Build and run the app image only**

```bash
docker build -t ai-taskvector .
docker run --rm -p 8550:8550 -e FLET_WEB=1 -e FLET_SERVER_PORT=8550 ai-taskvector
```

Open **http://localhost:8550**. If Ollama runs on your host, point the app at it with:

```bash
docker run --rm -p 8550:8550 -e OLLAMA_HOST=http://host.docker.internal:11434 ai-taskvector flet run gui/flet/main.py --web -p 8550
```

**Environment variables**

| Variable | Description |
|----------|-------------|
| `OLLAMA_HOST` | Ollama server URL (default: `http://127.0.0.1:11434`). In Compose, set to `http://ollama:11434`. |
| `OLLAMA_MODEL` | Default model name (e.g. `llama3.2`) when not set in GUI settings. |
| `OLLAMA_API_KEY` | Optional; for Ollama Cloud. |

**Files**

- `Dockerfile` — Full install (main + RAG + Flet GUI + units); default command runs the Flet GUI.
- `docker-compose.yml` — App + Ollama service; Flet runs in web mode on port 8550.

**Apply assistant edits from the CLI:**

```bash
# Process Assistant: apply graph edit (add/remove/connect units)
python -m assistants apply_graph --graph config/examples/temperature_process.yaml --edit edit.json [--out path]

# Training Assistant: apply config edit (goal, rewards, hyperparameters)
python -m assistants apply_config --config config/examples/training_config.yaml --edit edit.json [--out path]
```

## License

[MIT](LICENSE) — use and modify for your projects.
