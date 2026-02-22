# Workflow editors (PyFlow, Ryven) and code in the canonical format

This doc covers: **PyFlow** and **Ryven** as Python-native alternatives to Node-RED for our runtime; importing **full workflows** from both PyFlow and Node-RED **including functions/code**; and expanding our **canonical JSON format** to accept **code** in a language-agnostic way.

---

## JSON workflow export/import by framework

| Framework | JSON workflow export? | Our import support | Normalizer format |
|-----------|------------------------|--------------------|--------------------|
| **Node-RED** | Yes. Flows export as JSON (menu → Export; compact or formatted). Standard structure: array of nodes or `{ flows: [ { nodes: [] } ] }`, nodes have `id`, `type`, `wires`, `func`/`code` for function nodes. | Yes | `node_red` |
| **EdgeLinkd** | Yes. Drop-in Node-RED–compatible `flows.json`; same JSON shape as Node-RED. | Yes (same as Node-RED) | `node_red` |
| **PyFlow** | Yes. Project/graph serialization: top-level `nodes` + `connections`/`edges`/`wires`, or `graphManager.graphs[].nodes` and graph-level connections. GraphManager → graphs → nodes hierarchy. | Yes | `pyflow` |
| **Ryven** | Yes. ryvencore uses JSON for project persistence; typical layout: `scripts[].flow` with `nodes` and `connections`/`links`/`edges`. | Yes | `ryven` |
| **IDAES** | Partial. Flowsheet **layout** can be saved to JSON via the Flowsheet Visualizer (`save_as="file.json"`). Model **state** (variable values) has `to_json`/`from_json` in idaes.core.util.model_serializer. Topology is **not** exported as JSON; we import via **template-like** dict (units + connections) or by **introspecting** a live Pyomo model. | Yes (template-like or introspected) | `idaes` |
| **n8n** | Yes. Workflow export as JSON (Editor → Download / Import from File). Structure: `nodes` (array with `id`, `name`, `type`, `typeVersion`, `position`, `parameters`), `connections` (object keyed by **node name**: `{ "NodeName": { "main": [[ { "node": "TargetName", "type": "main", "index": 0 } ]] } }`). Code node: `n8n-nodes-base.code` with `parameters.jsCode`. | Yes | `n8n` |

**Agent/orchestration frameworks (not visual workflow editors):** [Microsoft Agent Framework](https://github.com/microsoft/agent-framework), [AutoGen](https://github.com/microsoft/autogen), and [Semantic Kernel](https://github.com/microsoft/semantic-kernel) are code-first agent/orchestration frameworks (multi-agent, plugins, graph-based orchestration). They do **not** provide the same “visual editor exports JSON workflow” format that we import for process graphs; our roundtrip is built around Node-RED, PyFlow, Ryven, and EdgeLinkd.

**Usage:** Load a JSON file with the right format: `to_process_graph(raw, format="node_red"|"pyflow"|"ryven"|"idaes")` or `load_process_graph_from_file(path, format="ryven")` (for `.json` we default to `node_red`; pass `format="pyflow"`, `format="ryven"`, or `format="idaes"` explicitly when needed).

---

## 1. PyFlow and Ryven as native Python alternatives to Node-RED

| Editor | Stack | Notes |
|--------|--------|--------|
| **PyFlow** | Python, node-based visual scripting | [PyFlow](https://github.com/pedroCabrera/PyFlow). Canvas, nodes, pins; Python script export; custom importers/exporters. Python-native; trained model can run as a node in the workflow. |
| **Ryven** | Python, flow-based (ryvencore + Ryven app) | [Ryven](https://github.com/leon-thomm/Ryven), [ryvencore](https://github.com/leon-thomm/ryvencore). Node graphs, run flows via Ryven Console or ryvencore; nodes are Python classes. Python-native; trained model as node fits the same roundtrip story. |
| **Node-RED** | Node.js, browser UI | Already supported: import flow JSON (process topology); roundtrip = import full workflow → train via node_red_adapter → use trained model in the flow. |

**Should we consider PyFlow or Ryven for our native runtime?**

- **Yes.** For a **Python-native** stack, PyFlow or Ryven are natural alternatives to Node-RED: same roundtrip idea (import full workflow → train full process via adapter → use trained model as a node in the workflow). We would add adapters analogous to `node_red_adapter`: e.g. **pyflow_adapter** and **ryven_adapter** that wrap the editor’s runtime as a Gymnasium env (sensors in, actions out) and, for deployment, inject the trained model as a node.
- **Choice:** PyFlow has explicit Python script export and custom IO; Ryven emphasizes running flows via ryvencore. Both can represent process topology + code; we’d need to map their export formats to our canonical format (see below).

---

## 2. Import full workflows from PyFlow and Node-RED including functions

We **import full workflows** from Node-RED and PyFlow: all nodes, all connections, and code in **code_blocks** (function/exec/template nodes). For that we have:

1. **A way to represent code in our data model** — e.g. function bodies, script content, per-node or global.
2. **Adapters** that map PyFlow and Node-RED exports (including code) into that representation.
3. **Roundtrip**: preserve the full workflow (topology + code) so we can re-export or sync back after training (e.g. add the “RL Agent” node).

So: **yes, we should aim to import full workflows from both PyFlow and Node-RED including functions.** That implies expanding our canonical format to carry code (see §3).

---

## 3. Expand canonical format to accept code (language-agnostic)

**Recommendation: extend the canonical format with an optional, language-agnostic code section.**

- **Shape:** Store code as **opaque source + language tag**. No execution or parsing by the constructor; we only store and roundtrip it.
- **Options:**
  - **Per-graph:** e.g. `code_blocks: list[{ "id": str, "language": str, "source": str }]`. Nodes in the process graph can reference `code_id` if they carry scripts (e.g. function node, script node).
  - **Per-unit:** optional `script: { "language": str, "source": str }` on a Unit (for units that embed code). Simpler but mixes structure and code.
  - **Separate section:** e.g. `workflow_scripts: list[{ "id", "language", "source", "node_id?" }]` at the top level of the process graph (or a sibling to it). Keeps units/connections clean; code is referenced by id.

**Language-agnostic:** we do **not** interpret the code. We store `language` (e.g. `"python"`, `"javascript"`) and `source` (raw string). Downstream (Node-RED, PyFlow, Ryven, or a rule engine) can interpret it. So the canonical format stays **language-agnostic**: it only carries topology + code blobs with a language tag.

**Schema change (optional, non-breaking):** add to the process graph (or a companion “workflow” object) an optional field, e.g. `code_blocks: list[CodeBlock] | None = None` with `CodeBlock = { id, language, source }`. Existing configs without `code_blocks` are unchanged. See **schemas/process_graph.py** for a minimal placeholder.

---

## 4. Runtime adapters status (external env for training)

The **roundtrip** is: (1) import full workflow → (2) **train via the external runtime** as env (flow runs in the real editor/runtime) → (3) use trained model in the flow (same runtime). So training and execution both use the **external** runtime, not our own executor.

| Adapter | File | Status | External runtime? | Roundtrip? |
|---------|------|--------|--------------------|------------|
| **Node-RED** | `environments/external/node_red_adapter.py` | **Implemented** | **Yes.** HTTP or WebSocket to Node-RED; flow runs in Node-RED. | Yes. Train and run in Node-RED. |
| **EdgeLinkd** | `environments/external/node_red_rust_edgelinkd_adapter.py` | **Implemented** | **Yes.** Same step-endpoint convention; flow runs in EdgeLinkd. | Yes. |
| **PyFlow** | `environments/external/pyflow_adapter.py` | **Implemented (in-process)** | **No.** We load PyFlow JSON and run the graph with **our own executor** (topological eval + code_blocks + RLAgent). Supports **RLOracle** units (step_driver + collector) for same logic as Node-RED/n8n but in-process. We do **not** use the PyFlow library or editor runtime. | **Partial.** Same graph (your workflow), but execution is ours. True roundtrip would use PyFlow’s EvaluationEngine. |
| **Ryven** | `environments/external/ryven_adapter.py` | **Implemented (WebSocket + HTTP)** | **Yes.** Flow (or bridge) runs in Ryven; we talk step/reset over WS/HTTP. | Yes. |
| **IDAES** | `environments/external/idaes_adapter.py` | **Implemented (in-process)** | **Yes.** IDAES/Pyomo model runs in-process; we set action vars, solve, read obs. | Yes (same model/runtime). |
| **n8n** | — | **Import + deploy** | Training: use Node-RED (or webhook) to expose step API. Deploy: `inject_agent_into_n8n_flow`. | Import + deploy; training via Node-RED or custom endpoint. |

**Import side:** Normalizer supports full Node-RED, PyFlow, **Ryven**, and **IDAES** import. For IDAES: use format `idaes` with a template-like dict (`units`/`blocks` + `connections`/`links`, default `environment_type` `"chemical"`), or build the canonical dict from a live model via `flowsheet_to_canonical_dict(model)` in the IDAES adapter. **Runtime side:** Node-RED (HTTP/WebSocket), PyFlow (in-process), Ryven (HTTP/WebSocket), and IDAES (in-process) adapters are implemented.

### 4.1 IDAES roundtrip and configuration

**Roundtrip:** (1) **Import** flowsheet topology as canonical `ProcessGraph` (template-like JSON or introspect from a live Pyomo model); (2) **Train** using the IDAES adapter as Gymnasium env (step = set action vars → solve → read observation vars → reward); (3) **Use** the trained model for control/optimization (e.g. setpoints, MPC).

**Import options:**

- **Template-like JSON:** Use normalizer with `format="idaes"`. Input is a dict with:
  - `units` or `blocks`: list of `{ "id", "type", "controllable?", "params?" }`
  - `connections` or `links`: list of `{ "from", "to" }`
  - Optional `environment_type` (default `"chemical"`)
  - Optional `observation_vars` / `action_vars` are for **training config** (adapter), not stored on `ProcessGraph`.
- **From live model:** After building an IDAES/Pyomo flowsheet in Python, call `flowsheet_to_canonical_dict(model)` from `environments.external.idaes_adapter` to get a dict suitable for `to_process_graph(..., format="dict")` or for display (e.g. GUI). Requires Pyomo and a flowsheet block (e.g. `model.fs`) with unit blocks and Arcs.

**Adapter config (for training):** Passed to `load_idaes_env(config)` or as `adapter_config` when using the IDAES environment type.

| Key | Required | Description |
|-----|----------|-------------|
| `model_path` | One of path/module | Path to a Python file that builds the model (must expose `model`, `m`, or `create_flowsheet()` / `get_model()`). |
| `model_module` | One of path/module | Dotted module path, e.g. `"my_package.flowsheet:get_model"`. |
| `model_attr` | No | Attribute or callable name (default `"model"`). |
| `state_path` | No | Path to JSON from `idaes.core.util.model_serializer.to_json`; state is loaded after build (optional). |
| `observation_vars` | Yes | List of variable paths (e.g. `["fs.mixer.outlet.temperature[0]"]`) for the observation vector. |
| `action_vars` | Yes | List of variable paths to set each step (control inputs). |
| `obs_shape` | No | Observation shape; inferred from `observation_vars` length if omitted. |
| `action_shape` | No | Action shape; inferred from `action_vars` length if omitted. |
| `reward_config` | No | Dict, e.g. `{"type": "setpoint", "observation_index": 0, "target": 100}` or `{"target_temp": 100}`. |
| `solver` | No | Solver name (default `"ipopt"`). |
| `solver_options` | No | Dict of solver options. |

**Example (minimal):**

```python
from normalizer import to_process_graph
from environments.external.idaes_adapter import load_idaes_env, flowsheet_to_canonical_dict

# Import topology from template-like dict
raw = {
    "environment_type": "chemical",
    "units": [{"id": "mixer", "type": "Mixer", "controllable": False}, {"id": "heater", "type": "Heater", "controllable": True}],
    "connections": [{"from": "mixer", "to": "heater"}],
}
pg = to_process_graph(raw, format="idaes")

# Or from a live model (after building it)
# canonical_dict = flowsheet_to_canonical_dict(model)
# pg = to_process_graph(canonical_dict, format="dict")

# Create env for training
env_config = {
    "model_path": "path/to/my_flowsheet.py",
    "observation_vars": ["fs.heater.outlet.temperature[0]"],
    "action_vars": ["fs.heater.heat_duty[0]"],
    "reward_config": {"type": "setpoint", "target_temp": 400},
}
env = load_idaes_env(env_config)
obs, info = env.reset()
action = env.action_space.sample()
obs, reward, terminated, truncated, info = env.step(action)
```

**Dependencies:** IDAES adapter requires Pyomo (`pip install pyomo`). Optional: `idaes-pse` and a solver (e.g. `ipopt`) for full IDAES models; `idaes.core.util.model_serializer` for `state_path` load/save. If Pyomo is missing, importing the adapter raises `ImportError` with install instructions.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| **Use PyFlow or Ryven for native runtime?** | Yes, consider both as Python-native alternatives to Node-RED; same roundtrip (import → train via adapter → model as node). Add pyflow_adapter / ryven_adapter when needed. |
| **Import full workflows from both including functions?** | Yes; implemented for Node-RED and PyFlow (all nodes, connections, code_blocks). |
| **Expand canonical format to accept code?** | Yes; `code_blocks` in ProcessGraph. We store and roundtrip; we don’t execute or parse. |
| **Are runtime adapters ready?** | Yes. Node-RED (HTTP/WebSocket), PyFlow (in-process), Ryven (HTTP/WebSocket, default port 1899), and IDAES (in-process) are implemented. n8n: import + deploy supported; training reuses Node-RED step-endpoint convention if the workflow exposes it. Deploy: `inject_agent_into_flow` (Node-RED/EdgeLinkd), `inject_agent_into_pyflow_flow` (PyFlow), `inject_agent_into_n8n_flow` (n8n). IDAES: use trained model in control/optimization (no flow-inject node yet). |

This gives a single canonical representation for **workflow constructor + rewards rules** that can be fed by Node-RED, PyFlow, Ryven, or IDAES (template-like or introspected) and that can carry code for functions/scripts in a language-agnostic way. IDAES roundtrip: import topology → train via `load_idaes_env` → use trained model in control/optimization; see §4.1 for config and examples.
