"""
GithubGET unit: GitHub REST API GET methods for workflow use (search, fetch repo/file, etc.).

Input: action (Any) — dict with "action" key and action-specific params, e.g.:
  {"action": "github_search_repos", "q": "topic:workflow", "sort": "stars", "per_page": 10}
  {"action": "github_search_code", "q": "def run_workflow repo:owner/name"}
  {"action": "github_search_issues", "q": "repo:owner/name is:issue"}
  {"action": "github_get_repo", "owner": "owner", "repo": "repo"}
  {"action": "github_get_content", "owner": "owner", "repo": "repo", "path": "src/main.py", "ref": "main"}
  {"action": "github_get_readme", "owner": "owner", "repo": "repo", "ref": "main"}
  {"action": "github_list_releases", "owner": "owner", "repo": "repo", "per_page": 10}
  {"action": "github_list_commits", "owner": "owner", "repo": "repo", "path": "", "sha": "", "per_page": 10}

Output: data (Any) — structured response (list or dict); error (str) — message on failure.
Params: token (str, optional) — GitHub personal access token for higher rate limits and private repos.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from units.registry import UnitSpec, register_unit

GITHUB_GET_INPUT_PORTS = [("action", "Any")]
GITHUB_GET_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

_API_BASE = "https://api.github.com"


def _request(
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
) -> tuple[Any, str | None]:
    """Perform GitHub API request. Returns (data, error_message)."""
    url = f"{_API_BASE}{path}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ai-taskvector-GithubGET",
    }
    if token and str(token).strip():
        headers["Authorization"] = f"Bearer {str(token).strip()}"
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw else None, None)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            msg = json.loads(body).get("message", body)[:200]
        except Exception:
            msg = str(e)[:200]
        return (None, f"GitHub API {e.code}: {msg}")
    except Exception as e:
        return (None, str(e)[:200])


def _run_action(action: str, payload: dict[str, Any], token: str | None) -> tuple[Any, str | None]:
    """Dispatch to the right GitHub API and return (data, error)."""
    if action == "github_search_repos":
        q = payload.get("q") or payload.get("query") or ""
        if not q.strip():
            return (None, "github_search_repos: q (or query) required")
        params = {"q": q.strip(), "sort": (payload.get("sort") or "stars").strip(), "per_page": min(100, max(1, int(payload.get("per_page") or 10))), "page": max(1, int(payload.get("page") or 1))}
        return _request("/search/repositories?" + urllib.parse.urlencode(params), token=token)

    if action == "github_search_code":
        q = payload.get("q") or payload.get("query") or ""
        if not q.strip():
            return (None, "github_search_code: q (or query) required")
        params = {"q": q.strip(), "per_page": min(100, max(1, int(payload.get("per_page") or 10))), "page": max(1, int(payload.get("page") or 1))}
        return _request("/search/code?" + urllib.parse.urlencode(params), token=token)

    if action == "github_search_issues":
        q = payload.get("q") or payload.get("query") or ""
        if not q.strip():
            return (None, "github_search_issues: q (or query) required")
        params = {"q": q.strip(), "sort": (payload.get("sort") or "updated").strip(), "per_page": min(100, max(1, int(payload.get("per_page") or 10))), "page": max(1, int(payload.get("page") or 1))}
        return _request("/search/issues?" + urllib.parse.urlencode(params), token=token)

    owner = (payload.get("owner") or "").strip()
    repo = (payload.get("repo") or "").strip()
    if not owner or not repo:
        return (None, f"{action}: owner and repo required")

    if action == "github_get_repo":
        return _request(f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}", token=token)

    if action == "github_get_content":
        path = (payload.get("path") or "").strip()
        if not path:
            return (None, "github_get_content: path required")
        ref = (payload.get("ref") or "").strip()
        path_enc = "/".join(urllib.parse.quote(p) for p in path.split("/"))
        url = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/contents/{path_enc}"
        if ref:
            url += "?" + urllib.parse.urlencode({"ref": ref})
        return _request(url, token=token)

    if action == "github_get_readme":
        ref = (payload.get("ref") or "").strip()
        url = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/readme"
        if ref:
            url += "?" + urllib.parse.urlencode({"ref": ref})
        return _request(url, token=token)

    if action == "github_list_releases":
        per_page = min(100, max(1, int(payload.get("per_page") or 10)))
        return _request(f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/releases?per_page={per_page}", token=token)

    if action == "github_list_commits":
        per_page = min(100, max(1, int(payload.get("per_page") or 10)))
        path = (payload.get("path") or "").strip()
        sha = (payload.get("sha") or "").strip()
        params = {"per_page": per_page}
        if path:
            params["path"] = path
        if sha:
            params["sha"] = sha
        return _request(f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/commits?" + urllib.parse.urlencode(params), token=token)

    return (None, f"Unknown action: {action}")


def _github_get_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    action_in = inputs.get("action")
    if not isinstance(action_in, dict):
        return ({"data": None, "error": "GithubGET: action must be a dict"}, state)
    action_name = (action_in.get("action") or "").strip()
    if not action_name:
        return ({"data": None, "error": "GithubGET: action.action required"}, state)
    token = (params.get("token") or "").strip() or None
    data, err = _run_action(action_name, action_in, token)
    return ({"data": data, "error": err}, state)


def register_github_get() -> None:
    register_unit(UnitSpec(
        type_name="GithubGET",
        input_ports=GITHUB_GET_INPUT_PORTS,
        output_ports=GITHUB_GET_OUTPUT_PORTS,
        step_fn=_github_get_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="GitHub REST API GET: search repos/code/issues, get repo/file/readme, list releases/commits. Input: action dict (action + params). Params: token (optional). Output: data, error.",
    ))


__all__ = ["register_github_get", "GITHUB_GET_INPUT_PORTS", "GITHUB_GET_OUTPUT_PORTS"]
