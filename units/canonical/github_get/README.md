# GithubGET

Canonical unit that wraps GitHub REST API **GET** methods. Accepts an action command (e.g. search repos, get file content) and returns structured data. Optional credentials via params for higher rate limits and private repos.

## Interface

- **Input:** `action` (Any) — dict with key `"action"` and action-specific parameters.
- **Output:** `data` (Any) — API response (list or object); `error` (str) — message on failure.
- **Params:** `token` (str, optional) — GitHub personal access token. Without token, unauthenticated requests are limited to 60/hour (search) or 60/hour for other endpoints; with token, 5,000/hour.

## Supported actions

| Action | Purpose | Required params | Optional params |
|--------|---------|-----------------|-----------------|
| `github_search_repos` | Search repositories | `q` (or `query`) | `sort` (stars, forks, updated), `per_page`, `page` |
| `github_search_code` | Search code | `q` (or `query`) | `per_page`, `page` (use `repo:owner/name` in `q` to scope) |
| `github_search_issues` | Search issues/PRs | `q` (or `query`) | `sort` (comments, created, updated), `per_page`, `page` |
| `github_get_repo` | Get repo metadata | `owner`, `repo` | — |
| `github_get_content` | Get file or directory contents | `owner`, `repo`, `path` | `ref` (branch/tag) |
| `github_get_readme` | Get README | `owner`, `repo` | `ref` |
| `github_list_releases` | List releases | `owner`, `repo` | `per_page` |
| `github_list_commits` | List commits | `owner`, `repo` | `path`, `sha`, `per_page` |

## Example (workflow / Inject)

```json
{ "action": "github_search_repos", "q": "topic:workflow automation", "sort": "stars", "per_page": 5 }
{ "action": "github_get_content", "owner": "myorg", "repo": "myrepo", "path": "README.md", "ref": "main" }
{ "action": "github_search_code", "q": "run_workflow repo:myorg/myrepo" }
```

## Discussion: what’s useful for the Workflow Designer

- **Search repos** — “Find repos about X”, “popular workflow engines” → inject `github_search_repos` with `q`, use `data.items` in follow-up context.
- **Search code** — “Find where we call run_workflow”, “example of Y” → `github_search_code` with `q` (optionally `repo:owner/name`); good for referencing external code.
- **Search issues** — “Open issues in repo X”, “PRs that mention Y” → `github_search_issues` with `q` (e.g. `repo:owner/repo is:issue`).
- **Get repo** — Metadata (description, stars, default branch) for a given repo.
- **Get file / readme** — “Show README of repo X”, “contents of path Y” → `github_get_content` or `github_get_readme`; file content is base64 in `data.content` (decode in a downstream unit or in the assistant if needed).
- **Releases / commits** — “Latest release of X”, “recent commits” → `github_list_releases`, `github_list_commits` for changelog or “what changed” context.

Integration with the designer can mirror **web_search** / **browse_url**: the LLM outputs a structured action (e.g. `{"action": "github_search_repos", "q": "..."}`); the chat runs a small workflow (Inject → GithubGET) and injects the result into follow-up context for the next turn.

Possible extensions (not implemented): `github_get_file_raw` (decode base64 and return text), or a single `github_search` action that dispatches by `type: "repos"|"code"|"issues"` to keep the parser surface small.
