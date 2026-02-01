# Node-RED flow format for Process RL Constructor

The constructor accepts **process graphs** in a Node-RED–style JSON format. You can design flows in Node-RED (with custom process-unit nodes) and export them, or build/edit the JSON directly and load it in the GUI.

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
