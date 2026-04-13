# `run_rl_training` tool

Run RL training from a packaged graph: inject config/paths → `RunRLTraining` unit. Used from the Training tab and any workflow that references this tool graph.

## Parser action

Not a typical chat “tool line” tool; training UIs and graphs load `get_tool_workflow_path("run_rl_training")` when needed.

## `tool.yaml`

- **`workflow`**: `run_rl_training.json`.

## Follow-up

There is no entry in `assistants/tools/registry.py` `TOOL_RUNNERS` for this id; execution is workflow-driven rather than the chat parser follow-up chain.
