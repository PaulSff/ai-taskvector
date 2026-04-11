"""Workflow Designer: JSON action line for github."""

TOOL_ACTION_PROMPT_LINE = (
    '- github: Query GitHub: { "action": "github", "payload": { "action": "github_search_repos", "q": "topic:workflow" } }. '
    'payload.action can be: github_search_repos, github_search_code, github_search_issues, github_get_repo, '
    'github_get_content, github_get_readme, github_list_releases, github_list_commits. '
    'Include in payload the params for that action (e.g. q, owner, repo, path, ref, per_page).'
)
