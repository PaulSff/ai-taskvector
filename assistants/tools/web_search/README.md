# `web_search` tool

Web search (e.g. DuckDuckGo) from a structured `web_search` action; results are injected into the next follow-up turn.

## Parser action

See `prompt.py` for `query` and optional `max_results`.

## `tool.yaml`

- **`workflow`**: `web_search.json` — Inject → web search path for `get_tool_workflow_path("web_search")`.

## Follow-up

`run_web_search_follow_up` in `__init__.py` → `TOOL_RUNNERS["web_search"]` in `registry.py`.
