# `github` tool

Query GitHub (repos, code, issues, content, releases, commits) via structured `github` actions in the model output.

## Parser action

See `prompt.py` for payload shape (`action`, nested `payload` per GitHub API surface).

## `tool.yaml`

- **`workflow`**: `github_get.json` — Inject → `GithubGET` for `get_tool_workflow_path("github")`.

## Follow-up

`run_github_follow_up` in `__init__.py` → `TOOL_RUNNERS["github"]` in `registry.py`.
