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

Node-RED **runtime** can also be used as the **external environment** during training: sensors/observations in, actions out. The training process would leverage Node-RED's runtime I/O (real or simulated nodes). An adapter in **environments/external/node_red_adapter.py** would wrap Node-RED as a Gymnasium env: `_connect()`, `_get_obs()` (from sensor nodes), `_send_action()` (to valve/actuator nodes), `_reward()` (from goal config or a Node-RED node). Stub is in place; implement by subclassing `BaseExternalWrapper`. Then we only need the **model-as-node** adapter for deployment (see below).

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
  - **Config**: path to the trained model (e.g. `best_model.zip`), optional env/observation spec so the node knows how to build `obs` from incoming messages.
  - **Input**: one or more inputs that carry observation components (and optionally setpoint); the node assembles them into the same `obs` shape the env used during training.
  - **Output**: one or more outputs carrying actions (e.g. one message per valve, or one payload with the full action vector).
- **Runtime**: Node-RED can run in the same machine as your plant gateway, or on a server; the RL node would need access to Python + our stack (e.g. `stable_baselines3`, `torch`) or you’d expose the policy via a small **HTTP/gRPC service** that the node calls so Node-RED stays in JS and the model runs in a Python process.

So: **trained model lives inside (or behind) one Node-RED node**, wired between sensors/setpoints and actuators in the flow.

---

## Summary

| Step   | What happens |
|--------|----------------|
| **1. Import** | Full Node-RED workflow imported; we extract process topology (and preserve full flow for roundtrip). |
| **2. Train**  | Train via **node_red_adapter** (Node-RED runtime = env) or env factory from topology. Output: model file. |
| **3. Use**    | Trained model is a **custom Node-RED node** in the flow; observations in, actions out; wired between sensors and actuators. |

The Node-RED case is **all about the roundtrip**: import full workflow → train full process via node_red_adapter → use trained model in the flow.
