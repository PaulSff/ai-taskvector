"""Workflow Designer: JSON action line for github."""

TOOL_ACTION_PROMPT_LINE = ("""- Query GitHub actions:
    - github_search_repos: { "action": "github", "payload": { "method": "github_search_repos", "q": "topic:workflow", "sort": "stars", "per_page": 10 } }
    - github_search_code: { "action": "github", "payload": { "method": "github_search_code", "q": "def run_workflow repo:owner/name" } }
    - github_search_issues: { "action": "github", "payload": { "method": "github_search_issues", "q": "repo:owner/name is:issue" } }
    - github_get_repo: { "action": "github", "payload": { "method": "github_get_repo", "owner": "owner", "repo": "repo" } }
    - github_get_content: { "action": "github", "payload": { "method": "github_get_content", "owner": "owner", "repo": "repo", "path": "src/main.py", "ref": "main" } }
    - github_get_readme: { "action": "github", "payload": { "method": "github_get_readme", "owner": "owner", "repo": "repo", "ref": "main" } }
    - github_list_releases: { "action": "github", "payload": { "method": "github_list_releases", "owner": "owner", "repo": "repo", "per_page": 10 } }
    - github_list_commits: { "action": "github", "payload": { "method": "github_list_commits", "owner": "owner", "repo": "repo", "path": "", "sha": "", "per_page": 10 } }"""
)
