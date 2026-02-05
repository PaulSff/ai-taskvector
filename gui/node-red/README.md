# Node-RED flow format for Process RL Constructor

The constructor accepts **process graphs** in a Node-RED–style JSON format. The intended Node-RED story is **roundtrip**: import full workflow → train the full process via the Node-RED adapter → use the trained model in the flow as a custom node. See **docs/DEPLOYMENT_NODERED.md**.

## Node-RED roundtrip

1. **Import full workflow** — Export the full Node-RED flow and import it here. We **import everything**: all nodes (process units + function, inject, MQTT, debug, etc.) as units, all wires as connections, and code from function/exec/template nodes into **code_blocks** (canonical format). Process topology is available for env/training; full graph + code is preserved for roundtrip.
2. **Train the full process via node_red_adapter** — Training uses Node-RED runtime as the external env (sensors in, actions out). The adapter wraps it as a Gymnasium env; we train (e.g. PPO). Stub: **environments/external/node_red_adapter.py**.
3. **Use the trained model in the flow** — After training, we add an **RL Agent** custom node to the flow that loads our trained model. The flow runs with the trained policy wired between sensors and actuators.

**Import behaviour:** All nodes are included (type = node.type or unitType/processType). All wires become connections. Nodes with `func`, `code`, `template`, or `command` contribute to **code_blocks** (language: javascript or shell for exec). The adapter and flow preservation for re-export are stubs or in progress.

## Supported format

The normalizer accepts one of:

1. **Array of nodes** — a JSON array where each element is a process unit node.
2. **Object with `nodes`** — e.g. `{ "nodes": [ ... ] }`.
3. **Object with `flows`** — e.g. `{ "flows": [ { "nodes": [ ... ] } ] }` (first tab used).

Each **node** should have:

| Field         | Type   | Required | Description |
|---------------|--------|----------|-------------|
| `id` or `name`| string | Yes      | Unique node id (e.g. `hot_source`, `mixer_tank`, or Node-RED’s internal id). |
| `type`        | string | No*      | Any node type: process units `Source`, `Valve`, `Tank`, `Sensor` (or `unitType`/`processType`), or standard types (`function`, `inject`, `debug`, `mqtt in`, etc.). Default `"node"` if missing. |
| `wires`       | array  | No       | List of output connections. Each element is an array of target node ids: `[["target_id1", "target_id2"]]`. Empty `[]` if no outputs. |
| `params`      | object | No       | Node parameters (process-unit params or node-specific). Default `{}`. |
| `controllable`| bool   | No       | For process valves: whether the valve is an RL action. Default `true` for Valve, else `false`. |
| `func` / `code` / `template` / `command` | string | No | For function/exec/template nodes: stored in **code_blocks** (language: javascript or shell). |

\* Process-unit nodes need a recognizable type for env/training; other nodes can have any type or omit it.

## Unit types

- **Source** — e.g. hot/cold water source. Typical params: `temp`, `max_flow`.
- **Valve** — controllable valve. Params optional (e.g. `position_range`, `max_flow`). Set `controllable: true` for RL action.
- **Tank** — mixing tank. Typical params: `capacity`, `cooling_rate`.
- **Sensor** — measures a quantity. Typical params: `measure` (e.g. `"temperature"`).

## Node-RED custom nodes (use as-is)

You can build flows using **existing Node-RED contrib/custom nodes** for thermometers, tanks, valves, and sensors. Install via Node-RED’s “Manage palette” or `npm install` in `~/.node-red`. Our normalizer accepts any node type; use these where they fit your process.

### Official extra nodes ([node-red/node-red-nodes](https://github.com/node-red/node-red-nodes))

The Node-RED project’s **extra nodes** repo provides installable npm packages (e.g. `npm install node-red-node-<name>` in `~/.node-red`). Relevant ones for temperature/process control and simulation:

| Package | Category | Notes |
|---------|----------|--------|
| **node-red-node-heatmiser** | Hardware | Read/write temperature and frost protection on Heatmiser thermostats. |
| **node-red-node-sensortag** | Hardware | Read data from TI BLE SensorTag (temp, humidity, etc.). |
| **node-red-node-pidcontrol** | Function | PID control loop for numeric inputs (setpoint, feedback). |
| **node-red-node-random** | Function | Random number generator (integers or floats in a range) — useful for simulated sensor noise. |
| **node-red-node-datagenerater** | Function | Generate dummy data (names, numbers, etc.) for testing/simulation. |
| **node-red-node-timeswitch** | Time | Repeating timers (e.g. simple heating/schedule control). |
| **node-red-node-smooth** | Function | Smoothing/filtering (max, min, mean, high/low pass) across previous values. |
| **node-red-node-rbe** | Function | Report by exception, deadband/bandgap for numeric inputs. |

### Community contrib nodes

| Role | Package | Notes |
|------|---------|--------|
| **Temperature sensors** | `node-red-contrib-gpio-dht-sensor` | DHT11/DHT22/AM2302 (temp + humidity) on GPIO. |
| | `node-red-contrib-thsense` | DHT on Raspberry Pi, runs as normal user. |
| | `node-red-contrib-sensor-ds18b20` | DS18B20 1-Wire; selectable sensor, interval, on-demand. |
| | `node-red-contrib-sensor-dynamic-ds18b20` | DS18B20 with dynamic sensor ID from UI. |
| | `node-red-contrib-ds18b20-sensor` | Scans 1-Wire bus, returns per-sensor or array. |
| **Tank / volume** | `node-red-contrib-tank-volume` | Converts liquid height → volume for various tank shapes (e.g. rainwater). |
| **Valves / control** | `node-red-contrib-vib-smart-valve` | Smart valve/TRV: grouping, calibration, manual override, Home Assistant. |
| | `node-red-contrib-smithtek-operator` | Level-based control, thresholds, tank fill/empty, up to 24 outputs. |
| **Other sensors** | `node-red-contrib-tinkerforge` | Tinkerforge sensors (distance, temp, etc.). |

**Simulated sensors (no hardware):** The [Node-RED Flow Library](https://flows.nodered.org/) has flows such as “Simulated temperature sensor” and “Smart Home Monitoring System (Simulated Sensors)” that use inject + function nodes to mock temperature (e.g. random walk, bounds). You can copy those patterns or use them as subflows.

When you use these nodes, ensure your flow still exposes the **step endpoint** (POST `/step` with `{ "reset": true }` or `{ "action": [...] }` → `{ "observation", "reward", "done" }`) if you want to train via **node_red_adapter**; you may need a thin function node to map node outputs into the observation array and to apply actions to valve nodes.

## Connections

Connections are derived from **wires**: for each node, `wires[i]` is the list of target node ids for output port `i`. **All** wires are kept (full graph), so connections can link process units, function nodes, inject, debug, etc.

Example: `"wires": [["hot_valve"]]` from node `hot_source` creates a connection `hot_source → hot_valve`.

## Mixed flows (standard Node-RED + process units)

Node-RED flows often include **standard nodes** (e.g. `function`, `inject`, `exec`, `mqtt in`, `http request`, `debug`, `change`, `switch`). Our normalizer **includes all of them**:

- **Units:** Every node is added with `type` = node’s `type` (or `unitType` / `processType` for process units). So you get both process units (Source, Valve, Tank, Sensor) and standard types (function, inject, debug, etc.).
- **Connections:** Every wire is kept, so the full topology (including links to/from function nodes, inject, debug, etc.) is preserved.
- **Code:** Nodes that contain code are stored in **code_blocks**: `func` / `code` / `template` → JavaScript (or shell for `exec` nodes’ `command`). This allows roundtrip and use by node_red_adapter.

The env factory and training still use only **process-unit** nodes (Source, Valve, Tank, Sensor) when building the Gymnasium env; the full graph and code_blocks are available for the Node-RED adapter and future re-export.

## Example flows (temperature mixing)

- **example_flow.json** — Minimal topology: 2 sources (hot, cold) → 2 valves → 1 tank; tank → dump valve and thermometer. 7 units, 6 connections. Use as a template for Node-RED custom nodes or import in the Constructor GUI.

- **config/examples/temperature_process_node_red_no_agent.json** — **Executable** Node-RED flow (no RLAgent), aligned with `temperature_process.yaml`. Uses **ready-to-use nodes** plus **micro functions**:
  - **Drift:** 2× **Function** nodes (“Drift hot”, “Drift cold”) output a random value in [-0.2, 0.2] using `Math.random()` — no extra packages required.
  - **Micro functions:** **Step driver** (reset/action dispatch), **Hot source** / **Cold source** (temp + drift), **Thermometer hot/cold/tank** (pass-through), **Hot/Cold/Dump valve** (flow from action), **Mixer tank** (energy balance, cooling, reward), **Water level** (volume ratio), **Collector** (observation + HTTP response).
  - Exposes **POST /step**: `{ "reset": true }` or `{ "action": [cold, dump, hot] }` → `{ "observation": [4], "reward", "done" }`. Use with **node_red_adapter** (step_url e.g. `http://127.0.0.1:1880/step`).

- **config/examples/temperature_process_node_red_wired.json** — Same assembled flow **with** the agent wired to sensors and valves (matches `temperature_process.yaml` topology):
  - **Inputs (observations):** thermometer_hot, thermometer_cold, thermometer_tank, water_level → **ai_tank_operator**.
  - **Outputs (actions):** **ai_tank_operator** → hot_valve, cold_valve, dump_valve.
  - The agent node is a **function** (id `ai_tank_operator`) that runs once per step: reads observation from flow, forwards `flow.get('action')` (from HTTP) to the three valves. For training the trainer sends action via POST /step; for deployment replace this node with one that runs the trained model. step_driver no longer sends to dump_valve; all three valves receive action from the agent.

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
