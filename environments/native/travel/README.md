# Native `travel` environment

Gymnasium **`GraphEnv`** integration for workflows whose primary domain is **NETWORK** (`units/network`: HttpResponse, HttpIn, MCPTool, MCPSource units, etc.).

## Pieces

| Module | Role |
|--------|------|
| **`spec.py`** — `TravelEnvironmentSpec` | Calls `register_travel_units()` and `register_travel_units()` so typical pipelines have step functions when `environment_type` is **network**. |
| **`loader.py`** — `load_travel_env(config, …)` | Loads graph + goal from config and delegates to `core.env_factory.build_env`. |

## Schema

`core.schemas.process_graph.EnvironmentType.TRAVEL` is the string **`travel`**. The normalizer sets this when unit-type inference detects the **`travel`** tag and no higher-priority env (thermodynamic, data_bi, web, semantics) wins.

## Related

- Unit registration: `units/travel/__init__.py` (`register_travel_units`, env loader tag **`travel`**).
- Workflow execution without Gym: `runtime.run.run_workflow` and `ensure_full_unit_registry()` still load TRAVEL units via env loaders.
