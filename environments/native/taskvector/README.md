# Native `taskvector` environment

Gymnasium **`GraphEnv`** integration for workflows whose primary domain is **taskvector** (`units/taskvector`: HttpResponse, HttpIn, MCPTool, MCPSource units, etc.).

## Pieces

| Module | Role |
|--------|------|
| **`spec.py`** — `TaskvectorEnvironmentSpec` | Calls `register_taskvector_units()` and `register_taskvector_units()` so typical pipelines have step functions when `environment_type` is **taskvector**. |
| **`loader.py`** — `load_taskvector_env(config, …)` | Loads graph + goal from config and delegates to `core.env_factory.build_env`. |

## Schema

`core.schemas.process_graph.EnvironmentType.TASKVECTOR` is the string **`taskvector`**. The normalizer sets this when unit-type inference detects the **`taskvector`** tag and no higher-priority env (thermodynamic, data_bi, web, semantics) wins.

## Related

- Unit registration: `units/taskvector/__init__.py` (`register_taskvector_units`, env loader tag **`taskvector`**).
- Workflow execution without Gym: `runtime.run.run_workflow` and `ensure_full_unit_registry()` still load TASKVECTOR units via env loaders.
