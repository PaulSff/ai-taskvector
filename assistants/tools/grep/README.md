# `grep` tool

Search a pattern inside a file path or inline text (e.g. logs). Used from assistant chat follow-ups and related workflows.

## Parser action

See `prompt.py` for `pattern`, `source`, and optional upstream context.

## `tool.yaml`

- **`workflow`**: `grep.json` — graph wired to the canonical `grep` unit for `get_tool_workflow_path("grep")`.

## Follow-up

`run_grep_follow_up` in `__init__.py` → `TOOL_RUNNERS["grep"]` in `registry.py`.
