# Native `coding` environment

Gymnasium **`GraphEnv`** integration for workflows whose primary domain is **coding** (`units/coding`: HttpResponse, HttpIn, MCPTool, MCPSource units, etc.).

## Pieces

| Module | Role |
|--------|------|
| **`spec.py`** — `CodingEnvironmentSpec` | Calls `register_coding_units()` and `register_coding_units()` so typical pipelines have step functions when `environment_type` is **coding**. |
| **`loader.py`** — `load_coding_env(config, …)` | Loads graph + goal from config and delegates to `core.env_factory.build_env`. |

## Schema

`core.schemas.process_graph.EnvironmentType.CODING` is the string **`coding`**. The normalizer sets this when unit-type inference detects the **`coding`** tag and no higher-priority env (thermodynamic, data_bi, web, semantics) wins.

## Related

- Unit registration: `units/coding/__init__.py` (`register_coding_units`, env loader tag **`coding`**).
- Workflow execution without Gym: `runtime.run.run_workflow` and `ensure_full_unit_registry()` still load CODING units via env loaders.
