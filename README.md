# AI TaskVector

Your personal open-source AI agents factory that runs on your machine.

## AI agents

- Bob - **Workflow Designer** to create/modify workflows, generate custom units (*if allowed*), make integrations.
- Inga -  **Analyst** to make deep data analysis and perform calculations
- Helen - **Dispatcher** to assign tasks to agents.
- Tom - **RL Coach** to train/fine-tune models.
- Demiurge (*coming soon*) - the **Boss** of it all.
----

**Beta version!** Use it at your own risk.

----
<img width="1339" height="807" alt="taskvecoter_demo_flow" src="https://github.com/user-attachments/assets/21a9d9f2-539c-4f9d-9eef-464729fd4b85" />


## Quick start

**0. Clone TaskVector to your machine**
```bash
git clone https://github.com/PaulSff/ai-taskvector.git
```

**1. Install TaskVector, GUI and packages**

```bash
cd ai-taskvector
pip install -e ".[rag,gui,messengers-integrations,units-web,units-semantics,units-messengers]"
```

**2. Pull LLM**
Make sure you have installed Ollama. 

Currently, we support Ollama. Follow the [instructions](https://github.com/ollama/ollama#ollama) to download Ollama and pull LLMs (No other services are required, but the models themselves. Everything else is provided by TaskVector (memory, tools, etc.). 

**3. Run workflow server**

```bash
 python server/workflow_server.py
```

**4. Run GUI: Desktop/WEB app**

- Desktop:

```bash
flet run gui/main.py
```

- WEB:
```bash
flet run gui/main.py --web -p 8550
```
In your WEB browser, open: `http://localhost:8550`

Development mode (allows to follow the LLMs context, prompts, etc.):

```bash
python -m gui.main -dev
```

## Usage

**The primary interface is the AI chat.** Talk to the TaskVector AI team to accomplish your goal. Ask for creation/modificaion of an Agent, workflow, unit, process, etc. Run the workflow, debug, research, etc.

## Configuration
- `config/app_settings.json` - general settings
- `config/prompts/<role>.json` - role prompt config used on agent workflow execution
- `rag/ragconf.yaml` - rag config
- `roles/<role>/role.yaml` - agent role config
- `tools/<tool>/tool.yaml` - agent tool config
- `mydata/`- default RAG folder for uploaded data
- `rag/.rag_index_data/`
   - `chroma_db/` - default db folder
   - `rag_index_state.json` - mydata changes state
- `chat_history/` - AI chat conversations and metadata ranked


## Create your custom AI agent in one command
You can create a new agent in one command by cloning the Analyst role package. 

Execute From the repo root:

```bash
  python agents/roles/clone_role.py --new-role administrator \
    --character-name Alex \
    --responsibility "Responsible for X" \
    --intro "Hello, I'm Admin at TaskVector." \
    --tools grep read_file formulas_calc     
```
- `--new-role` (mandatory) - new agent role name (e.g. administrator, sales manager, account manager, etc.)
- `--character-name`(mandatory) - any human-like name for the character to interact with 
- `--responsibility` - responsibility descritpion
- `--intro` - one sentence introduction
- `--tools` - a set of tools available for the agent (pick up the tools from here: `agents/tools`)
- `--intro-body`  e.g. "You do servers administraion job and address users requests.."
- `--conversational-behaviour` e.g. "Start with a short lead sentence, then go deeper..."
- `--reasoning` e.g. "Break down tasks..."

Once the new role is created, adjust the prompt to adapt the agent behaviour:  `agents/roles/<new_role>/prompts.py`. Modify these particular sections: 
- `<NEW_ROLE>_SECTION_ROLE_AND_INTRO_BODY = """ ... """`. 
- `<NEW_ROLE>_SECTION_CONVERSATIONAL_BEHAVIOUR = """ ... """`
- `<NEW_ROLE>_SECTION_REASONING = """..."""`

Restart the app and enjoy interacting with your agent through the chat. The `config/prompts/<role>.json` is built automaticaly on startup. Configure the agent with the `roles/<role>/role.yaml`.

----
- **Workflows:** 
  - You can either create a workflow from scratch or import one.
  - Drop in a workflow graph (TaskVector, Node-RED, PyFlow, n8n, ..). External ones are translated to TaskVector canonical workflow format on import;
  - Modify the workflow (export back if external)
  - Run the process inline (Python only)
  - Testing: Add a `Debug` unit with `/debug.log` in params to log the output. Use `Template` unit to pass mock/test data into the workflow. A simple test workflow would be as follows: `Template -> Inject -> YourUnitToTest -> Debug`
- **RAG:** 
  - **Knowledge Base**: Upload files, search data (e.g. you can upload node-red repo for the AI agents to use their workflow library or an XLSX spreadsheet to make calculations using formulas, etc.).
  - **Agent Long Memory**: Make sure the `chat_history` folder is under the RAG (e.g. `mydata/chat_history`) for the agents to remember conversations that happened in the past.
- **Training:** 
  - Load/edit training config (goal, rewards, callbacks). 
  - Run training or test Best model.

## Framework structure

```
ai-taskvector
├── agents
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
│   (native workflow executor + cross-process messaging via ZeroMQ)
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

## Creating new units and tools

- Follow this guide to create custom units (nodes): `units/CREATING-NEW-UNIT.md`
- Explore new tools development guide: `agents/tools/README.md`

## LLM Integrations

We created a unified LLM client interface (`LLM_integrations/client.py`) to support multiple LLM providers. Each provider has its own adapter in `LLM_integrations/<provider>.py`, which converts the provider's API to a uniform interface. Create a new adapter for your provider, use the `LLM_integrations/ollama.py` as a reference.

## Contribution

Thanks for considering a contribution — we welcome fixes, features, docs, tests, and new units/agents. Fork the repo and follow the [contribution guidelines](/docs/CONTRIBUTING.md).

## License

[MIT](LICENSE) — use and modify for your projects.
