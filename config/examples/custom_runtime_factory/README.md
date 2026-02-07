# Custom runtime examples (env_factory)

Training using the **custom** environment: in-process `TemperatureControlEnv` built from a canonical process graph by `env_factory`. No external runtime (Node-RED, PyFlow) required.

| Folder | Description |
|--------|-------------|
| **custom_AI_temperature-control-agent/** | Temperature mixing: wired process graph (YAML) + training_config_custom.yaml. Run: `python train.py --config config/examples/custom_runtime_factory/custom_AI_temperature-control-agent/training_config_custom.yaml` |

Process graph must include exactly one **RLAgent** unit with inputs (observations) and outputs (actions) wired; see `env_factory/factory.py` and `docs/TEMPERATURE_CONTROL_WORKFLOW.md`.
