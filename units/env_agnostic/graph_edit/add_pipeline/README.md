# Add Pipeline

Add a pipeline (RLGym, RLOracle, RLSet, LLMSet) to the graph. Env-agnostic; used in edit workflows.

## Purpose

Applies an add_pipeline edit: inserts the pipeline and its canonical topology. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with pipeline and wiring added |
| **Params**   | config    | —    | `pipeline` — object with `id`, `type`, `params` |

## Example

**Params:** `{"pipeline": {"id": "rl_training", "type": "RLGym", "params": {"observation_source_ids": [...], "action_target_ids": [...]}}}`  
**Input:** `{"graph": {"units": [...], "connections": [...]}}`  
**Output:** `{"graph": {"units": [..., pipeline unit, Join, Switch, ...], "connections": [...]}}`
