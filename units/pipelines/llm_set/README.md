# LLMSet

LLM agent pipeline. Use `add_pipeline` with type `LLMSet`. **Template-driven:** topology is imported from `workflow.json`; no topology is built in code.

**Topology:** Observation sources (injects) → Merge → Prompt → LLMAgent → ProcessAgent → action targets. The JSON defines `pipeline_interface` (observation_inputs, action_output, params_unit_id) so the loader can wire the graph.

**Params:** `model_name`, `provider`, `system_prompt`, `observation_source_ids`, `action_target_ids`, optional `template_path` for the prompt template.

**Template:** `workflow.json` in this folder is registered as the pipeline template path. Edit this file to change the pipeline without code changes.
