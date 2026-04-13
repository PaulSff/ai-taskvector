# `read_current_workflow` tool

Parser side-channel action: `{ "action": "read_current_workflow" }` (no extra fields).

## Follow-up

`run_read_current_workflow_follow_up` (in `__init__.py`) builds a **full** `core.graph.summary.graph_summary` for the canvas graph (structure on, code-block source policy from `get_summary_params` / open todo tasks), JSON-encodes it, and injects it into the next assistant turn’s `follow_up_context`—same chaining as RAG / `read_file` / `grep`.

## Declared workflow (`tool.yaml`)

`workflow` points at `gui/.../graph_summary_single.json` so `get_tool_workflow_path("read_current_workflow")` resolves; the follow-up does **not** run that graph (implementation is pure Python).

## Registration

- `assistants/tools/registry.py` → `TOOL_RUNNERS["read_current_workflow"]`
- `assistants/tools/catalog.py` → `ORDERED_ANALYST_TOOLS` (not Workflow Designer; WD already gets a full graph summary in the default inject)
- `units/canonical/process_agent/action_blocks.py` → merges `read_current_workflow: true` into `parser_output`
