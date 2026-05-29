# Native `rag` environment

Gymnasium **`GraphEnv`** integration for workflows whose primary domain is **RAG** (`units/rag`: RagSearch, Embedder, ChromaIndexer, ingest units, etc.).

## Pieces

| Module | Role |
|--------|------|
| **`spec.py`** — `RagEnvironmentSpec` | Calls `register_rag_units()` and `register_data_bi_units()` so typical pipelines (Filter, JsonParser, FileTypeDetector, …) have step functions when `environment_type` is **rag**. |
| **`loader.py`** — `load_rag_env(config, …)` | Loads graph + goal from config and delegates to `core.env_factory.build_env`. |

## Schema

`core.schemas.process_graph.EnvironmentType.RAG` is the string **`rag`**. The normalizer sets this when unit-type inference detects the **`rag`** tag and no higher-priority env (thermodynamic, data_bi, web, semantics) wins.

## Related

- Unit registration: `units/rag/__init__.py` (`register_rag_units`, env loader tag **`rag`**).
- Workflow execution without Gym: `runtime.run.run_workflow` and `ensure_full_unit_registry()` still load RAG units via env loaders.
