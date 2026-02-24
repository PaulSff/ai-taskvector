# Deploy: Injected Nodes for PyFlow, Node-RED, n8n

This module provides template-based injection of **RLOracle** (training) and **RLAgent** (inference) nodes into workflow runtimes. All parameters come from training config; no embedded simulations.

---

## Overview

| Component | Phase | API |
|-----------|-------|-----|
| **RLOracle** | Training (environment) | HTTP POST `/step` (reset/step) |
| **RLAgent** | Inference (policy) | HTTP POST `/predict` |
| **Inference server** | Serves RLAgent at runtime | `python -m deploy.rl_inference_server` |
| **ComfyUI bridge** | Serves RLOracle for ComfyUI workflows | `python -m deploy.comfyui_bridge` |

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
- **Bridge**: `python -m deploy.comfyui_bridge --workflow workflow.json --port 8189 --comfy-url http://127.0.0.1:8188`
- **Convention**: Step driver reads action from file (set by bridge); collector writes `{observation, reward, done}` to file for bridge to return.
- **Adapter**: Use `adapter: comfyui`, `step_url: http://127.0.0.1:8189/step`.

---

## RLAgent (Inference)

RLAgent runs the trained policy at runtime. All runtimes use the same HTTP API: a thin client that POSTs observations and receives actions.

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

Run the inference server:

```bash
python -m deploy.rl_inference_server --model path/to/model.zip
python -m deploy.rl_inference_server --model path/to/model.zip --port 8001 --host 0.0.0.0
```

Default: `http://127.0.0.1:8000/predict`

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
