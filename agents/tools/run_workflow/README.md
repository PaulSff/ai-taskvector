# `run_workflow` tool

Run an arbitrary workflow JSON (or the current graph) from a structured `run_workflow` action—used heavily by Workflow Designer and nested graphs (e.g. `read_file`, `read_code_block`).

## Parser action

See `prompt.py` for `path`, `initial_inputs`, and `unit_param_overrides`. Normalized in `action_blocks.py` and executed by the canonical `RunWorkflow` unit.

## `tool.yaml`

- **`workflow`**: `run_workflow.json` — reference graph for `get_tool_workflow_path("run_workflow")` (console / tooling).

## Follow-up

`run_run_workflow_follow_up` in `__init__.py` → `TOOL_RUNNERS["run_workflow"]` in `registry.py`. Workflow Designer catalog includes this tool; Analyst role does not list it in `ORDERED_ANALYST_TOOLS`.
