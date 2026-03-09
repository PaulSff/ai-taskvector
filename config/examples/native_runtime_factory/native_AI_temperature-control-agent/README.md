# Native runtime (env_factory) example

Temperature control using the **native** env: in-process `GraphEnv` built from a canonical process graph by `env_factory`.

- **temperature_process.yaml** — Wired process graph (Source, Valve, Tank, Sensor, RLAgent) with observations and actions connected to the agent. Required for training so observation/action spaces match.
- **temperature_workflow_wired.yaml** — Full workflow with thermodynamic units, canonical topology (RLAgent with `observation_source_ids` / `action_target_ids`), optional Random unit, and `model_path` for deployed best model. Use for runtime execution tests.
- **workflow.json** — Complete graph with canonical pipeline units explicit: Join (`collector`), Switch (`switch`), StepDriver (`step_driver`), Split (`split`), StepRewards (`step_rewards`), plus thermodynamic units and RLAgent. All connections wired (obs sources → Join → StepRewards; Switch → valves; StepDriver → Split → simulators). Load with `load_process_graph_from_file(path, format="template")` (default for `.json` is node_red).
- **training_config_native.yaml** — Training config: `source: native`, `type: thermodynamic`, `process_graph_path` pointing at this folder’s YAML.

## Train

From repo root:

```bash
python train.py --config config/examples/native_runtime_factory/native_AI_temperature-control-agent/training_config_native.yaml
```

Or use `--process-config` to override the process graph path; the config’s `process_graph_path` is used by default.

No Node-RED or PyFlow; everything runs in-process. Models are saved under `models/native_AI_temperature-control-agent/`.

## Test runtime execution

From repo root (uses random actions if no trained model is present):

```bash
python scripts/test_custom_runtime_workflow.py
```

This loads `temperature_workflow_wired.yaml`, builds the env via `env_factory`, and runs reset + 10 steps.
