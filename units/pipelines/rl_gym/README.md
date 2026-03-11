# RLGym

Full training pipeline for the **canonical (native) runtime**. Use `add_pipeline` with type `RLGym`.

**Topology:** observations → Join → StepRewards; Switch → actions; StepDriver → Split → simulators. The policy runs in the training loop (e.g. SB3), not inside the graph.

**Params:** `observation_source_ids`, `action_target_ids`, `max_steps`, optional reward config.

**Template:** `workflow.json` in this folder is registered as the pipeline template path; topology can also be built in code in `graph_edits` when adding the pipeline.
