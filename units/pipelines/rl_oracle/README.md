# RLOracle

Step-handler pipeline for **external runtimes** (Node-RED, PyFlow, n8n, etc.). Use `add_pipeline` with type `RLOracle`.

**Roles:** Collector (observation in from sensors; returns obs/reward/done to client) and step_driver (action out to process). One UnitSpec; adapters map to the external runtime.

**Params:** `observation_source_ids`, `action_target_ids`, `adapter_config` (e.g. max_steps).

**Template:** `workflow.json` in this folder is registered as the pipeline template path.
