# AI Control Agent

**Train AI agents for any purpose — no programming required.** AI Assistants create a worflow and set up the process, goals, and training for you. They will be happy to help you atomate any process you like. Data-driven design and roundtrip execution make it easy to integrate with your existing workflows.

Drop your workflow from anywhere -> Wire the training loop -> Train the model -> Plug it back in.

---

## Core idea

You describe what you want; The **AI Assistants** (Workflow Designer and Training Assistant) configure everything and train new agents for you. No need to write environment code, reward logic, or training scripts. You work with **data**: process graphs (units and connections), goals, and reward rules. The system turns that into a training run and, when you use an external runtime (Node-RED, n8n, PyFlow, ComfyUI), **roundtrip execution** lets you import a workflow, train on it, and drop the trained model back in with copy-paste–style integration.

- **No coding.** Process and training are defined by **process graphs** and **training config** (YAML/JSON). Assistants propose and apply edits (add units, set goals, tune rewards).
- **Data-driven.** One canonical schema for process and config. Multiple formats (Node-RED, PyFlow, n8n, ComfyUI, YAML) normalize to it. Unit types and behavior come from the **unit spec**; rewards use a **DSL** (formula + rule engine).
- **Self-training loops.** Training is config-driven. You (or the assistant) change goal or rewards, run training, test the policy, then iterate. Checkpoints and best-model handling are built in.
- **Roundtrip with external runtime.** Import a flow from Node-RED, n8n, PyFlow, or ComfyUI; train using that runtime as the environment (or use our built-in simulator); deploy the trained agent back into the same flow. Same workflow for design, training, and execution.
- **Language-agnostic workflows.** Python, JavaScript, or any external node code live in the graph as **code_blocks** (language tag + source). The system stores and roundtrips them without interpreting; you can mix runtimes and languages in one flow. Node-RED (JS), PyFlow/Ryven (Python), n8n (JS), ComfyUI (Python) all map to the same canonical graph and optional code. See **docs/WORKFLOW_EDITORS_AND_CODE.md**.
 **RAG think-tank directory** — An optional RAG index (e.g. `.rag_index`) supports a **think-tank directory** in a variety of formats: workflows (Node-RED/n8n JSON), node catalogues (Node-RED catalogue), and user documents (PDF, DOC, XLS). Assistants retrieve relevant context from it; the Workflow Designer can **import_unit** (add a node from the catalogue by id) or **import_workflow** from the index. See **rag/README.md**.

---

## Quick start

**1. Install (from repo root)**

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Open the Constructor GUI**

The Streamlit app is your main entry point: load or paste a process graph, edit training config, run training and test, and apply assistant edits.

```bash
streamlit run gui/app.py
```

- **Process graph:** Load example, upload Node-RED/PyFlow/n8n JSON or YAML, or paste JSON. The normalizer converts to canonical form; you see units and connections.
- **Training config:** Set goal (e.g. target temperature, volume range), rewards (preset or formula/rules), algorithm (PPO), hyperparameters. Save to file.
- **Run / Test:** Start training or test a saved model from the GUI.
- **Assistant:** Paste a Process or Training assistant edit (JSON); apply to graph or config and see the result.

**3. Train from the command line (optional)**

```bash
python train.py --config config/examples/training_config.yaml
```

Use `--process-config` for a custom process graph; use `--checkpoint` to resume. All behavior is driven by the config files the assistants (or you) produce.

**4. Test a trained model**

```bash
python test_model.py ./models/temperature-control-agent/best/best_model
```

For a visual tank demo and manual sliders (thermodynamic example):

```bash
python -m environments.custom.thermodynamics.water_tank_simulator --config config/examples/training_config.yaml --model ./models/temperature-control-agent/best/best_model
```

---

## How it works (short)

1. **Process graph** — Units (sources, valves, tank, sensor, or domain-specific) and connections. Defined in YAML/JSON or imported from Node-RED, PyFlow, n8n, ComfyUI. Unit types and “controllable” come from the **unit spec** (see **units/README.md**).
2. **Training config** — Goal (e.g. setpoint, target range), rewards (preset + weights or formula/rules), algorithm (PPO), hyperparameters. Stored as YAML/JSON.
3. **Env factory** — Builds a Gymnasium env from the process graph + config (our simulator or an external runtime adapter).
4. **Training** — Stable-Baselines3 (e.g. PPO) runs on that env; checkpoints and best model saved under `models/<agent_name>/`.
5. **Deploy** — Inject an **RLAgent** (or **LLMAgent**) node into your flow; the node calls the inference server or runs in-process. For training with an external runtime, **RLOracle** nodes expose a `/step` API; we provide templates and injectors for Node-RED, n8n, PyFlow, ComfyUI.

Assistants never write raw code; they suggest and apply **edits** to the graph and config. You (or an orchestrator) apply those edits; the rest is data and existing pipelines.

---

## Integration and roundtrip

- **Import** — Load a flow from Node-RED, PyFlow, Ryven, n8n, or ComfyUI (JSON). The normalizer maps to the canonical process graph (and optional code_blocks). See **docs/WORKFLOW_EDITORS_AND_CODE.md**.
- **Train** — With our simulator: env factory builds a GraphEnv from the graph. With external runtime: use the Node-RED, PyFlow, Ryven, n8n, or ComfyUI adapter; the flow runs in that runtime and we send actions / receive observations and rewards.
- **Deploy** — Add an RLAgent (or LLMAgent) node to the flow; wire observations and actions. Run the inference server (`python -m server.inference_server` or `server.rl_inference_server` / `server.llm_inference_server`). Export or push the flow back to your runtime. **Copy-paste integration:** export flow → paste/load in our app → train → export flow with agent node → import into Node-RED/n8n/etc.

Details: **docs/DEPLOYMENT_NODERED.md**, **deploy/README.md**, **server/README.md**.

---

## Docs and next steps

| Doc | Content |
|-----|--------|
| **docs/VISION.md** | Constructor idea, data model, two AI roles, no-code/low-code path. |
| **docs/PROCESS_GRAPH_TOPOLOGY.md** | Canonical process graph: units, connections, agent/oracle types, unit spec. |
| **docs/DEPLOYMENT_NODERED.md** | Node-RED roundtrip: import, train, deploy; agent detection and scenarios. |
| **docs/WORKFLOW_EDITORS_AND_CODE.md** | PyFlow, Ryven, n8n, ComfyUI; import/export; code_blocks; adapters. |
| **docs/REWARD_RULES.md** | Formula, rule engine, text-to-reward; rewards DSL. |
| **deploy/README.md** | RLOracle and RLAgent injection; inference server; templates. |
| **server/README.md** | Run inference server and ComfyUI bridge. |
| **units/README.md** | Unit spec, registry, how to add unit types. |
| **gui/README.md** | Constructor GUI and Node-RED flow format. |

**Apply assistant edits from the CLI:**

```bash
# Process Assistant: apply graph edit (add/remove/connect units)
python -m assistants apply_graph --graph config/examples/temperature_process.yaml --edit edit.json [--out path]

# Training Assistant: apply config edit (goal, rewards, hyperparameters)
python -m assistants apply_config --config config/examples/training_config.yaml --edit edit.json [--out path]
```

**Chat with the model (optional):**

- Local LLM (Ollama): `python chat_with_local_ai.py` (see repo for setup).
- Rule-based (no setup): `python chat_with_model.py`.

---

## Project structure (summary)

```
├── gui/                    # Constructor GUI (Streamlit): graph, config, run/test, assistant
├── assistants/             # Process + Training assistants; graph edits; Workflow Designer prompts
├── normalizer/             # All formats → canonical process graph + training config
├── schemas/                # Process graph, training config, agent nodes
├── env_factory/            # Process graph + config → Gymnasium env
├── environments/           # GraphEnv, custom envs (thermodynamics, data_bi), external adapters
├── units/                  # Unit spec (registry); thermodynamic + data_bi + agent/oracle
├── deploy/                 # Inject RLOracle/RLAgent/LLMAgent into Node-RED, PyFlow, n8n, ComfyUI
├── server/                 # Inference server (RL + LLM), ComfyUI bridge
├── rewards/                # Reward formula + rule engine (DSL)
├── train.py, test_model.py
├── config/examples/        # Example process and training configs
└── docs/                   # VISION, topology, deployment, rewards, workflows
```

---

## License

MIT License — use and modify for your projects.
