# Node-RED roundtrip: full workflow → train → model in the flow

This doc describes the **Node-RED roundtrip**: import the full workflow, train the model with the full process via the Node-RED adapter, then use the trained model in the same flow as a custom node.

## The roundtrip

1. **Import full workflow** — User exports the full Node-RED flow (process-unit nodes + functions, MQTT, etc.). We import it; we extract process topology for env/training and, for roundtrip, preserve or store the full flow so we can re-export it with the model node added.
2. **Train the model as a custom node in the workflow** — Training uses the **full process** via **node_red_adapter**: Node-RED runtime is the external env (sensors in, actions out). We wrap it as a Gymnasium env and train (e.g. PPO). The trained model is then the “custom node” we inject back into the flow.
3. **Use the trained model in the flow** — After training, we add (or update) an **RL Agent** custom node in the flow that loads our trained model. The flow now runs with the trained policy wired between sensors and actuators. Roundtrip complete.

So: **import full workflow → train full process via node_red_adapter → use trained model in the flow.**

---

## Trained agent as a Node-RED custom node

**Yes.** An agent trained in our platform is deployed as a **custom Node-RED node**. At runtime the trained model sits **in the flow** as one node: **observations in** (from sensors / setpoints), **actions out** (to valves / actuators).

---

## Node-RED as external environment (training)

Node-RED **runtime** can be used as the **external environment** during training. The adapter in **environments/external/node_red_adapter.py** wraps a Node-RED flow as a Gymnasium env.

**Step-endpoint convention:** The flow must expose one HTTP endpoint (e.g. an **HTTP In** node) that we POST to for each step and for reset. No Admin API or MQTT is required.

- **Step:** `POST step_url` with body `{ "action": [float, ...] }` → response `{ "observation": [...], "reward": float, "done": bool }`.
- **Reset:** `POST step_url` with body `{ "reset": true }` → response `{ "observation": [...], "reward": 0, "done": false }`.

Config: `step_url` (e.g. `http://127.0.0.1:1880/step`), optional `obs_shape` / `action_shape`, `timeout`. The flow designer adds an HTTP In node (e.g. path `/step`) and a **Function** node that: on `msg.payload.reset` calls the process reset and returns the initial observation; otherwise applies `msg.payload.action` to the valves, runs one step, reads sensors, computes reward, and returns observation, reward, and done. See **environments/external/node_red_adapter.py** for the client implementation.

**EdgeLinkd (Rust runtime):** For **faster execution** and lower memory, you can use [EdgeLinkd](https://github.com/oldrev/edgelinkd) — a Node-RED–compatible runtime reimplemented in Rust (drop-in `flows.json`, same default port 1888, headless or with integrated web UI). Adapter stub: **environments/external/node_red_rust_edgelinkd_adapter.py**. Same roundtrip and flow format; when both adapters are implemented, training can target either Node-RED or EdgeLinkd.

---

## End-to-end flow (roundtrip)

### 1. Import full workflow

1. **Node-RED**: user has (or designs) the **full workflow** — process-unit nodes (Source, Valve, Tank, Sensor) plus any standard nodes (function, MQTT, HTTP, etc.).
2. **Export** the full flow JSON → **import** into our constructor GUI (or paste JSON). We extract process topology for our use; for roundtrip we preserve/store the full flow so we can re-export it with the model node added.
3. **Train**: either (a) **node_red_adapter** — Node-RED runtime is the env (sensors in, actions out); we wrap it as gym.Env and train against the full process in Node-RED; or (b) **env factory** from extracted topology (current path). Output: saved model (e.g. `models/<agent>/best/best_model.zip`).
4. **Re-export / inject**: flow is updated with an **RL Agent** custom node that loads the trained model; user re-imports into Node-RED or we export the modified flow.

So: **import full workflow → train (via node_red_adapter or env factory) → model file → inject model node into flow.**

### 2. Use trained model in the flow (runtime)

1. **Node-RED** runs the **operational flow** (same or separate instance).
2. **Custom node: “RL Agent”** (or “Process Controller”):
   - **Inputs**: observations — e.g. from **Sensor** nodes (temperature, level, etc.) and **Setpoint** nodes (target temp, target volume). Message payloads are assembled into the same observation vector your env uses.
   - **Node logic**: loads our trained model (e.g. SB3 `PPO.load(path)`), calls `model.predict(obs)`, optionally masks/deterministic.
   - **Outputs**: actions — e.g. to **Valve** nodes or actuator nodes (open/close, setpoints). Those nodes then talk to the real plant (MQTT, OPC-UA, HTTP, etc.).

So the **trained agent sits as one node** in the Node-RED flow, **wired between**:

- **Upstream**: Sensor nodes, setpoint nodes → observation vector → **RL Agent node**.
- **Downstream**: **RL Agent node** → action vector → Valve / actuator nodes → plant.

```
[Setpoint] ──┐
[Sensor 1] ──┼──► [RL Agent node] ──► [Valve 1]
[Sensor 2] ──┘         │              [Valve 2]
                       │              [Valve 3]
                  (loads our
                   trained .zip)
```

---

## What you’d implement

- **Custom Node-RED node** (e.g. “RL Agent” or “Process Controller”):
  - **Deploy (Python):** `deploy.inject_agent_into_flow(flow, agent_id, model_path, observation_source_ids, action_target_ids)` adds the RL Agent node to the flow JSON; save or push to runtime.
  - **Config**: path to the trained model (e.g. `best_model.zip`), optional env/observation spec so the node knows how to build `obs` from incoming messages.
  - **Input**: one or more inputs that carry observation components (and optionally setpoint); the node assembles them into the same `obs` shape the env used during training.
  - **Output**: one or more outputs carrying actions (e.g. one message per valve, or one payload with the full action vector).
- **Runtime**: Node-RED can run in the same machine as your plant gateway, or on a server; the RL node would need access to Python + our stack (e.g. `stable_baselines3`, `torch`) or you’d expose the policy via a small **HTTP/gRPC service** that the node calls so Node-RED stays in JS and the model runs in a Python process.

So: **trained model lives inside (or behind) one Node-RED node**, wired between sensors/setpoints and actuators in the flow.

---

## Import scenarios: workflow with or without an agent node

When the user imports a workflow (Node-RED, EdgeLinkd, PyFlow), we need to handle two cases.

### Identifying an existing RL Agent node in the workflow

- **Convention:** An **RL Agent node** in the flow is a unit whose **type** is one of: `RLAgent`, `ProcessController`, `rl_agent` (or editor-specific equivalents). The **node id** (or a param such as `agent_id` / `model_name`) is the **agent name** and maps to the model folder: **`models/<agent_name>/`**.
- **Example:** A node with `id: "temperature_controller"` and `type: "RLAgent"` → model dir **`models/temperature_controller/`** (we expect `models/temperature_controller/best/best_model.zip` and `training_config_used.yaml` there after training).
- **Resolution:** On import, scan units for type in the agent types above. If exactly one is found, we treat it as the **existing agent node** and use its id (or `params.agent_id` if set) to resolve the model directory. If multiple exist, the UI can let the user choose which one to train/test, or we take the first and document the convention.

So: **agent node id (or params.agent_id) → folder `models/<agent_id>/`**. No need to deploy the node “into” the runtime at import time when one already exists; we only need to know which node is the agent and where its model lives.

### Scenario 1: Workflow has **no** agent node

1. **After import:** Detect that no unit has type in (RLAgent, ProcessController, rl_agent). Show a prompt: **“Would you like to add an AI agent to this workflow?”**
2. **User chooses “Yes”:**
   - **In our system:** Add a **placeholder agent unit** to the canonical process graph (e.g. `type: RLAgent`, `id: rl_agent_1` or a user-chosen name like `temperature_controller`). Optionally create the folder **`models/<agent_id>/`** so training has a place to write the model. Do **not** push the node into the live Node-RED/EdgeLinkd runtime yet—we only update the graph we hold in the constructor.
   - **User flow:** User configures training (goal, rewards, observation/action mapping), runs **Train**. After training, the model is saved under `models/<agent_id>/`. Then the user can **Deploy** (see below).
3. **User chooses “No”:** Use the workflow for topology-only training (env factory from graph) or for design only; no agent node is added.

**Why training does not require the agent node in the live flow**

- **Training with our custom simulator (env_factory):** We don’t run Node-RED at all. We build a Gymnasium env in Python from the process graph (sources, valves, tank, sensors). The “agent” during training is our training loop (e.g. PPO); the agent **node** in the graph is only a placeholder for “where the model will sit later.” So no live flow is needed; the node doesn’t need to be deployed to train.
- **Training with the external runtime (node_red_adapter):** The flow runs in Node-RED (or EdgeLinkd) and we connect to it: we read observations from sensor nodes and send actions to valve/actuator nodes. Our **Python training process** acts as the agent; the flow does not need to contain an RL Agent node during training. The flow only needs the process (sensors, valves, etc.). After training we **deploy** the agent node so that the flow can run **standalone** with the model inside it (inference without our trainer connected).

So: **training** uses either our simulator or the live flow as the *environment*; the agent is either our code (custom) or our process talking to the flow (external). The **agent node** in the flow is for **runtime inference** after training.

**Deploy (after training):** When the user wants the agent **in the live flow** so the flow can run with the trained model (e.g. in production), a **“Deploy”** step is needed: we inject the RL Agent node into the flow JSON (wires from sensors/setpoints, to valves/actuators) and export or push the flow. So: **Add agent** = add unit in our graph + prepare model dir; **Train** = train without the node in the flow; **Deploy** = add the node to the flow so the flow can run with the model inside it.

### Scenario 2: Workflow **already has** an agent node

1. **On import:** We detect one (or more) units with type in (RLAgent, ProcessController, rl_agent). Take the node’s **id** (or `params.agent_id`) as the **agent name**.
2. **Model folder:** Resolve **`models/<agent_name>/`**. If that folder exists and contains a trained model (e.g. `best/best_model.zip`) and `training_config_used.yaml`, we can offer **Test** (and **Retrain**). If the folder is missing or empty, treat it like “agent node exists but not yet trained” and offer **Train** (same as adding a new agent, but the node is already in the graph).
3. **Train / Test:** Use the same training config and environment as before (from `training_config_used.yaml`) or let the user pick a config. No need to “add” the node; we only need to know which node is the agent and where its model lives.

### Summary

| Scenario | Detection | Action |
|----------|-----------|--------|
| **No agent in workflow** | No unit with type RLAgent / ProcessController / rl_agent | Prompt: “Add an AI agent?” → Yes: add placeholder unit (type RLAgent, id e.g. `rl_agent_1`), create `models/<id>/`; then Train; Deploy later (export/push flow with node). |
| **Agent node present** | Unit(s) with agent type; id (or params.agent_id) = agent name | Resolve `models/<agent_name>/`. If model exists: offer Test / Retrain; else offer Train. No deploy needed for testing; deploy only to push updated flow to runtime. |

---

## Summary

| Step   | What happens |
|--------|----------------|
| **1. Import** | Full Node-RED workflow imported; we extract process topology (and preserve full flow for roundtrip). |
| **2. Train**  | Train via **node_red_adapter** (Node-RED runtime = env) or env factory from topology. Output: model file. |
| **3. Use**    | Trained model is a **custom Node-RED node** in the flow; observations in, actions out; wired between sensors and actuators. |

The Node-RED case is **all about the roundtrip**: import full workflow → train full process via node_red_adapter → use trained model in the flow.
