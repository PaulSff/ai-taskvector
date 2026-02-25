# Deploy: Injected Nodes for PyFlow, Node-RED, n8n

This module provides template-based injection of **RLOracle** (training) and **RLAgent** (inference) nodes into workflow runtimes. All parameters come from training config; no embedded simulations.

---

## Overview

| Component | Phase | API |
|-----------|-------|-----|
| **RLOracle** | Training (environment) | HTTP POST `/step` (reset/step) |
| **RLAgent** | Inference (policy) | HTTP POST `/predict` |
| **Inference server** | Serves RLAgent and/or LLMAgent at runtime | `python -m server.inference_server` (unified) or `server.rl_inference_server` / `server.llm_inference_server` (thin entry points) |
| **ComfyUI bridge** | Serves RLOracle for ComfyUI workflows | `python -m server.comfyui_bridge` |

**Two different servers, two different phases.** During **training**, the RL loop needs an environment that accepts actions and returns observations/rewards (RLOracle via `/step`). During **inference**, the workflow needs a policy that accepts observations and returns actions (RLAgent via `/predict`). Node-RED and n8n expose `/step` directly from their flow. ComfyUI needs the bridge to wrap its API and expose `/step` for training. The inference server is the same for all runtimes — run it when you deploy the trained model; the flow’s RLAgent node calls it.

---

## RLOracle (Training)

RLOracle exposes a step endpoint so the training loop can drive the process. It consists of:

- **Step driver**: Accepts `{ "action": [...] }` or `{ "reset": true }`, routes to process, returns observation/reward/done.
- **Collector**: Aggregates observations from sensors (by `topic`), computes reward from `reward_config`, returns response.

Parameters from `adapter_config`: `observation_spec`, `action_spec`, `reward_config`, `max_steps`.

### PyFlow

- **Structure**: Two units (`{oracle_id}_step_driver`, `{oracle_id}_collector`) with Python `code_blocks`.
- **Templates**: `rloracle_step_driver.py`, `rloracle_collector.py`
- **Execution**: In-process; PyFlow adapter runs the code blocks. No HTTP.
- **Convention**: `state["__rl_oracle_action__"]` holds the action; collector reads `inputs` from wired observation sources.

### Node-RED

- **Structure**: HTTP In → step driver (function) → HTTP Response + process; collector (function) receives sensor wires.
- **Templates**: `rloracle_step_driver.js`, `rloracle_collector.js`
- **Nodes**: `http in` (POST /step), `function` (step driver, 2 outputs), `function` (collector), `http response`
- **Convention**: Sensors send `msg.topic = observation_name`, `msg.payload = value`. Step driver uses `flow.get/set` for state.
- **Formula/rules reward (DSL)**: Add `expr-eval` to `settings.js` so the collector can evaluate formula and rules:
  ```js
  functionGlobalContext: {
    exprEval: require('expr-eval')
  }
  ```
  Then: `cd ~/.node-red && npm install expr-eval`

### n8n

- **Structure**: Webhook → step driver Code → Merge; collector Code → Merge → Respond to Webhook.
- **Templates**: `rloracle_step_driver_n8n.js`, `rloracle_collector_n8n.js` (use `$getWorkflowStaticData`)
- **Nodes**: `n8n-nodes-base.webhook`, `n8n-nodes-base.code` (step driver), `n8n-nodes-base.code` (collector), `n8n-nodes-base.merge`, `n8n-nodes-base.respondToWebhook`
- **Convention**: Same as Node-RED for observation `topic`; state in `$getWorkflowStaticData('global')`.
- **Formula/rules reward (DSL)**: Set `NODE_FUNCTION_ALLOW_EXTERNAL=expr-eval` and install: `npm install expr-eval` (in the n8n environment). Self-hosted only; n8n Cloud does not support external modules.

### ComfyUI

- **Structure**: RLOracleStepDriver + RLOracleCollector custom nodes. Bridge exposes `/step`.
- **Custom nodes**: `deploy/custom_nodes/ai_control_rl/` (copy into `ComfyUI/custom_nodes/ai_control_rl/`)
- **Bridge**: `python -m server.comfyui_bridge --workflow workflow.json --port 8189 --comfy-url http://127.0.0.1:8188`
- **Convention**: Step driver reads action from file (set by bridge); collector writes `{observation, reward, done}` to file for bridge to return.
- **Adapter**: Use `adapter: comfyui`, `step_url: http://127.0.0.1:8189/step`.

---

## RLAgent (Inference)

RLAgent runs the trained policy at runtime. All runtimes use the same HTTP API: a thin client that POSTs observations and receives actions.

### Agent model options

The agent node can use different backends. Configure them via the unit **params** (e.g. when adding an RLAgent in the Workflow Designer or when injecting into a flow):

| Option | Description | Params |
|--------|-------------|--------|
| **Local model (our system)** | Model trained in this repo (SB3/PPO), served by `server.inference_server` or `server.rl_inference_server`. | `model_path` = path to the model (e.g. `models/temperature-control-agent/best/best_model.zip`). `inference_url` = URL of the server (default `http://127.0.0.1:8000/predict`). |
| **Our server (deployed)** | Same inference server running elsewhere; model is chosen by the server. | `inference_url` = deployed server URL (e.g. `https://rl-inference.example.com/predict`). `model_path` can be empty or a hint. |
| **External model** | Policy or API from another provider (Ollama, Hugging Face, custom endpoint). Must expose the same contract: POST with `{ "observation": [...] }` → `{ "action": [...] }`. | `inference_url` = provider’s predict endpoint. `model_path` can be empty. |

When adding an agent, the Workflow Designer asks which model the user wants and sets these params accordingly.

### LLM agents (local or external)

If the agent is an **LLM** (language model), the same model options apply (local path, our server, or external). The **LLM_integrations** (e.g. Ollama) are chat-based (messages → text), so they are not a drop-in RLAgent backend: an adapter must turn observation → prompt → LLM call → parsed action (e.g. a small server or in-process code using `LLM_integrations.client.chat`). In addition to `inference_url` (or in-process provider config), set:

| Param | Description |
|-------|-------------|
| `model_name` | Model name for the provider (e.g. `llama3.2` for Ollama). Required for LLM backends; for SB3 use `model_path` instead. |
| `system_prompt` | System message for the LLM (role, task, output format). |
| `user_prompt_template` | Optional. Template for the user message, with a placeholder for observations (e.g. `"Observations: {observation_json}. Reply with action JSON."`). |
| `provider` | Optional. When calling **LLM_integrations** in-process, the provider id (e.g. `ollama`). Not needed if inference_url points to an adapter that already selects the provider. |

These apply whether the LLM is served locally (our server or same machine) or by an external provider.

### PyFlow

- **Structure**: Single node with Python `code_block`.
- **Template**: `rl_agent_predict.py`
- **Execution**: PyFlow adapter runs the code block; it uses `urllib.request` to call the inference server.

### Node-RED

Two deployment styles:

1. **Single function node** (canonical export): One `function` node with `rl_agent_predict.js`. Accumulates observations via `flow.get/set`, POSTs to inference, returns action.
2. **Three-node subflow** (`inject_agent_template_into_flow`): Prepare (function) → HTTP Request → Parse (function). Prepare builds the request; parse extracts the action.

- **Templates**: `rl_agent_predict.js` (single node), or `rl_agent_prepare.js` + `rl_agent_parse.js` (three-node)
- **Convention**: Upstream nodes send `msg.topic = observation_source_id`, `msg.payload = value`.

### n8n

- **Structure**: Single Code node.
- **Template**: `rl_agent_predict_n8n.js`
- **Execution**: Uses `$getWorkflowStaticData`, `$input.all()`, `this.helpers.httpRequest`.
- **Convention**: Upstream items have `json.topic` = observation source id, `json.payload` or `json.value`.

### ComfyUI

- **Structure**: RLAgentPredict custom node.
- **Custom nodes**: Same `deploy/custom_nodes/ai_control_rl/` package.
- **Convention**: Observations wired to agent inputs; agent calls inference API, outputs action to connected nodes.

---

## Universal API

### Inference (RLAgent)

```
POST /predict
Content-Type: application/json

Request:  { "observation": [float, ...] }
Response: { "action": [float, ...] }
```

**Unified server** (one process for both RL and LLM):

```bash
# RL only (requires --model)
python -m server.inference_server --model path/to/model.zip --rl-only --port 8000

# LLM only
python -m server.inference_server --llm-only --port 8000

# Both: RL when --model given; request body selects path (LLM if system_prompt/model_name present)
python -m server.inference_server --model path/to/model.zip --port 8000
```

**Thin entry points** (same process, just preset flags):

```bash
python -m server.rl_inference_server --model path/to/model.zip
python -m server.llm_inference_server --port 8001
```

Default: `http://127.0.0.1:8000/predict`. One endpoint: RL path for `{ "observation": [...] }` when an RL model is loaded; LLM path for bodies with `system_prompt` / `model_name` (and observation). Use `--llm-only` or `--rl-only` to disable one path.

### Oracle Step (RLOracle)

```
POST /step
Content-Type: application/json

Reset:  { "reset": true }
        → { "observation": [...], "reward": 0, "done": false }

Step:   { "action": [float, ...] }
        → { "observation": [...], "reward": float, "done": bool }
```

---

## Python API

### RLOracle

| Function | Runtime | Description |
|----------|---------|-------------|
| `inject_oracle_into_flow(flow, adapter_config, ...)` | Node-RED | Add Oracle nodes to Node-RED flow |
| `inject_oracle_into_n8n_flow(flow, adapter_config, ...)` | n8n | Add Oracle nodes to n8n workflow |
| `inject_oracle_into_comfyui_workflow(workflow, adapter_config, ...)` | ComfyUI | Add RLOracle nodes to ComfyUI workflow |
| `inject_oracle_into_process_graph(graph, adapter_config, ...)` | Canonical | Add Oracle units + code_blocks to ProcessGraph |

### RLAgent

| Function | Runtime | Description |
|----------|---------|-------------|
| `inject_agent_into_flow(flow, agent_id, model_path, obs_ids, action_ids, ...)` | Node-RED | Add bare RLAgent node (no code) |
| `inject_agent_template_into_flow(flow, agent_id, model_path, obs_ids, action_ids, ...)` | Node-RED | Add prepare + HTTP + parse nodes |
| `inject_agent_into_pyflow_flow(flow, agent_id, model_path, obs_ids, action_ids, ...)` | PyFlow | Add RLAgent node with Python code_block |
| `inject_agent_into_n8n_flow(flow, agent_id, model_path, obs_ids, action_ids, ...)` | n8n | Add bare RLAgent node (no code) |
| `inject_agent_into_comfyui_workflow(workflow, agent_id, model_path, obs_ids, action_ids, ...)` | ComfyUI | Add RLAgentPredict node |

When using the GUI or `apply_graph_edit` to add an RLAgent unit, a code_block is added automatically based on graph origin (Python for PyFlow/Ryven, Node-RED JS for Node-RED, n8n JS for n8n). Export then emits executable nodes.

### LLMAgent

| Function | Runtime | Description |
|----------|---------|-------------|
| `inject_llm_agent_into_flow(flow, agent_id, obs_ids, action_ids, ...)` | Node-RED | Add LLMAgent function node (code + wires) |
| `inject_llm_agent_into_pyflow_flow(flow, agent_id, obs_ids, action_ids, ...)` | PyFlow | Add LLMAgent node with Python code_block |
| `inject_llm_agent_into_n8n_flow(flow, agent_id, obs_ids, action_ids, ...)` | n8n | Add LLMAgent Code node |

Run `python -m server.llm_inference_server --port 8001` (or `server.inference_server --llm-only`) so flows can call the LLM. When adding an LLMAgent unit via `apply_graph_edit`, a code_block is added automatically (Python or JS by origin).

---

## Templates

| File | Use |
|------|-----|
| `rloracle_step_driver.js` | Node-RED Oracle step driver |
| `rloracle_collector.js` | Node-RED Oracle collector |
| `rloracle_step_driver_n8n.js` | n8n Oracle step driver |
| `rloracle_collector_n8n.js` | n8n Oracle collector |
| `rloracle_step_driver.py` | PyFlow Oracle step driver |
| `rloracle_collector.py` | PyFlow Oracle collector |
| `rl_agent_predict.py` | PyFlow RLAgent (single node) |
| `rl_agent_predict.js` | Node-RED RLAgent (single function node) |
| `rl_agent_predict_n8n.js` | n8n RLAgent (Code node) |
| `rl_agent_prepare.js` | Node-RED prepare (three-node style) |
| `rl_agent_parse.js` | Node-RED parse (three-node style) |
| `llm_agent_predict.py` | PyFlow LLMAgent (POST to LLM inference server) |
| `llm_agent_predict.js` | Node-RED LLMAgent (single function node) |
| `llm_agent_predict_n8n.js` | n8n LLMAgent (Code node) |

Placeholders (e.g. `__TPL_INFERENCE_URL__`) are replaced at render time.

---

## Observation convention

- **Observation names/source ids**: Order matters; must match training `observation_spec` order.
- **Node-RED / n8n**: Sensors send `topic` = observation name or source id, `payload` = numeric value.
- **PyFlow**: Wired upstream nodes; code receives `inputs` dict keyed by source id.
- **Value extraction**: Supports `payload` as number, `{ value }`, `{ temp }`, `{ volRatio }`.

---

## Reward DSL (formula/rules) on Node-RED and n8n

When `reward_config` has `formula` or `rules`, the collector evaluates the DSL to compute rewards. This requires the `expr-eval` package:

| Runtime   | Setup |
|----------|-------|
| **Node-RED** | 1. Add to `settings.js` (`~/.node-red/`): `functionGlobalContext: { exprEval: require('expr-eval') }`<br>2. `cd ~/.node-red && npm install expr-eval` |
| **n8n**      | 1. Set env: `NODE_FUNCTION_ALLOW_EXTERNAL=expr-eval`<br>2. Install: `npm install expr-eval` in the n8n install directory |

Without this setup, the collector falls back to setpoint or static reward. PyFlow uses the Python rewards pipeline directly (no extra config).
