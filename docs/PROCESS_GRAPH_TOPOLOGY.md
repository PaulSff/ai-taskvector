# Process graph topology (canonical schema)

This document describes the **canonical process graph**: the single schema used for process structure (units, connections), optional code blocks for roundtrip, and optional layout for visual positions. See **schemas/process_graph.py** for the implementation.

---

## 1. Overview

The process graph is the source of truth for:

- **Topology:** which units exist and how they are connected
- **Environment type:** thermodynamic, chemical, or generic_control (drives which env factory and rewards apply)
- **Code (optional):** language-agnostic code blocks for function/script nodes (Node-RED, PyFlow roundtrip)
- **Layout (optional):** visual positions (x, y) per unit for the editor canvas

All external formats (Node-RED, PyFlow, Ryven, n8n, YAML, dict) are normalized into this schema via **normalizer.to_process_graph()**.

---

## 2. Environment types

| Value | Description |
|-------|-------------|
| `thermodynamic` | Temperature/mixing process (e.g. hot/cold sources, tank, valves, sensor). Mapped to `TemperatureControlEnv` by env factory. |
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

---

## 4. Unit types

### 4.1 Process-unit types (thermodynamic)

Used by the constructor and env factory for temperature-control flows.

| Type | Description | Typical params | Controllable |
|------|-------------|----------------|--------------|
| **Source** | Inflow (e.g. hot/cold water). | `temp`, `max_flow` | No |
| **Valve** | Flow control (hot, cold, dump). | `position_range`, `setpoint`, `max_flow` | Yes (when used as actuator) |
| **Tank** | Mixing tank / reservoir. | `capacity`, `cooling_rate` | No |
| **Sensor** | Measurement (temperature, level, etc.). | `measure` (e.g. temperature, pressure) | No |

For thermodynamic envs the factory expects: at least 2 Source, 1 Tank, 3 controllable Valves; optional Sensor; and exactly one RLAgent with observations in and actions out.

### 4.2 Agent node types

Units that represent the trained RL agent (roundtrip: Node-RED, PyFlow). The **unit id** (or `params.agent_id`) is the agent name and maps to the model folder `models/<agent_name>/`.

| Type | Notes |
|------|-------|
| **RLAgent** | Default agent node type. |
| **ProcessController** | Alias. |
| **rl_agent** | Alternative (lowercase). |
| **process_controller** | Alternative. |

Defined in **schemas/agent_node.py** as `RL_AGENT_NODE_TYPES`. The agent node must have at least one connection **in** (observations) and one **out** (actions).

### 4.3 Other types (imported workflows)

When importing from Node-RED, PyFlow, Ryven, or n8n, any node type is allowed (e.g. `function`, `inject`, `debug`, `exec`, or package-specific names). They are stored as units with the same `id`/`type`/`params`; code is extracted into **code_blocks** (see §6). The constructor does not execute or interpret these; they are preserved for roundtrip and for adapters (e.g. node_red_adapter, pyflow_adapter).

---

## 5. Connection

A directed edge between two units (flow or measurement).

| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Source unit id (alias `from_id` in code). |
| `to` | string | Target unit id (alias `to_id` in code). |

Connections define the graph topology only; they do not carry port indices (multiple wires between the same pair are represented as multiple connections if needed by the normalizer).

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
| `environment_type` | string (enum) | `thermodynamic` | One of thermodynamic, chemical, generic_control. |
| `units` | list[Unit] | [] | All units in the graph. |
| `connections` | list[Connection] | [] | All directed edges (from, to). |
| `code_blocks` | list[CodeBlock] | [] | Optional code for function/script nodes. |
| `layout` | dict[str, NodePosition] \| null | null | Optional per-unit positions (unit_id -> {x, y}). |

Existing configs without `layout` or `code_blocks` remain valid (defaults apply).

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
    { "from": "hot_source", "to": "hot_valve" },
    { "from": "cold_source", "to": "cold_valve" },
    { "from": "hot_valve", "to": "tank" },
    { "from": "cold_valve", "to": "tank" },
    { "from": "tank", "to": "dump_valve" },
    { "from": "tank", "to": "sensor" },
    { "from": "sensor", "to": "rl_agent_1" },
    { "from": "rl_agent_1", "to": "hot_valve" },
    { "from": "rl_agent_1", "to": "cold_valve" },
    { "from": "rl_agent_1", "to": "dump_valve" }
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

- **schemas/process_graph.py** — Canonical schema (Unit, Connection, CodeBlock, NodePosition, ProcessGraph).
- **schemas/agent_node.py** — RL Agent node convention and helpers.
- **docs/WORKFLOW_EDITORS_AND_CODE.md** — Code blocks, import formats, runtime adapters.
- **docs/WORKFLOW_STORAGE_AND_ROUNDTRIP.md** — Storage format, layout, roundtrip.
- **docs/DEPLOYMENT_NODERED.md** — Node-RED roundtrip and agent deployment.
- **normalizer/normalizer.py** — `to_process_graph(raw, format="node_red"|"pyflow"|"dict"|...)`.
- **env_factory/factory.py** — Build env from ProcessGraph (thermodynamic).
