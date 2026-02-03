# Workflow editors (PyFlow, Ryven) and code in the canonical format

This doc covers: **PyFlow** and **Ryven** as Python-native alternatives to Node-RED for our runtime; importing **full workflows** from both PyFlow and Node-RED **including functions/code**; and expanding our **canonical JSON format** to accept **code** in a language-agnostic way.

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

The **roundtrip** is: (1) import full workflow → (2) train via external runtime as env → (3) use trained model in the flow.

| Adapter | File | Status | Ready for roundtrip? |
|---------|------|--------|----------------------|
| **Node-RED** | `environments/external/node_red_adapter.py` | **Implemented** | Yes. **HTTP or WebSocket**: flow exposes step endpoint; send `{ "action": [...] }` or `{ "reset": true }`, receive `{ "observation", "reward", "done" }`. Config: `transport` (http/websocket), `step_url` / `ws_url`, optional `obs_shape`/`action_shape`, `timeout`. |
| **EdgeLinkd** | `environments/external/node_red_rust_edgelinkd_adapter.py` | **Implemented** | Yes. Reuses Node-RED step-endpoint logic; default `step_url` http://127.0.0.1:1888/step. Same flow convention as Node-RED. |
| **PyFlow** | `environments/external/pyflow_adapter.py` | **Implemented (in-process)** | Yes. **In-process execution**: load PyFlow JSON, run graph in Python (topological eval + code_blocks). Config: `flow_path`, `observation_sources`, `action_targets`, optional `goal` (e.g. target_temp), `reward_node`, `obs_shape`/`action_shape`. |
| **Ryven** | `environments/external/ryven_adapter.py` | **Implemented (WebSocket + HTTP)** | Yes. Same step-endpoint convention as Node-RED; default port 1899. Flow (or bridge) must expose step/reset endpoint. |

**Import side:** Normalizer supports full Node-RED, PyFlow, and **Ryven** import (all nodes, connections, `code_blocks`). Ryven project: `scripts[].flow` with `nodes` and `connections`/`links`/`edges`. **Runtime side:** Node-RED (HTTP/WebSocket), PyFlow (in-process), and Ryven (HTTP/WebSocket) adapters are implemented.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| **Use PyFlow or Ryven for native runtime?** | Yes, consider both as Python-native alternatives to Node-RED; same roundtrip (import → train via adapter → model as node). Add pyflow_adapter / ryven_adapter when needed. |
| **Import full workflows from both including functions?** | Yes; implemented for Node-RED and PyFlow (all nodes, connections, code_blocks). |
| **Expand canonical format to accept code?** | Yes; `code_blocks` in ProcessGraph. We store and roundtrip; we don’t execute or parse. |
| **Are runtime adapters ready?** | Yes. Node-RED (HTTP/WebSocket), PyFlow (in-process), and Ryven (HTTP/WebSocket, default port 1899) are implemented. Deploy: `inject_agent_into_flow` (Node-RED/EdgeLinkd) and `inject_agent_into_pyflow_flow` (PyFlow). |

This gives a single canonical representation for **workflow constructor + rewards rules** that can be fed by Node-RED, PyFlow, or Ryven and that can carry code for functions/scripts in a language-agnostic way.
