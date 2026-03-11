# Pipelines

Pipeline types (RLGym, RLOracle, RLSet, LLMSet) are registered in the unit registry and added to the graph via **add_pipeline**. Each pipeline lives in its own package with a README and `workflow.json`.

## Packages

| Package     | Type      | Scope       | Template path (in registry) |
|-------------|-----------|-------------|-----------------------------|
| `rl_gym/`   | RLGym     | canonical   | `units/pipelines/rl_gym/workflow.json` |
| `rl_oracle/`| RLOracle  | external    | `units/pipelines/rl_oracle/workflow.json` |
| `rl_set/`   | RLSet     | any         | `units/pipelines/rl_set/workflow.json` |
| `llm_set/`  | LLMSet    | any         | `units/pipelines/llm_set/workflow.json` |

Each package contains:
- **`__init__.py`** — registers the pipeline type with `template_path` pointing at its `workflow.json`.
- **`README.md`** — short description and params.
- **`workflow.json`** — canonical topology; for LLMSet this includes `pipeline_interface` so the loader can wire observation inputs and action outputs.

**LLMSet** is template-driven: the loader imports `workflow.json` and wires by `pipeline_interface`. Other types register their path for reference; topology can also be built in `graph_edits` when adding the pipeline.

## Registry

- `register_all_pipelines()` — registers all four (idempotent).
- Individual: `register_rl_gym()`, `register_oracle_units()`, `register_rl_set()`, `register_llm_set()`.
