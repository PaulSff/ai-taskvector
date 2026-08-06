# AI Agents (TaskVector)

TaskVector is an open-source, local-first “AI agents factory” that turns high-level AI reasoning into **structured, runnable work**. It coordinates an internal “AI team” of specialized agents, but constrains their autonomy so they can only act through **framework-defined workflow primitives**: roles, tools, and executable graph units.

> Status: Beta version — use at your own risk.

## Core concept: Every process is a canonical workflow (process graph)

TaskVector represents **any process** as a **canonical process graph**—a portable workflow schema that serves as the **single source of truth** for:

- **Units (nodes):** what functionality exists in the workflow
- **Directed connections (edges):** how units are wired together
- **Ports + connections:** the data-flow contract between units
- **Optional embedded artifacts:** language-agnostic code blocks preserved for roundtrip
- **Optional layout metadata:** for editor visualization
- **Optional comments:** metadata-only notes
- **Todo lists / task notes:** for human/agent task organization

External workflow formats (e.g., Node-RED, PyFlow, n8n, Ryven, etc.) are normalized **into** the canonical graph so they can be inspected, controlled, and executed consistently. The result is a system where work is:

- portable
- inspectable
- controllable
- trainable

## What TaskVector is: an operating system for an autonomous AI team

TaskVector acts like a local **operating system** for a multi-role AI team:

- specialized **agents** coordinate, design, dispatch tasks, analyze outcomes, and train/update capabilities
- workflows can be executed **deterministically** via TaskVector’s native runtime
- training and improvement are modeled as part of the ongoing operational loop, not only a separate offline ritual

So TaskVector is not just a chat prompt interface—it’s a framework where agent activity is structured as **runnable graph-based workflows**.


## Core principles (why autonomy stays predictable)

### 1) Graph = source of truth
Execution and summary logic read from the canonical graph only.

### 2) Ports and connections are mandatory
Workflows are not “best-effort.” **Ports + connections define the data flow contract.**
When ports are missing after import or edits, normalization enriches the graph using unit specs so the executor can run without guessing.

### 3) Structure constrains autonomy (predictable, safe-by-design)
Agents cannot “take over the computer” because the system only provides capabilities that exist as **tools/units** inside the framework.

A workflow’s wiring and unit types determine what is allowed—keeping autonomy:
- bounded
- observable
- controllable through framework primitives

### 4) Roles and tools/skills are modular and composable
TaskVector supports creation and composition of:
- **roles** (agent personas with responsibilities and prompt configuration)
- **tools** (framework capabilities usable by agents)
- **units** (graph nodes representing executable functionality)

Skill growth becomes systematic: register a capability as a unit/tool, then wire it into graphs.

### 5) Training during operation (lifelong loop)
The system aims for continual improvement:
- the AI team executes workflows for user goals
- outcomes generate signals (data, reward proxies, evaluation results, traces)
- the system updates models and/or training configuration
- updated learnings become new or improved units for future workflows

Training is part of ongoing operation.

## The built-in TaskVector agent team

TaskVector includes a set of built-in roles that coordinate work inside the framework.

### Bob — Workflow Designer
- Purpose: create/modify workflows, generate custom units (if allowed), and make integrations.

Ask Bob for things like:
- “Design a workflow graph to process X.”
- “Import this external graph and translate it into TaskVector canonical format.”
- “Modify this workflow: add Debug logging, Template injection, etc.”
- “Create a new unit for doing Y.”

### Inga — Analyst
- Purpose: deep data analysis and performing calculations.

Ask Inga for:
- “Analyze this dataset/spreadsheet.”
- “Compute formulas and derive metrics.”
- “Summarize findings from uploaded files.”

### Helen — Dispatcher
- Purpose: assign tasks to agents and coordinate internal role work.

Ask Helen for:
- “Split the work into sub-tasks and delegate to the right roles.”
- “Which steps should be workflow units vs analysis vs training?”

### Tom — RL Coach
- Purpose: train/fine-tune models.

Ask Tom for:
- “Load/edit training config for goal X.”
- “Run training or test the best model.”
- “Adjust rewards/callbacks for behavior Y.”

### Demiurge — Role Cloner / Role Factory
- Purpose: create new roles by cloning the Analyst pattern.

Ask Demiurge for:
- “Clone the Analyst role to create a role for my domain.”
- “Generate role scaffolding and prompt config from my specs.”


## AI agents

- Bob - **Workflow Designer** to create/modify workflows, generate custom units (*if allowed*), make integrations.
- Inga -  **Analyst** to make deep data analysis and perform calculations
- Helen - **Dispatcher** to assign tasks to agents.
- Tom - **RL Coach** to train/fine-tune models.
- Atlas - **Planner** to break down complex tasks into smaller actionable steps.
- Demiurge - **Demiurge** to create new roles by cloning the Analyst.
----
## Quick start

**0. Clone TaskVector to your machine**
```bash
git clone https://github.com/PaulSff/ai-taskvector.git
```

**1. Install TaskVector, GUI and packages**

```bash
cd ai-taskvector
pip install -e ".[rag,gui,messengers-integrations,units-web,units-semantics,units-messengers,units-time]"
```

**2. Pull LLM**
Make sure you have installed Ollama. 

Currently, we support Ollama. Follow the [instructions](https://github.com/ollama/ollama#ollama) to download Ollama and pull LLMs (No other services are required, but the models themselves. Everything else is provided by TaskVector (memory, tools, etc.). 

**3. Run workflow server and GUI in one command**

```bash
sh run.sh
```

or

Run workflow server only:

```bash
 python services/server/workflow_server.py
```

Run GUI only:

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
├── llm_integrations
│   ├── Ollama
│   └── ...
├── gui editor (desktop/web)
├── core
│   (workflow graph, training schemas, rewards DSL, etc.)
├── deploy
│   (cross-platform nodes/pipelines deployment, external runtime roundtrip)
├── runtime
│   (native workflow executor + cross-process messaging via ZeroMQ)
└── services
│    (workflow server, zmq messaging, inference server)
└── messengers_integrations
│    ├── Telegram
│    └── ...
```

Brief overview:
- Low-code data driven concept
- Language agnostic graph: The canonical graph is capable of carrying units written in any language as code blocks. (`/core/schemas`). Explore `/docs/PROCESS_GRAPH_TOPOLOGY.md`).
- Native runtime: Python-based graph execution (`/runtime`).
- External runtimes (workflow conversion compatibility): `Node-RED`, `Pyflow`, `ComFy`, `n8n`.
- Offline local models
- Sustainable Agents memory and RAG knowledge base


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
  python agents/roles/clone_role.py --new-role operator \
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
These lines will be used to auto-generate `config/<role>.json` prompt config passed on input of the role worklflow execution.

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

We created a unified LLM client interface (`llm_integrations/client.py`) to support multiple LLM providers. Each provider has its own adapter in `llm_integrations/<provider>.py`, which converts the provider's API to a uniform interface. Create a new adapter for your provider, use the `llm_integrations/ollama.py` as a reference.
