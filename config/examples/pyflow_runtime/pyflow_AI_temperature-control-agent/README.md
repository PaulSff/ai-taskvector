# PyFlow runtime example

Temperature control using the **PyFlow** adapter: the graph runs in-process (no Node-RED or PyFlow app); the adapter executes the flow and injects actions into the valve nodes.

## Flow files

- **temperature_process_pyflow_no_agent.json** — Flow **before** the RL Agent node is added and wired. Use this as the starting point when you want to add an agent to an existing process graph (e.g. import, then add a placeholder agent and wire it).

```
Hot water source -> T sensor -> Valve -> Tank
```

- **temperature_process_pyflow_wired.json** — Flow **after** the Agent node is wired: observation sources and action targets are connected in the same order as in the training config. Use this flow for training (set `adapter_config.flow_path` to this file) and as the target when deploying the trained model.

```
Hot water source --> T sensor --> Valve --> Tank
                        ↓           ↑
                        └─→ Agent ─→┘
```

## Training config

- **training_config_pyflow.yaml** — Training config: `source: external`, `adapter: pyflow`, with `flow_path`, `observation_sources`, `action_targets`, and optional `reward_node` and `goal` in `adapter_config`.

## Train

From repo root:

```bash
python train.py --config config/examples/pyflow_runtime/pyflow_AI_temperature-control-agent/training_config_pyflow.yaml
```

No external runtime needed; the adapter runs the flow in-process. Models are saved under `models/pyflow_AI_temperature-control-agent/`. See [config/TRAINING_CONFIG_GUIDE.md](../../../TRAINING_CONFIG_GUIDE.md) for full PyFlow pipeline details.
