# `browse` tool

Fetch and parse a web page (URL) for the assistant, typically after a `browse` / `browse_url` action in structured output.

## Parser action

See `prompt.py`. Side channel key on `parser_output` is `browse_url` (catalog maps tool id `browse` → that key for Workflow Designer).

## `tool.yaml`

- **`workflow`**: `browser.json` — Inject → browse/HTML extraction path for `get_tool_workflow_path("browse")`.

## Follow-up

`run_browse_follow_up` in `__init__.py` → `TOOL_RUNNERS["browse"]` in `registry.py`.
