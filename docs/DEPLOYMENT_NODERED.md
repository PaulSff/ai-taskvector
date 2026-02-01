# Trained agent as a Node-RED custom node

This doc projects **where our trained model sits** in the flow when you use Node-RED for both design and runtime.

## Short answer

**Yes.** An agent trained in our platform can be implemented as a **custom Node-RED node**. At runtime the trained model sits **in the flow** as one node: **observations in** (from sensors / setpoints), **actions out** (to valves / actuators).

---

## Node-RED as external environment (training)

Node-RED **runtime** can also be used as the **external environment** during training: sensors/observations in, actions out. The training process would leverage Node-RED's runtime I/O (real or simulated nodes). An adapter in **environments/external/node_red_adapter.py** would wrap Node-RED as a Gymnasium env: `_connect()`, `_get_obs()` (from sensor nodes), `_send_action()` (to valve/actuator nodes), `_reward()` (from goal config or a Node-RED node). Stub is in place; implement by subclassing `BaseExternalWrapper`. Then we only need the **model-as-node** adapter for deployment (see below).

---

## End-to-end flow

### Design time (today)

1. **Node-RED** (or our GUI): you design the **process graph** (units + connections) — e.g. Source, Valve, Tank, Sensor nodes.
2. **Export** the flow JSON → import into our **constructor GUI** (or paste JSON).
3. **Normalizer** → canonical `ProcessGraph` → **env factory** → Gymnasium env.
4. **Training config** (goal, rewards, algorithm) → **train.py** → Stable-Baselines3 (e.g. PPO).
5. **Output**: saved model (e.g. `models/<agent>/best/best_model.zip`).

So: **Node-RED / GUI → process graph → our platform → train → model file.**

### Runtime (projected)

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

| Phase        | Where the model sits |
|-------------|-----------------------|
| **Design**  | Not in Node-RED. Process graph (from Node-RED or GUI) → our platform → **train** → **model file** on disk. |
| **Runtime** | **Custom Node-RED node** that loads (or calls) the model; **observations in**, **actions out**; wired between Sensor/Setpoint nodes and Valve/actuator nodes. |

This keeps a single place to train (our constructor) and a clear place in the flow where the trained agent runs (one node in Node-RED).
