# AI TaskVector

**Core concept**: An open low-code programming framework and GUI visual editor for AI Agents to develop and train themselves safely while helping users address their business and engineering challenges.

**Example**: *"- Could you create an AI agent that would set up a production line and operate the process...?"*

----

**Beta version!** Use it at your own risk.

----
<img width="1339" height="807" alt="taskvecoter_demo_flow" src="https://github.com/user-attachments/assets/21a9d9f2-539c-4f9d-9eef-464729fd4b85" />

## Agents (TaskVector team)

- Bob - **Workflow Designer** to create/modify workflows, generate custom units (*if allowed*), make integrations.
- Tom - **RL Coach** to train/fine-tune models.
- Inga -  **Data Analyst** to make deep data analysis and perform calculations
- **Demiurge** (*coming soon*) - main autonomous orchestrator.

## Quick start

**1. Install TaskVector**

```bash
cd ai-taskvector
pip install -r requirements.txt
```

**2. Install RAG**

```bash
`pip install -r rag/requirements.txt`
```

**3. Install Units Packages**

```bash
pip install -r units/web/requirements.txt
pip install -r units/semantics/requirements.txt
```

Creating new units guide: `units/CREATING-NEW-UNIT.md`

**4. GUI: Desktop app and AI chat**

- Install:

```bash
pip install -r gui/requirements.txt
```

- Run:

```bash
python -m gui.main
```
**5. Configuration**
- `/config/app_settings.json` - general settings
- `/rag/ragconf.yaml` - rag config
- `/roles/<role>/role.yaml` - agent role config
- `/tools/<tool>/tool.yaml` - agent tool config
- `/mydata/`- default RAG folder for uploaded data
- `rag/.rag_index_data/`
  - `/chroma_db` - default db folder
  - `/rag_index_state.json` - mydata changes state
- `/chat_history/` - AI chat conversations and metadata ranked

## Usage

**The primary interface is the AI chat.** Talk to the TaskVector AI team to accomplish your goal. Ask for creation/modificaion of an Agent, workflow, unit, process, training a regression etc. Run the workflow, debug, research, etc.

- **Workflows:** 
  - You can either consider creating a workflow from scratch or import one.
  - Drop in a workflow graph (TaskVector, Node-RED, PyFlow, n8n, ..). External ones are translated to TaskVector (canonical) on import;
  - Modify the workflow (export back if external)
  - Run the process inline (Python only)
  - Testing: Add a `Debug` unit with `/debug.log` in params to log the output. Use `Template` unit to pass mock/test data into the workflow. A simple test workflow would be as follows: `Template -> Inject -> YourUnitToTest -> Debug`
- **Training:** 
  - Load/edit training config (goal, rewards, callbacks). 
  - Run training or test a saved model.
  - Use the external runtime "roundtrip" feature for RL training: integrate an agentic loop into the external workflow (e.g, Node-Red ot n8n), export back and run the loop (Taskvector <-> Node-Red).
- **RAG:** 
  - **Knowledge Base**: Upload files, search data (e.g. you can upload node-red repo for the AI agents to use their workflow library or an XLSX spreadsheet to make calculations using formulas, etc.).
  - **Agent Long Memory**: Make sure the `chat_history` folder is under the RAG (e.g. `/mydata/chat_history`) for the agents to remember past confersations.
  - ****

---
## Framework structure

```
ai-taskvector
├── assistants
│   ├── roles
│   │   ├── workflow_designer
│   │   ├── ...
│   │   └── registry.py
│   └── tools
│       ├── web_search
│       ├── ...
│       └── registry.py
├── environments
│   ├── ...
│   └── registry.py
├── units
│   ├── canonical
│   ├── data_bi
│   ├── web
│   ├── pipelines
│   ├── node-red 
│   ├── n8n
│   ├── ...
│   └── registry.py
├── rag
│   └── content_types
│       ├── audio
│       ├── video
│       ├── spreadsheet
│       ├── pdf
│       ├── markdown
│       ├── ...
│       └── registry.py
├── LLM_integrations
│   ├── Ollama
│   └── ...
├── gui editor (desktop/web)
├── core
│   (workflow graph, training schemas, rewards DSL, etc.)
├── deploy
│   (cross-platform nodes/pipelines deployment, external runtime roundtrip)
├── runtime
│   (native workflow executor)
└── server
    (inference server)
```

Brief overview:
- Low-code data driven concept
- Language agnostic graph: The canonical graph is capable of carrying units written in any language as code blocks. (`/core/schemas`). Explore `/docs/PROCESS_GRAPH_TOPOLOGY.md`).
- Native runtime: Python-based graph execution (`/runtime`).
- External runtimes (workflow conversion compatibility): `Node-RED`, `Pyflow`, `ComFy`, `n8n`.
- Offline local models
- Sustainable Agents memory and RAG knowledge base

---

## Docker

You can run the app (and optionally the Ollama LLM server) in Docker. The image includes the full stack (main app, RAG, GUI, Units). Works with **classic Docker (e.g. 2022)** and newer BuildKit.

**Build and run with Docker Compose (app + Ollama)**

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
docker run --rm -p 8550:8550 -e OLLAMA_HOST=http://host.docker.internal:11434 ai-taskvector flet run gui/main.py --web -p 8550
```

**Environment variables**

| Variable | Description |
|----------|-------------|
| `OLLAMA_HOST` | Ollama server URL (default: `http://127.0.0.1:11434`). In Compose, set to `http://ollama:11434`. |
| `OLLAMA_MODEL` | Default model name (e.g. `llama3.2`) when not set in GUI settings. |
| `OLLAMA_API_KEY` | Optional; for Ollama Cloud. |

**Docker Files**

- `Dockerfile` — Full install (main + RAG + Flet GUI + units); default command runs the Flet GUI.
- `docker-compose.yml` — App + Ollama service; Flet runs in web mode on port 8550.

## Dependencies

| Area | Notable libraries | Declared in |
|------|-------------------|-------------|
| **Core** (schemas, configs, graphs) | **Pydantic**, **PyYAML**, **NumPy**, **Pandas**; **scikit-learn**, **Matplotlib** where analytics/plotting are used | `requirements.txt` |
| **Runtime** (workflows, units, servers) | **FastAPI**, **Uvicorn** (LLM inference / ASGI); **Requests**, **websocket-client** (HTTP/WS and external adapters) | `requirements.txt` |
| **Training** (RL) | **PyTorch**, **Gymnasium**, **Stable-Baselines3** (with extras), **TensorBoard**; **tqdm**, **rich** (CLI progress/logging); **asteval**, **rule-engine** (reward formula DSL and rule evaluation) | `requirements.txt` |
| **GUI** | **Flet**, **flet-code-editor** (workflow/code views) | `gui/requirements.txt` (install after `requirements.txt`) |
| **RAG** | **ChromaDB**, **sentence-transformers**, **pandas**, **formulas** (canonical **Embedder** / **ChromaIndexer** units), **Docling** (PDF/DOC/XLS/XLSX ingestion via LoadDocument) | `rag/requirements.txt` (optional; `pip install -r rag/requirements.txt`) |
| **Assistants / chat** | **ollama** (Python client to a local Ollama server; install models with the Ollama app / CLI separately) | `requirements.txt` |

## Contribution

Thanks for considering a contribution — we welcome fixes, features, docs, tests, and new units/agents. Fork the repo and follow the [contribution guidelines](docs/CONTRIBUTION.md").

## License

[MIT](LICENSE) — use and modify for your projects.
