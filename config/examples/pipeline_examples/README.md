# Pipeline workflow examples

Pipeline templates live in **`units/pipelines/`**, one folder per pipeline type:

- `units/pipelines/rl_gym/workflow.json` — RLGym
- `units/pipelines/rl_oracle/workflow.json` — RLOracle
- `units/pipelines/rl_set/workflow.json` — RLSet
- `units/pipelines/llm_set/workflow.json` — LLMSet (template-driven, has `pipeline_interface`)

Each package has a README and registers its path in the unit registry. See **`units/pipelines/README.md`**.
