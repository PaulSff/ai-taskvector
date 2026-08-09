# AI TaskVector

Your personal AI assistant and agents factory that runs explicitly on your machine.
--- 
- **Runtime**: allows for easy creation of custom AI agents/agent teams working 24/7, while you sleep;
- **Custom automations**: creates and runs automations by means of its own built-in low-code framework;
- **Skills/Roles**: talks to your data, works with documents/spreadsheets, does analysis, chats over messengers, schedules events over calendar, creates and runs workflow automations, handles coding tasks/works with files, etc.;
- **Local models**: via llama.cpp and Ollama;
- **Local tools**: via automation workflows *(exchangeable with n8n, NodeRED, Pyflow, Comfy)*;
- **MCP host**: tools and resources via MCP; MCPTool and MCPSource units providing the calls inside workflows;
- **RAG**: local RAG & memory;
- **Self-evolving**: builds itsef "out of bricks", RL gym + RL coach to train models;
- **Channels**: WEB & Desktop (Flet), Telegram.

<img width="2352" height="1720" alt="ai-taskvector_screen" src="https://github.com/user-attachments/assets/a732d2ee-873d-4c0b-a29a-67803a64780a" />

## Quick start

**Rename**: `config/app_settings_example.json` -> `config/app_settings.json`

### macOS / Linux
Install:
```bash
curl -fsSL https://github.com/PaulSff/ai-taskvector/raw/master/install.sh | bash
```
Run:
```bash
cd ai-taskvector
sh run.sh
```
### Windows
Install:
```powershell
irm https://github.com/PaulSff/ai-taskvector/raw/master/install.ps1 | iex
```
Run:
```powershell
cd ai-taskvector
.\run.ps1
```

Docker:
```bash
docker compose build
docker compose up
```

Then open the Flet GUI in your browser at **http://localhost:8550**. The app is configured to use the Ollama service automatically via `OLLAMA_HOST`.

Pull a model in Ollama (one-time):

```bash
docker compose exec ollama ollama pull gemma4:31b-cloud
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
| `OLLAMA_MODEL` | Default model name (e.g. `gemma4:31b-cloud`) when not set in GUI settings. |
| `OLLAMA_API_KEY` | Optional; for Ollama Cloud. |

**Docker Files**

- `Dockerfile` — Full install (main + RAG + Flet GUI + units); default command runs the Flet GUI.
- `docker-compose.yml` — App + Ollama service; Flet runs in web mode on port 8550.

---

## Install manually
**0. Clone TaskVector to your machine**
```bash
git clone https://github.com/PaulSff/ai-taskvector.git
```

**1. Install TaskVector, GUI and packages**

```bash
cd ai-taskvector
pip install -e ".[rag,gui,llm-integrations,messengers-integrations,units-web,units-semantics,units-messengers,units-time,units-network,mcp-integrations]"
```

**2. Pull LLM**
Make sure you have installed Ollama. 

Currently, we support Ollama. Follow the [instructions](https://github.com/ollama/ollama#ollama) to download Ollama and pull LLMs (No other services are required, but the models themselves. Everything else is provided by TaskVector (memory, tools, etc.). 

**3. Run workflow server and GUI**

Run workflow server:

```bash
 python services/server/workflow_server.py
```

Run GUI:

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

## Configuration
- `config/app_settings.json` - general settings **rename**: *app_settings_example.json*
- `config/prompts/<role>.json` - role prompt used on agent workflow execution
- `rag/ragconf.yaml` - rag config
- `roles/<role>/role.yaml` - agent role config
- `tools/<tool>/tool.yaml` - agent tool config
- `mydata/`- default folder for your data (set up any folder)
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
    --responsibility "Responsible for X..." \
    --intro "Hello, I'm Admin at TaskVector..." \
    --tools grep read_file formulas_calc ...     
```
- `--new-role` (mandatory) - new agent role name (e.g. administrator, sales manager, account manager, etc.)
- `--character-name`(mandatory) - any human-like name for the character to interact with 
- `--responsibility` - responsibility descritpion
- `--intro` - one sentence introduction
- `--tools` - a set of tools available for the agent (pick up the tools from here: `agents/tools`)
- `--intro-body`  e.g. "You do servers administration jobs and address users requests.."
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

---

## Creating new units and tools

- Follow this guide to create custom units (nodes): `units/CREATING-NEW-UNIT.md`
- Explore new tools development guide: `agents/tools/README.md`

## LLM Integrations

We created a unified LLM client interface (`llm_integrations/client.py`) to support multiple LLM providers. Each provider has its own adapter in `llm_integrations/<provider>.py`, which converts the provider's API to a uniform interface. Create a new adapter for your provider, use the `llm_integrations/ollama.py` as a reference.

## Messengers integrations

- Follow the Telegram example (`messengers_integrations/telegram`) to integrate new provider into the system. 
- Create a unit for the messenger to interact with from the workflow. Reference: `units/messengers/telegram_bot`
- Create a gateway for your messenger. Use the telegram gateway (`agents/chat/telegram_gateway`) as a reference to wire new messenger into the agents flow. 

## Contribution

Thanks for considering a contribution — we welcome fixes, features, docs, tests, and new units/agents. Fork the repo and follow the [contribution guidelines](/docs/CONTRIBUTING.md).

## Stage

**Beta version!** Use it at your own risk.

## License

[MIT](LICENSE) — use and modify for your projects.
