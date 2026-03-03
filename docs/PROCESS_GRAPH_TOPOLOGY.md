# Process graph topology (canonical schema)

This document describes the **canonical process graph**: the single schema used for process structure (units, connections), optional code blocks for roundtrip, and optional layout for visual positions. See **schemas/process_graph.py** for the implementation.

---

## 1. Overview

The process graph is the source of truth for:

- **Topology:** which units exist and how they are connected
- **Environment type:** thermodynamic, chemical, or generic_control (drives which env factory and rewards apply)
- **Code (optional):** language-agnostic code blocks for function/script nodes (Node-RED, PyFlow roundtrip)
- **Layout (optional):** visual positions (x, y) per unit for the editor canvas

All external formats (Node-RED, PyFlow, Ryven, n8n, ComfyUI, template/IDAES, YAML, dict) are normalized into this schema via **normalizer.to_process_graph(raw, format=...)**. Format-specific conversion lives in **normalizer/** import modules (`node_red_import`, `n8n_import`, `pyflow_import`, etc.); shared canonicalization (unit type aliases, connection list shape) is in **normalizer/shared.py**.

---

## 2. Environment types

| Value | Description |
|-------|-------------|
| `thermodynamic` | Temperature/mixing process (e.g. hot/cold sources, tank, valves, sensor). Mapped to `GraphEnv` by env factory. |
| `chemical` | Chemical process (IDAES-style units/blocks, connections). |
| `generic_control` | Generic control topology; no built-in physics. |

Defined in **schemas/process_graph.py** as `EnvironmentType` enum.

---

## 3. Unit

A **unit** is a single node in the process graph.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (used in connections and code_blocks). |
| `type` | string | Yes | Unit type (see §4). |
| `controllable` | bool | No (default false) | Whether this unit is an action/control input (e.g. valve). |
| `params` | object | No (default {}) | Type-specific parameters (temp, max_flow, capacity, etc.). |
| `name` | string | No | Optional display name (e.g. n8n node name, Node-RED label). Set on import when available. |

---

## 4. Unit types

Unit types and the **controllable** flag (whether the unit is an action/control input) are defined by the **unit spec** in **units/registry.py** (`UnitSpec.controllable`). The normalizer uses `units.registry.is_controllable_type(type_name)` when importing flows; unknown types default to non-controllable. Which unit types exist (e.g. process units, data nodes) depends on the **environment** and is documented per env (e.g. **units/thermodynamic/**, **environments/**). See **units/README.md** for how to register units.

### 4.1 Agent node types

Units that represent the trained RL agent (roundtrip: Node-RED, PyFlow). The **unit id** (or `params.agent_id`) is the agent name and maps to the model folder `models/<agent_name>/`.

**Canonical types (strict):** **RLAgent**, **LLMAgent**. The rest of the system uses only these.  
**Normalizer:** On input, aliases are resolved to these types (e.g. `rl_agent` → **RLAgent**; `llm_agent` → **LLMAgent**). Case and common variants are handled in **normalizer.to_process_graph()**; see **normalizer/shared.py** (`_canonical_unit_type`).

Defined in **schemas/agent_node.py** as `RL_AGENT_NODE_TYPES` and `LLM_AGENT_NODE_TYPES`. The agent node must have at least one connection **in** (observations) and one **out** (actions).

#### 4.1.1 Agent params: model (local, our server, external)

The agent can use different backends. Configure them via the unit **params**:

| Param | When to use | Description |
|-------|--------------|-------------|
| `model_path` | Local model (our system) | Path to the trained model (e.g. `models/temperature-control-agent/best/best_model.zip`). Used when the inference server is started with that path. |
| `inference_url` | All options | URL of the predict endpoint. Default `http://127.0.0.1:8000/predict` for a local inference server. For a deployed instance of our server or an external provider (Ollama, Hugging Face, etc.), set to that endpoint. |

- **Local model (our system):** Set `model_path` and `inference_url` (default above). The workflow calls `inference_url`; whoever runs the server uses `model_path`.
- **Our server (deployed):** Set only `inference_url` to the deployed URL; `model_path` can be empty or a hint.
- **External model:** Set `inference_url` to the provider’s predict endpoint; `model_path` can be empty. The endpoint must accept `POST` with `{ "observation": [...] }` and return `{ "action": [...] }`.

For **LLM providers** (e.g. Ollama, Hugging Face), the “model” is typically a **name** (e.g. `llama3.2`), not a path. Set **`model_name`** in params so the adapter or inference service knows which model to call. Optional: `provider` (e.g. `ollama`) and `host` (e.g. `http://127.0.0.1:11434`) when the runtime calls **LLM_integrations** directly instead of an HTTP predict endpoint.

Optional wiring params (also in **params**): `observation_source_ids`, `action_target_ids` — when present, graph edits can auto-wire the agent; otherwise use explicit **connect** edits.

#### 4.1.2 Agent params: LLM (model name, system prompt)

If the agent is an **LLM** (language model), e.g. Ollama, the **LLM_integrations** (e.g. `LLM_integrations.ollama`) are chat-based (messages → text). They are not directly the RLAgent backend: an adapter must turn observation → prompt → LLM call → parsed action (e.g. a small inference server or in-process code that calls `LLM_integrations.client.chat`). That adapter can use the following params.

| Param | Required | Description |
|-------|----------|-------------|
| `model_name` | Yes (for LLM) | Model name for the provider (e.g. `llama3.2` for Ollama). For SB3/local file use `model_path` instead. |
| `system_prompt` | Yes (for LLM) | System message for the LLM (role, task, output format). |
| `user_prompt_template` | No | Template for the user message, with a placeholder for observations (e.g. `"Observations: {observation_json}. Reply with action JSON."`). |
| `provider` | No | LLM provider id when using **LLM_integrations** in-process (e.g. `ollama`). Optional if inference_url points to an adapter that already knows the provider. |

These apply to both locally served and externally served LLMs. See **deploy/README.md** for runtime behaviour and **assistants/prompts.py** (Workflow Designer) for how the assistant asks the user and sets these params.

#### 4.1.3 LLMAgent unit (LLM adapter in-flow)

The LLM adapter (observation → prompt → LLM → parsed action) is implemented as a single unit type: **LLMAgent**. All three topologies use the same class; the only differences are **wiring** (what is connected in and out) and **prompt** (`system_prompt`, `user_prompt_template`).

| Topology | Role | Data flow |
|----------|------|-----------|
| **Observations → LLMAgent → Actions** | LLMAgent *is* the agent. Same slot as RLAgent: observations in, actions out. | Observation(s) → **LLMAgent** → Action target(s). |
| **RLAgent → LLMAgent → Actions** | LLMAgent is a **post-processor**: RL draft → LLM refinement → final action. | Observation(s) → RLAgent → **LLMAgent** (refiner) → Action target(s). |
| **LLMAgent → RLAgent → Actions** | **Delegation:** LLMAgent uses RLAgent as a tool. LLM sees observations, decides when to delegate; runtime passes observation to RLAgent for action. | Observation(s) → **LLMAgent** → RLAgent (tool) → Action target(s). |

One new unit type **LLMAgent** (in schemas and runtime) with params: `model_name`, `provider`, `system_prompt`, `user_prompt_template`. **RLAgent** has no prompt params (only `model_path`, `inference_url`, and optional wiring params). The runtime builds messages from the prompt and inputs, calls the LLM, and parses the response (e.g. to an action vector). The **prompt** alone distinguishes the three cases: as agent (prompt describes "you are a controller, given observations output actions"); as refiner (prompt describes "refine this draft action"); as delegator (prompt describes "you may use the RL tool when appropriate").

All three patterns keep the adapter logic inside the graph as a first-class unit, so no separate inference server is required when the runtime can call **LLM_integrations** (e.g. Ollama) in-process.

### 4.2 Oracle node type (external runtime training)

For external-runtime training (Node-RED/EdgeLinkd/etc.), workflows typically include a step handler node we call **RLOracle**:

**Canonical type (strict):** **RLOracle**.  
**Normalizer:** On input, aliases are resolved to this type (e.g. `rl_oracle` → **RLOracle**). See **normalizer/shared.py** (`_canonical_unit_type`).

The Oracle implements the `/step` endpoint: reset/action → observation, reward, done. Used by external adapters for training. Its semantics (observation/action vector meaning) are defined in the training config under `environment.adapter_config` (`observation_spec` / `action_spec`). See **docs/DEPLOYMENT_NODERED.md**.

### 4.3 Other types (imported workflows)

When importing from Node-RED, PyFlow, Ryven, or n8n, any node type is allowed (e.g. `function`, `inject`, `debug`, `exec`, or package-specific names). They are stored as units with the same `id`/`type`/`params`; code is extracted into **code_blocks** (see §6). The constructor does not execute or interpret these; they are preserved for roundtrip and for adapters (e.g. node_red_adapter, pyflow_adapter).

### 4.4 Comments (metadata)

Assistants can leave notes on the flow via **comments**: a separate list on the graph, not units. Comments are **metadata** (see §8) and are **not exported** to external runtimes (Node-RED, n8n, PyFlow, ComfyUI); export only writes units, connections, code_blocks, and layout.

Each comment is a **Comment** (see **schemas/process_graph.py**):

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique id (e.g. `comment_` + short hex). |
| `info` | string | Comment text (required when adding). |
| `commenter` | string | Optional identifier of who left the comment (e.g. assistant name). |
| `created_at` | string | ISO 8601 timestamp (e.g. `2025-03-03T12:00:00Z`), set when the comment is added. |
| `x`, `y` | number \| null | Optional canvas position in logical pixels. |

**Graph edit action:** `add_comment` — appends one entry to `ProcessGraph.comments`. Payload: `{"action": "add_comment", "info": "..."}`; optional `"commenter": "..."`. The backend generates `id` and `created_at`. See **assistants/graph_edits.py** (`GraphEditAction`, `apply_graph_edit`).

---

## 5. Connection

A directed edge between two units, with mandatory port indices. Every connection specifies which output port of the source and which input port of the target it wires.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | string | Yes | Source unit id (alias `from_id` in code). |
| `to` | string | Yes | Target unit id (alias `to_id` in code). |
| `from_port` | string | Yes (default `"0"`) | Source output port index. Value is typically `"0"`, `"1"`, etc. |
| `to_port` | string | Yes (default `"0"`) | Target input port index. Value is typically `"0"`, `"1"`, etc. |
| `connection_type` | string | No | Optional connection type from source format (e.g. n8n: `main`, `ai_tool`, `ai_languageModel`). Preserved on import for roundtrip. |

Port indices are derived from the source format on import (Node-RED `wires`, n8n `main`/`index`, PyFlow pins, Ryven `nodeId:port`, ComfyUI `origin_slot`/`target_slot`). When omitted in dict/YAML, they default to `"0"`. Port names and types (e.g. ComfyUI) can be stored as the port value when the format provides them.

---

## 5.1 Input/output ports per unit type

Port options are defined by the **UnitSpec** for each unit type (see **units/README.md**). The graph executor resolves connections using `from_port`/`to_port` and the unit's input/output port specs. For imported workflows (Node-RED, n8n, PyFlow, Ryven), ports are derived from the source format and stored on connections.

| Unit (thermodynamic) | Input ports | Output ports |
|----------------------|-------------|--------------|
| Source | — | temp, max_flow |
| Valve | setpoint | flow |
| Tank | hot_flow, cold_flow, dump_flow, hot_temp, cold_temp | temp, volume, volume_ratio |
| Sensor | value | measurement, raw |

See **units/thermodynamic/** for implementations and **units/README.md** for the full reference.

---

## 6. Code blocks (optional)

Language-agnostic code attached to the graph for **roundtrip** (Node-RED function nodes, PyFlow script nodes, etc.). The constructor does **not** execute or parse this code; it is stored and can be re-exported. See **docs/WORKFLOW_EDITORS_AND_CODE.md**.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique id; typically matches the unit id that “owns” this code (e.g. function node). |
| `language` | string | Language tag: `javascript`, `python`, `shell`, etc. |
| `source` | string | Raw source code (opaque). |

---

## 7. Layout (optional)

Per-unit visual positions for the editor canvas (same idea as Node-RED’s `x`, `y` on each node). When present, the GUI uses these positions; when absent, it uses auto layout (e.g. layered). See **docs/WORKFLOW_STORAGE_AND_ROUNDTRIP.md**.

| Key | Value | Description |
|-----|--------|-------------|
| (unit_id) | `{ "x": number, "y": number }` | Top-left position of the unit in logical pixels. |

- **Schema:** `ProcessGraph.layout: dict[str, NodePosition] | None`, with `NodePosition = { x: float, y: float }`.
- **Import:** When importing from Node-RED or PyFlow, the normalizer can populate `layout` from each node’s `x`/`y`.
- **Save:** When the user drags nodes, the canvas can update `layout` and persist it with the graph.

---

## 8. ProcessGraph (top-level)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `environment_type` | string (enum) | `thermodynamic` | One of thermodynamic, chemical, generic_control, data_bi. |
| `units` | list[Unit] | [] | All units in the graph (when no tabs, or primary/first tab when tabs present). |
| `connections` | list[Connection] | [] | All directed edges (from, to). When `tabs` is set, mirrors the first tab. |
| `code_blocks` | list[CodeBlock] | [] | Optional code for function/script nodes. |
| `layout` | dict[str, NodePosition] | null | Optional per-unit positions (unit_id -> {x, y}). |
| `origin` | GraphOrigin | null | Optional metadata for imported workflows (e.g. Node-RED tab labels). |
| `origin_format` | string | null | Import format: node_red, pyflow, n8n, ryven, dict. Used for export (export only to same format). |
| `tabs` | list[TabFlow] | null | Multi-tab flows (e.g. Node-RED). One tab per flow; each tab has id, label, disabled, units, connections. When non-empty, top-level `units`/`connections` mirror the first tab. |
| `comments` | list[Comment] | null | Optional assistant comments on the flow (see §4.4). Not exported to external runtimes. |

Existing configs without `layout`, `code_blocks`, `origin`, `tabs`, or `comments` remain valid (defaults apply).

### 8.1 Multi-tab flows (tabs)

When the graph was imported from a multi-tab editor (e.g. Node-RED with several flow tabs), **tabs** is a list of **TabFlow** entries. Each tab has:

- **id** — Tab/flow id (e.g. Node-RED tab node id).
- **label** — Optional display name.
- **disabled** — Optional; whether the tab is disabled.
- **units** — Units in this tab only.
- **connections** — Connections in this tab only (between that tab’s units).

Top-level **units** and **connections** always mirror the first tab so that single-tab consumers (editors, env factory) see the primary flow without change. **layout** and **code_blocks** are global (keyed by unit id across all tabs). Export (e.g. Node-RED) uses **tabs** when present to emit one tab node per tab and assign each node to the correct tab via `z`.

---

## 9. Example (minimal JSON)

```json
{
  "environment_type": "thermodynamic",
  "units": [
    { "id": "hot_source", "type": "Source", "controllable": false, "params": { "temp": 60, "max_flow": 1.0 } },
    { "id": "cold_source", "type": "Source", "controllable": false, "params": { "temp": 10, "max_flow": 1.0 } },
    { "id": "hot_valve", "type": "Valve", "controllable": true, "params": {} },
    { "id": "cold_valve", "type": "Valve", "controllable": true, "params": {} },
    { "id": "dump_valve", "type": "Valve", "controllable": true, "params": {} },
    { "id": "tank", "type": "Tank", "controllable": false, "params": { "capacity": 1.0, "cooling_rate": 0.01 } },
    { "id": "sensor", "type": "Sensor", "controllable": false, "params": { "measure": "temperature" } },
    { "id": "rl_agent_1", "type": "RLAgent", "controllable": false, "params": {} }
  ],
  "connections": [
    { "from": "hot_source", "to": "hot_valve", "from_port": "0", "to_port": "0" },
    { "from": "cold_source", "to": "cold_valve", "from_port": "0", "to_port": "0" },
    { "from": "hot_valve", "to": "tank", "from_port": "0", "to_port": "0" },
    { "from": "cold_valve", "to": "tank", "from_port": "0", "to_port": "0" },
    { "from": "tank", "to": "dump_valve", "from_port": "0", "to_port": "0" },
    { "from": "tank", "to": "sensor", "from_port": "0", "to_port": "0" },
    { "from": "sensor", "to": "rl_agent_1", "from_port": "0", "to_port": "0" },
    { "from": "rl_agent_1", "to": "hot_valve", "from_port": "0", "to_port": "0" },
    { "from": "rl_agent_1", "to": "cold_valve", "from_port": "0", "to_port": "0" },
    { "from": "rl_agent_1", "to": "dump_valve", "from_port": "0", "to_port": "0" }
  ],
  "layout": {
    "hot_source": { "x": 80, "y": 60 },
    "cold_source": { "x": 80, "y": 160 },
    "hot_valve": { "x": 340, "y": 40 },
    "cold_valve": { "x": 340, "y": 140 },
    "dump_valve": { "x": 340, "y": 240 },
    "tank": { "x": 600, "y": 140 },
    "sensor": { "x": 860, "y": 100 },
    "rl_agent_1": { "x": 860, "y": 180 }
  }
}
```

---

## 10. Related docs

- **schemas/process_graph.py** — Canonical schema (Unit, Connection, CodeBlock, Comment, NodePosition, TabFlow, GraphOrigin, ProcessGraph). **Comment** and **ProcessGraph.comments** for assistant notes (§4.4).
- **assistants/graph_edits.py** — Graph edit schema and **apply_graph_edit** (including **add_comment**); edits produce a graph dict that **normalizer.to_process_graph** consumes.
- **schemas/agent_node.py** — RL Agent node convention and helpers.
- **docs/WORKFLOW_EDITORS_AND_CODE.md** — Code blocks, import formats, runtime adapters.
- **docs/WORKFLOW_STORAGE_AND_ROUNDTRIP.md** — Storage format, layout, roundtrip.
- **docs/DEPLOYMENT_NODERED.md** — Node-RED roundtrip and agent deployment.
- **normalizer/** — Normalization pipeline: **normalizer.py** (`to_process_graph(raw, format=...)`), **shared.py** (canonical unit type and connection list helpers), **node_red_import.py**, **n8n_import.py**, **pyflow_import.py**, **template_import.py**, **ryven_import.py**, **idaes_import.py**, **comfyui_import.py** (each exposes `to_canonical_dict`).
- **env_factory/factory.py** — Build env from ProcessGraph (thermodynamic).
