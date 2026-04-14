# `add_comment` tool

Leave a note on the current workflow graph (`add_comment` / `add_comment` edit). Used from Workflow Designer and Analyst chat follow-ups.

## Parser action

See `prompt.py` (`TOOL_ACTION_PROMPT_LINE`). The model emits a JSON object with `"action": "add_comment"` and note text; `units/canonical/process_agent/action_blocks.py` forwards it into `parser_output` for apply and follow-up.

## `tool.yaml`

- **`workflow`**: `edit_add_comment.json` — inject + graph edit path for tooling that resolves `get_tool_workflow_path("add_comment")`.

## Follow-up

`run_add_comment_follow_up` in `__init__.py` registers in `assistants/tools/registry.py` as `TOOL_RUNNERS["add_comment"]`. Chained like other tools via `gui/chat/parser_follow_up/chain.py` using `ORDERED_WORKFLOW_DESIGNER_TOOLS` / `ORDERED_ANALYST_TOOLS` (`catalog.py`).
