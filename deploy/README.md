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

**Environment-agnostic.** Canonical units (Join, Switch, StepDriver, Split, StepRewards, HttpIn, HttpResponse) and RLAgent, LLMAgent, RLGym, RLOracle are **environment-agnostic**: they are registered for all environments (thermodynamics, data_bi, and any custom env), not only thermodynamics. See `units/register_env_agnostic.py` and `environments/graph_env.py`.

**RLGym vs RLOracle vs RLAgent/LLMAgent.**

- **RLGym** (new): Full training setup for **our own runtime**. Add an RLGym node with `observation_source_ids` and `action_target_ids`; the graph gets full canonical topology: observations → Join → StepRewards, Switch → actions, StepDriver → Split → simulators. The policy runs in the training loop (e.g. SB3), not in the graph; no RLAgent node required for training.
- **RLOracle**: Kept for **external** training (Node-RED, n8n, PyFlow deploy). Adds the Oracle pair (step_driver + collector) and canonical units for deployment to those runtimes.
- **RLAgent / LLMAgent**: When added, **short topology** only: observations → Join → RLAgent/LLMAgent → Switch → actions (Join and Switch only; no StepRewards, StepDriver, Split). Used for inference or when the agent is in the graph; for training in our runtime, add **RLGym** instead to get the full setup.

```
  INLINE (our runtime)                    EXTERNAL (HTTP opt-in)
  No step_router. Executor injects          step_router demuxes request
  trigger + action directly.                into trigger + action.

  [Training loop]                         [Training loop]
       │                                       │
       │ obs ← env.step()                      │ POST /step { action }
       │ action = policy(obs)                  │ obs, reward, done ← response
       ▼                                       ▼
  ┌─────────────┐                         ┌───────────┐
  │  Executor   │                         │  http_in  │
  │ injects     │                         └─────┬─────┘
  │ trigger +   │                               │
  │ action     │                         ┌──────▼──────┐
  └─────┬──────┘                         │ step_router│ (only when HTTP present)
        │                                └──┬───────┬──┘
        │ trigger                           │       │ action
        ▼                                  ▼       ▼
  ┌─────────────┐                    ┌──────────┐  ┌────────┐
  │ StepDriver  │                    │StepDriver│  │ Switch │
  └──────┬──────┘                    └────┬─────┘  └───┬────┘
         │ start                          │             │
         ▼                                ▼             ▼
  ┌─────────────┐                    ┌──────────┐   [action targets]
  │   Split     │                    │  Split   │
  └──────┬──────┘                    └────┬─────┘
         │                                │
         ▼                                ▼
  [simulators 1..n]                 [simulators 1..n]

  action ▼ (injected)                (same process graph below)

  ┌─────────────┐
  │   Switch   │  ◄── action from training loop (inline) or step_router (HTTP)
  └──────┬──────┘
         │
         ▼
  [action targets: valves, setpoints, ...]

  [observation sources: Tank, Sensor, ...]
         │
         ▼
  ┌─────────────┐
  │    Join     │  observation vector
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐     observation, reward, done
  │ StepRewards │  ───────────────────────────►  Executor / env  (inline)
  └──────┬──────┘                               or http_response (external)
         │ payload (obs, reward, done)
         ▼
  (http_response only when HTTP present)

  ┌─────────────┐
  │ RLGym or    │  RLGym: full training topology (obs/act from params). Not executed.
  │ RLAgent     │  RLAgent: short topology; policy runs in training loop when training.
  └─────────────┘
```

- **step_router**: Only in the **external (HTTP)** path. Demuxes http_in request into trigger (→ StepDriver) and action (→ Switch). **Inline path has no step_router** — the executor injects trigger and action directly into StepDriver and Switch.
- **Join**: observation sources → one observation vector (read by StepRewards and by executor/env).
- **StepRewards**: Join → observation; executor injects trigger + outputs. Produces observation, reward, done (and payload for http_response). Same unit for inline and external.
- **Switch**: action demux. Input = action from training loop (inline: executor injects; external: step_router out 1). Outputs → action targets.
- **StepDriver**: trigger (reset/step) → Split → simulators. Trigger from executor (inline) or step_router out 0 (external).
- **RLAgent**: Required for canonical training. Provides actions via the training loop; reads observations via env (from StepRewards/Join). Not executed by the graph.

**Two pipelines for our runtime (inline training).** The wiring is:

1. **Observation → policy → action** (logical): **observations → Join → StepRewards → RLAgent → Switch → actions.**  
   In the graph: observation sources (from RLGym or RLAgent `observation_source_ids`) → Join; Join → StepRewards. The executor/env reads observation (and reward, done) from Join/StepRewards. The training loop gets obs from the env, calls the policy (outside the graph), gets an action, and passes it to `env.step(action)`; the executor injects that action into the Switch. Switch → action targets (from RLGym or RLAgent `action_target_ids`). The policy runs in the training loop; RLGym/RLAgent node is not executed.

2. **Environment step** (simulators): **StepDriver → Split → simulators.**  
   Trigger (reset/step) is injected by the executor into StepDriver. StepDriver output 0 (start) → Split → each simulator (Source, Tank, etc.). This pipeline is independent of the observation/action pipeline; it only advances the process each step.

**HTTP is opt-in.** `http_in` and `http_response` are **excluded from standard wiring**. Add them when you want the runtime callable from outside (e.g. HTTP `/step`). Then: http_in → step_router (Switch, 2 outs) → step_driver + Switch; StepRewards.payload → http_response → client.

**Alignment with implementation.** The executor skips RLGym, RLAgent, RLOracle, LLMAgent (`EXECUTOR_EXCLUDED_TYPES`). It injects trigger into StepDriver and StepRewards, and action into Switch; it reads observation (and optionally reward/done) from Join/StepRewards. Adding **RLGym** creates full training topology (Join, StepRewards, Switch, StepDriver, Split). Adding **RLAgent** or **LLMAgent** creates short topology (Join, Switch only). Adding **RLOracle** creates full topology including HTTP (http_in, step_router, http_response) plus the Oracle pair for external deploy. For our runtime (RLGym), HTTP is not added by default.

**Full setup on export.** When you export the process graph to Node-RED, n8n, or PyFlow, the **whole setup** is emitted as runnable code: RLOracle and RLAgent/LLMAgent (from their code_blocks) plus **canonical units** (step_driver, join, switch, split, step_rewards). If a canonical unit has no code_block, the normalizer uses **deploy.canonical_inject** to generate code from templates at export time, so every such unit becomes a function/code node in the exported flow.

**Deploy alignment (our runtime vs external).** The same canonical units are used for both; only the transport differs (no HTTP for our runtime unless added).

| Unit | Our runtime (inline) | External (Node-RED / n8n / PyFlow) |
|------|----------------------|-----------------------------------|
| Join, Switch, StepDriver, Split | Executed by GraphExecutor; templates in `deploy/templates/canonical_*.py`, `canonical_*.js` | Exported as function/code nodes from same templates |
| StepRewards | Executor + StepRewards unit; observation, reward, done from one place | Template `canonical_step_rewards.py` / `canonical_step_rewards.js` at export; same semantics (reward DSL, done = step_count >= max_steps) |
| HttpIn, HttpResponse | Not in standard wiring; add when you want HTTP | Node-RED: map to platform nodes `http in`, `http response`. No code template; export uses type map. |
| RLGym | Full topology (Join → StepRewards, Switch, StepDriver → Split); no deploy nodes | Not deployed as nodes; use for our runtime only |
| RLOracle | Not used (we use RLGym) | step_driver + collector + HTTP (added by default); templates `rloracle_*` |

All canonical units (including StepRewards) have templates so export produces runnable flows with aligned semantics. RLAgent/LLMAgent have predict templates; RLOracle has step_driver + collector templates for external deploy.

**If I add RLOracle to my workflow imported from Node-RED, will the whole setup be added?**  
Yes. Adding an RLOracle node (in the workflow designer, to a graph imported from Node-RED or any other source) triggers:

- **Full canonical topology**: Join, Switch, StepDriver, Split, and StepRewards are created and wired (observation sources → Join → StepRewards; Switch → action targets; StepDriver → Split → simulators).
- **Oracle pair**: RLOracle step_driver and RLOracle collector are added, with observation sources → collector and step_driver → canonical Switch and StepDriver.
- **HTTP for external runtimes**: Because RLOracle is for external deploy (Node-RED, n8n, PyFlow over HTTP), **http_in, step_router, and http_response are added by default** when you add RLOracle. The graph is ready to expose `/step` when exported. StepRewards.payload → http_response.
- **Code blocks**: The Oracle step_driver and collector get code from the appropriate template (JavaScript for Node-RED/n8n, Python for PyFlow).

For **our runtime** (RLGym), HTTP is not added by default; add HttpIn and HttpResponse only when you want to call the runtime from outside.

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
| `canonical_step_driver.js` | Node-RED/n8n canonical StepDriver (trigger → start + response) |
| `canonical_join.js` | Node-RED/n8n canonical Join (accumulate → observation vector) |
| `canonical_switch.js` | Node-RED/n8n canonical Switch (action vector → out_0..out_n) |
| `canonical_split.js` | Node-RED/n8n canonical Split (trigger → fan-out) |
| `canonical_step_driver.py` | PyFlow canonical StepDriver |
| `canonical_join.py` | PyFlow canonical Join |
| `canonical_switch.py` | PyFlow canonical Switch |
| `canonical_split.py` | PyFlow canonical Split |

Placeholders (e.g. `__TPL_INFERENCE_URL__`, `__TPL_NUM_INPUTS__`) are replaced at render time. Canonical templates are used by **deploy.canonical_inject** when exporting a graph so that units with canonical roles get code if they have no code_block.

**Existing demux-style nodes.** We looked for an existing Node-RED node that demuxes an array to indexed outputs (payload[i] → output i). **[node-red-contrib-msg-router](https://flows.nodered.org/node/node-red-contrib-msg-router)** supports routing (broadcast, round-robin, message-based via `msg.output`): you still need a preceding Function to turn one message with `payload: [a,b,c]` into messages with the right `output` and payload. The [Node-RED community pattern](https://groups.google.com/g/node-red/c/ThYtMXIZ81o) for "array → each element to its own output" is a **Function node with N outputs** that returns an array of N message objects. That is what our canonical Switch template does, so we did not add a dependency on msg-router. Alternatives (core Split + Switch by `msg.parts.index`) use two nodes; a single Function node is the standard approach for our demux semantics.

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
