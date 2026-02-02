# Node-RED flow format for Process RL Constructor

The constructor accepts **process graphs** in a Node-RED–style JSON format. The intended Node-RED story is **roundtrip**: import full workflow → train the full process via the Node-RED adapter → use the trained model in the flow as a custom node. See **docs/DEPLOYMENT_NODERED.md**.

## Node-RED roundtrip

1. **Import full workflow** — Export the full Node-RED flow (process-unit nodes + functions, MQTT, etc.) and import it here. We **extract** process topology (Source, Valve, Tank, Sensor and their wires) for env/training; for full roundtrip we would **preserve** the full flow so we can re-export it with the model node added (not yet implemented).
2. **Train the full process via node_red_adapter** — Training uses Node-RED runtime as the external env (sensors in, actions out). The adapter wraps it as a Gymnasium env; we train (e.g. PPO). Stub: **environments/external/node_red_adapter.py**.
3. **Use the trained model in the flow** — After training, we add an **RL Agent** custom node to the flow that loads our trained model. The flow runs with the trained policy wired between sensors and actuators.

Today we only **extract topology** on import (other nodes are ignored). Full roundtrip (preserve flow, train via node_red_adapter, inject model node) is the target; adapter and flow preservation are stubs or in progress.

## Supported format

The normalizer accepts one of:

1. **Array of nodes** — a JSON array where each element is a process unit node.
2. **Object with `nodes`** — e.g. `{ "nodes": [ ... ] }`.
3. **Object with `flows`** — e.g. `{ "flows": [ { "nodes": [ ... ] } ] }` (first tab used).

Each **node** must have:

| Field         | Type   | Required | Description |
|---------------|--------|----------|-------------|
| `id` or `name`| string | Yes      | Unique unit id (e.g. `hot_source`, `mixer_tank`). |
| `type`        | string | Yes      | One of: `Source`, `Valve`, `Tank`, `Sensor`. (Also accepted: `unitType`, `processType`.) |
| `wires`       | array  | Yes*     | List of output connections. Each element is an array of target node ids: `[["target_id1", "target_id2"]]`. |
| `params`      | object | No       | Unit parameters (e.g. `temp`, `max_flow`, `capacity`, `cooling_rate`, `measure`). Default `{}`. |
| `controllable`| bool   | No       | For valves: whether the valve is controllable. Default `true` for Valve, else `false`. |

\* For nodes with no outgoing connections use `"wires": []`.

## Unit types

- **Source** — e.g. hot/cold water source. Typical params: `temp`, `max_flow`.
- **Valve** — controllable valve. Params optional (e.g. `position_range`, `max_flow`). Set `controllable: true` for RL action.
- **Tank** — mixing tank. Typical params: `capacity`, `cooling_rate`.
- **Sensor** — measures a quantity. Typical params: `measure` (e.g. `"temperature"`).

## Connections

Connections are derived from **wires**: for each node, `wires[i]` is the list of target node ids for output port `i`. Only connections between **recognized unit ids** (nodes with type in Source, Valve, Tank, Sensor) are kept.

Example: `"wires": [["hot_valve"]]` from node `hot_source` creates a connection `hot_source → hot_valve`.

## Mixed flows (standard Node-RED + process units)

Node-RED flows often include **standard nodes** (e.g. `function`, `inject`, `exec`, `mqtt in`, `http request`, `debug`, `change`, `switch`). Our system **only interprets process-unit nodes** (Source, Valve, Tank, Sensor). All other nodes are **ignored** for the purpose of building the canonical process graph:

- **Units:** Only nodes whose `type` (or `unitType` / `processType`) is one of Source, Valve, Tank, Sensor are added to the process graph.
- **Connections:** Only wires **between** two process-unit nodes are kept. Any wire to or from a non–process-unit node (e.g. a function node, inject, debug) is dropped.

So if someone pastes a full Node-RED flow that includes JS functions, commands, MQTT, HTTP, etc., the normalizer extracts just the process topology (sources, valves, tank, sensor) and their connections. The rest of the flow is not used by the constructor. No error is raised; the result may be a valid partial graph or, if there are no process-unit nodes, an empty graph.

## Example flow (temperature mixing)

See **example_flow.json** in this folder. It defines:

- 2 sources (hot, cold) → 2 valves → 1 tank; tank → dump valve and thermometer.
- 7 units, 6 connections.

Import this file in the Constructor GUI (Process graph → Upload Node-RED JSON) or use it as a template for Node-RED custom nodes.

## Using Node-RED

1. **Run Node-RED** (e.g. `npx node-red` or Docker).
2. **Custom nodes** (optional): create nodes that output this JSON shape (id, type, wires, params, controllable) so the flow export matches the format above.
3. **Export**: export your flow as JSON. If the structure is `flows[0].nodes`, the normalizer accepts it. If you use a different layout, ensure the root has a `nodes` array or use the array-of-nodes format.
4. **Import in GUI**: In the Constructor GUI, use “Upload Node-RED JSON” or “Paste JSON” and load/paste the exported flow.

## Using the GUI without Node-RED

You can skip Node-RED and:

- Load the **canonical YAML** process graph (e.g. `config/examples/temperature_process.yaml`), or
- Paste or upload the **Node-RED-style JSON** (e.g. contents of `example_flow.json`) directly in the GUI.

The GUI normalizes both to the same canonical process graph for training and testing.
