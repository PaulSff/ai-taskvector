# Custom runtime (env_factory) example

Temperature control using the **custom** env: in-process `GraphEnv` built from a canonical process graph by `env_factory`.

- **temperature_process.yaml** — Wired process graph (Source, Valve, Tank, Sensor, RLAgent) with observations and actions connected to the agent. Required for training so observation/action spaces match.
- **training_config_custom.yaml** — Training config: `source: custom`, `type: thermodynamic`, `process_graph_path` pointing at this folder’s YAML.

## Train

From repo root:

```bash
python train.py --config config/examples/custom_runtime_factory/custom_AI_temperature-control-agent/training_config_custom.yaml
```

Or use `--process-config` to override the process graph path; the config’s `process_graph_path` is used by default.

No Node-RED or PyFlow; everything runs in-process. Models are saved under `models/custom_AI_temperature-control-agent/`.
