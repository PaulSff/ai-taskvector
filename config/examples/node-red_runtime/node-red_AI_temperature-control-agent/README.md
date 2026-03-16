# Node-RED runtime example

Temperature control using **Node-RED** as the environment: the flow runs in Node-RED and exposes `POST /step`; training talks to it over HTTP.

## Flow files

- **temperature_process_node_red_no_agent.json** — Flow **before** the RL Agent node is added and wired. Use this as the starting point when you want to add an agent to an existing process flow (e.g. import into the constructor, then add a placeholder agent and wire it).

```
Hot water source -> T sensor -> Valve -> Tank
```

- **temperature_process_node_red_wired.json** — Flow **after** the Agent node is wired: observations (sensors, setpoint) and actions (valves) are connected to the RL Agent node in the same order used for training and deploy. Use this flow when running training (deploy it in Node-RED so the step endpoint matches) and as the target when deploying the trained model.

```
Hot water source --> T sensor --> Valve --> Tank
                        ↓           ↑
                        └─→ Agent ─→┘
```

## Training config

- **training_config_node_red.yaml** — Training config: `source: external`, `adapter: node_red`, `adapter_config.step_url` pointing at your Node-RED step endpoint (e.g. `http://127.0.0.1:1880/step`).

## Train

1. Start Node-RED and deploy the **wired** flow (`temperature_process_node_red_wired.json`) so the step URL is available.
2. From repo root:

```bash
python runtime/train.py --config config/examples/node-red_runtime/node-red_AI_temperature-control-agent/training_config_node_red.yaml
```

Models are saved under `models/node-red_AI_temperature-control-agent/`. See [config/TRAINING_CONFIG_GUIDE.md](../../../TRAINING_CONFIG_GUIDE.md) for full Node-RED pipeline details.
