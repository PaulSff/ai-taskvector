# RL agent as a PyFlow node: train in your workflow

If you build your workflow in the **PyFlow editor** and want the RL agent to be a **PyFlow node** trained **in that same workflow**, follow this path.

**Roundtrip = external runtime.** The roundtrip idea is that training and execution both use the **external** runtime (e.g. Node-RED runs the flow; we send actions and get obs over HTTP/WS). For **PyFlow** we do **not** use the PyFlow runtime today: we load your exported JSON and run the graph with **our own executor**. So you get “same workflow (topology + code), train and deploy with our executor”; true roundtrip with PyFlow would mean integrating PyFlow’s EvaluationEngine so the flow runs exactly in their runtime.

**Roundtrip idea:** The goal is to use the **external runtime** — train and run in the **real** workflow engine (e.g. Node-RED runs the flow over HTTP/WS; we send actions, get obs/reward). For **Node-RED** we do that. For **PyFlow** we currently use your **same workflow graph** (exported JSON) but run it with **our own in-process executor**, not the PyFlow editor’s runtime. So: same topology and code, our execution. True roundtrip with PyFlow would mean driving the PyFlow runtime (e.g. their EvaluationEngine) so that training and deployment run **exactly** in PyFlow; that is not implemented yet.

---

## 1. Export your workflow from PyFlow

In the PyFlow editor, export/save your graph to a JSON file (e.g. `my_process.json`).  
That file is your **flow**: same nodes and connections you use in PyFlow. We will use it as the **environment** for training and, after training, add an **RL Agent** node to it.

---

## 2. Training config: use your flow as the env

Create a **training config** that uses the **external** env with the **pyflow** adapter and points to your flow.

Example `training_config_pyflow.yaml`:

```yaml
environment:
  source: external
  adapter: pyflow
  adapter_config:
    flow_path: "path/to/my_process.json"
    observation_sources: ["thermometer", "tank_level"]   # node ids whose outputs = observation
    action_targets: ["hot_valve", "cold_valve", "dump_valve"]   # node ids that receive the action
    goal:
      target_temp: 37.0
    # optional: reward_node: "reward_node_id"   # if you have a node that outputs reward

goal:
  type: setpoint
  target_temp: 37.0
  target_volume_ratio: [0.80, 0.85]

rewards:
  preset: temperature_and_volume
  weights: { temp_error: -1.0, volume_in_range: 10.0, dumping: -0.1 }

algorithm: PPO
total_timesteps: 100000
callbacks:
  model_dir: "models/my-pyflow-agent"
hyperparameters:
  learning_rate: 3.0e-4
  n_steps: 2048
  batch_size: 64
  n_epochs: 10
# ... rest as in config/examples/training_config.yaml
```

- **observation_sources**: list of **node ids** in your flow that produce the observation vector (e.g. sensor nodes). Their outputs are concatenated in order to form `obs`.
- **action_targets**: list of **node ids** that receive the action each step (e.g. valve nodes). The agent’s action vector is written into these nodes; the rest of the graph then runs with those values.
- **flow_path**: path to your PyFlow JSON (relative or absolute).

Training runs **in-process**: we load your JSON, normalize it to our graph format, and run it with our executor (topological order, code_blocks, Source/Valve/Tank/Sensor, etc.). No PyFlow app or WebSocket/HTTP in the loop. The RL algorithm (e.g. PPO) receives `obs` from your workflow and sends `action` into it every step.

---

## 3. Train

```bash
python train.py --config training_config_pyflow.yaml
```

The **environment** is your PyFlow workflow (same topology and code), executed by our adapter. The agent is trained exactly in that workflow.

---

## 4. Deploy the agent as a node in the same flow

After training, inject the trained model as an **RL Agent** node into the **same** flow and wire it to observations and actions:

```python
from deploy.flow_inject import inject_agent_into_pyflow_flow
import json

with open("path/to/my_process.json") as f:
    flow = json.load(f)

inject_agent_into_pyflow_flow(
    flow,
    agent_id="rl_agent_1",
    model_path="models/my-pyflow-agent/best/best_model.zip",
    observation_source_ids=["thermometer", "tank_level"],
    action_target_ids=["hot_valve", "cold_valve", "dump_valve"],
)

with open("path/to/my_process_with_agent.json", "w") as f:
    json.dump(flow, f, indent=2)
```

The flow now has an **RLAgent** node: inputs = observation nodes, outputs = action nodes. When we run this flow (same adapter, same executor), the RLAgent node is **executed inline**: we load the SB3 model and call `predict(obs)` each step—no external services.

You can run this “with agent” flow for inference (e.g. a small script that loads the flow, resets, and steps in a loop, or use it in a test harness). The agent is a normal node in the graph; it’s just that we execute that node by running the trained model.

---

## 5. Roundtrip: our executor vs external PyFlow runtime

- **Roundtrip** here means: train and run in the **external** runtime (the real workflow engine). For Node-RED we do that (flow runs in Node-RED; we talk to it over HTTP/WS). For **PyFlow we do not**: we run your graph with **our own executor**, not the PyFlow library or editor.
- So today: we load your **PyFlow JSON**, convert it to our canonical graph, and execute it ourselves (topological order, code_blocks, Source/Valve/Tank/Sensor/RLAgent). Same **workflow** (topology + code); **execution** is ours. That gives you “agent as a node trained in my workflow” with one caveat: behavior is our executor’s, not the PyFlow runtime’s.
- For **true roundtrip** with PyFlow (flow runs exactly in the PyFlow runtime during training and when you open it in the editor), we would need to integrate PyFlow’s EvaluationEngine and either a custom RL Agent node type or a callback so the agent runs in their graph. That is not implemented yet.

---

## Summary

| Step | What you do |
|------|-------------|
| 1 | Export your workflow from PyFlow to a JSON file. |
| 2 | Create a training config with `environment.source: external`, `adapter: pyflow`, and `adapter_config` with `flow_path`, `observation_sources`, `action_targets` (and optional `goal` / `reward_node`). |
| 3 | Run `train.py --config <that_config>`. The env is your workflow; the agent is trained in it. |
| 4 | Use `inject_agent_into_pyflow_flow()` to add an RL Agent node (with `model_path`) and wire it to the same observation and action nodes. |
| 5 | Run the resulting flow (with our adapter) for inference; the agent node runs inline (SB3 model loaded and used each step). |

The RL agent is a node in **your** workflow, trained **in** that workflow, and executed **inline** when you run the flow with our adapter.
