# ApplyTrainingConfigEdits unit

Canonical unit that **applies a list of training-config edits** to the current config and outputs the updated config.

- **Inputs**
  - `training_config` (Any) — Current config as dict or TrainingConfig (with `model_dump`). If missing, treated as empty `{}`.
  - `edits` (Any) — List of edit dicts from TrainingConfigParser (e.g. `no_edit`, `goal`, `reward_formula_add`, partial `rewards`/`hyperparameters`/`callbacks`).
- **Outputs**
  - `result` (Any) — Dict with `kind` (`no_edits` | `applied` | `apply_failed`), `content_for_display`, `config` (updated dict), `edits`.
  - `status` (Any) — `attempted`, `success`, `error`, optional `edits_summary`.
  - `config` (Any) — Updated config dict (canonical schema) for saving to file or downstream.
  - `error` (str) — Error message when apply or validation failed.

Uses `core.gym.training_edits.apply_config_edits` and `core.normalizer.to_training_config`. Used in `assistants/roles/rl_coach/rl_coach_workflow.json`: inject_training_config_dict → ApplyTrainingConfigEdits (training_config); TrainingConfigParser (edits) → ApplyTrainingConfigEdits (edits). Standalone workflow: `gui/components/workflow/core/apply_training_config_edits_single.json` (see `core_workflows.run_apply_training_config_edits`).
