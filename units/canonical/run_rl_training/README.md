# RunRLTraining unit

Canonical unit that **runs RL training** from an action command (e.g. from GUI or workflow).

- **Inputs**
  - `action` (Any) — Dict with `"action": "run_rl_training"`, required `config_path` (training config YAML), and optional `process_config_path`, `total_timesteps`, `checkpoint_path`.
- **Outputs**
  - `result` (Any) — Dict with `status` ("success" | "failed"), `message`, `best_model_save_path`, `final_model_save_path` (from config callbacks after run).
  - `error` (str) — Non-empty on failure (missing config, import error, or exception from training).

Calls `train.run_training_from_config(config_path, ...)`. Training runs synchronously in the unit step (blocking). For GUI, run the workflow in a thread or executor. Used in workflow: Inject (action) → RunRLTraining.

**Example action:**
```json
{
  "action": "run_rl_training",
  "config_path": "config/examples/training_config.yaml",
  "process_config_path": null,
  "total_timesteps": 100000,
  "checkpoint_path": null
}
```
