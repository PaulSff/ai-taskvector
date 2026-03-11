# RLSet

Serving pipeline for a **trained RL agent**. Use `add_pipeline` with type `RLSet`.

**Topology:** Join → RLAgent → Switch. Observations feed the agent; actions go to the specified targets.

**Params:** `inference_url`, `model_path`, `observation_source_ids`, `action_target_ids`.

**Template:** `workflow.json` in this folder is registered as the pipeline template path.
