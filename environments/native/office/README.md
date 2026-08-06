# Native `ofiice` environment

Gymnasium **`GraphEnv`** integration for workflows whose primary domain is **OFFICE** (`units/office`)

## Pieces

| Module | Role |
|--------|------|
| **`spec.py`** — `OfficeEnvironmentSpec` | Calls `register_office_units()` and `register_office_units()` so typical pipelines have step functions when `environment_type` is **office**. |
| **`loader.py`** — `load_office_env(config, …)` | Loads graph + goal from config and delegates to `core.env_factory.build_env`. |

## Schema

`core.schemas.process_graph.EnvironmentType.OFFICE` is the string **`office`**. The normalizer sets this when unit-type inference detects the **`office`** tag and no higher-priority env (thermodynamic, data_bi, web, semantics) wins.

## Related

- Unit registration: `units/office/__init__.py` (`register_office_units`, env loader tag **`office`**).
- Workflow execution without Gym: `runtime.run.run_workflow` and `ensure_full_unit_registry()` still load `OFFICE` units via env loaders.
