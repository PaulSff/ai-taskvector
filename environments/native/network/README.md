# Native `network` environment

Gymnasium **`GraphEnv`** integration for workflows whose primary domain is **NETWORK** (`units/network`: HttpResponse, HttpIn, MCPTool, MCPSource units, etc.).

## Pieces

| Module | Role |
|--------|------|
| **`spec.py`** — `NetworkEnvironmentSpec` | Calls `register_network_units()` and `register_network_units()` so typical pipelines have step functions when `environment_type` is **network**. |
| **`loader.py`** — `load_network_env(config, …)` | Loads graph + goal from config and delegates to `core.env_factory.build_env`. |

## Schema

`core.schemas.process_graph.EnvironmentType.NETWORK` is the string **`network`**. The normalizer sets this when unit-type inference detects the **`network`** tag and no higher-priority env (thermodynamic, data_bi, web, semantics) wins.

## Related

- Unit registration: `units/network/__init__.py` (`register_network_units`, env loader tag **`network`**).
- Workflow execution without Gym: `runtime.run.run_workflow` and `ensure_full_unit_registry()` still load NETWORK units via env loaders.
