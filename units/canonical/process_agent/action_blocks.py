"""
Parse LLM output into generic action blocks (any dict with an "action" key).

**Content form:** The input is a single string — the raw LLM response. In the assistant
workflow this comes from the **LLMAgent** unit (output port `action` → ProcessAgent input
port `action`). The string may be plain text, markdown, and/or contain fenced ```json
blocks or inline { ... } JSON; this module extracts and parses those blocks.

Used by the ProcessAgent unit. Does not reference GraphEditAction or any domain-specific type;
downstream units (e.g. ApplyEdits) filter by their own action set.
Self-contained: JSON block extraction is in this module (no dependency on assistants).
"""
from __future__ import annotations

import json
import re
from typing import Any


def _remove_json_comments(s: str) -> str:
    """Strip // and # line comments, and /* */ block comments, only when outside double-quoted strings.
    Also removes trailing commas before ] or }. This allows LLM output with comments (e.g. in add_code_block blocks) to parse."""
    in_string = False
    escape = False
    i = 0
    n = len(s)
    out: list[str] = []
    while i < n:
        if escape:
            escape = False
            out.append(s[i])
            i += 1
            continue
        if in_string:
            if s[i] == "\\":
                escape = True
                out.append(s[i])
                i += 1
                continue
            if s[i] == '"':
                in_string = False
            out.append(s[i])
            i += 1
            continue
        # Not in string
        if s[i] == '"':
            in_string = True
            out.append(s[i])
            i += 1
            continue
        if s[i : i + 2] == "//":
            # Line comment: skip to end of line
            j = s.find("\n", i + 2)
            if j == -1:
                j = n
            i = j
            if i < n and s[i] == "\n":
                out.append(s[i])
                i += 1
            continue
        if s[i : i + 2] == "/*":
            # Block comment: skip to */
            j = s.find("*/", i + 2)
            if j == -1:
                j = n
            i = j + 2
            continue
        if s[i] == "#":
            # # line comment (e.g. shell-style)
            j = s.find("\n", i + 1)
            if j == -1:
                j = n
            i = j
            if i < n and s[i] == "\n":
                out.append(s[i])
                i += 1
            continue
        out.append(s[i])
        i += 1
    # Trailing commas before ] or }
    s2 = "".join(out)
    s2 = re.sub(r",\s*([}\]])", r"\1", s2)
    return s2


def strip_json_blocks(content: str) -> str:
    """Remove fenced JSON blocks from content. Used when preparing history for LLM context."""
    return re.sub(r"```(?:json)?[\s\S]*?```", "", content).strip()


def _parse_json_blocks(content: str) -> list[Any] | dict[str, str]:
    """
    Extract and parse JSON blocks from LLM content.
    Prefers fenced ```json blocks; falls back to inline {...} scanning.
    Returns list of parsed objects, or {parse_error: str} if fenced blocks were present but all failed.
    """
    content = content.strip()
    results: list[Any] = []
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)
    fenced_parse_attempted = False
    for block in fenced:
        fenced_parse_attempted = True
        try:
            clean = _remove_json_comments(block.strip())
            obj = json.loads(clean)
            results.append(obj)
        except json.JSONDecodeError:
            continue
    if fenced_parse_attempted and not results:
        return {"parse_error": "Invalid JSON: syntax error or comments detected in fenced block"}
    if results:
        return results
    # Fallback: scan for inline JSON blocks
    i, n = 0, len(content)
    while i < n:
        if content[i] == "{":
            depth = 0
            for j in range(i, n):
                if content[j] == "{":
                    depth += 1
                elif content[j] == "}":
                    depth -= 1
                    if depth == 0:
                        raw = content[i : j + 1]
                        try:
                            clean = _remove_json_comments(raw)
                            obj = json.loads(clean)
                            results.append(obj)
                            i = j + 1
                            break
                        except json.JSONDecodeError:
                            i = j + 1
                            break
            else:
                i += 1
        else:
            i += 1
    return results


def parse_action_blocks(content: str) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Parse LLM content into a generic list of action blocks (any dict with an "action" key).
    Same syntax can be used for graph edits, config edits, or other domains; this function
    does not reference GraphEditAction. Downstream units decide which actions they consume.
    Returns:
      - list of action dicts (each has "action": str and optional payload),
      - or dict with "edits" (list) plus optional "read_file", "rag_search", "read_code_block_ids", "read_current_workflow",
        "report", "web_search", "browse_url", "github", "formulas_calc", "delegate_request",
      - or {parse_error: str} if fenced JSON was present but all blocks failed.
    """
    parsed = _parse_json_blocks(content)
    if isinstance(parsed, dict):
        return parsed
    return _parsed_blocks_to_action_blocks(parsed)


def _parsed_blocks_to_action_blocks(parsed_blocks: list[Any]) -> list[dict[str, Any]] | dict[str, Any]:
    """Convert parsed JSON blocks to flat list of action dicts; extract side-channel actions into separate keys."""
    edits: list[dict[str, Any]] = []
    read_file_paths: list[str] = []
    rag_search_query: str | None = None
    rag_search_max_results: int | None = None
    rag_search_max_chars: int | None = None
    rag_search_snippet_max: int | None = None
    read_code_block_ids: list[str] = []
    web_search_query: str | None = None
    web_search_max_results: int | None = None
    browse_url: str | None = None
    github_obj: dict[str, Any] | None = None
    report_obj: dict[str, Any] | None = None
    run_workflow_obj: dict[str, Any] | None = None
    grep_obj: dict[str, Any] | None = None
    formulas_calc_obj: dict[str, Any] | None = None
    delegate_request_obj: dict[str, Any] | None = None
    read_current_workflow_requested = False

    def collect_one(obj: dict[str, Any]) -> None:
        nonlocal rag_search_query, rag_search_max_results, rag_search_max_chars, rag_search_snippet_max, read_code_block_ids
        nonlocal web_search_query, web_search_max_results, browse_url, github_obj
        nonlocal report_obj, run_workflow_obj, grep_obj, formulas_calc_obj, delegate_request_obj, read_current_workflow_requested
        if obj.get("action") == "read_file":
            path = obj.get("path")
            if isinstance(path, str) and path.strip():
                read_file_paths.append(path.strip())
            return
        if obj.get("action") == "search":
            q = obj.get("what") or obj.get("query") or obj.get("q")
            if isinstance(q, str) and q.strip():
                rag_search_query = q.strip()
            mr = obj.get("max_results")
            if mr is not None:
                try:
                    n = int(mr)
                    if n >= 1:
                        rag_search_max_results = min(50, n)
                except (TypeError, ValueError):
                    pass
            mc = obj.get("max_chars")
            if mc is not None:
                try:
                    n = int(mc)
                    if n >= 1:
                        rag_search_max_chars = min(5000, n)
                except (TypeError, ValueError):
                    pass
            sm = obj.get("snippet_max")
            if sm is not None:
                try:
                    n = int(sm)
                    if n >= 1:
                        rag_search_snippet_max = min(2000, n)
                except (TypeError, ValueError):
                    pass
            return
        if obj.get("action") == "read_code_block":
            bid = obj.get("id")
            if isinstance(bid, str) and bid.strip():
                read_code_block_ids.append(bid.strip())
            elif isinstance(bid, list):
                for x in bid:
                    if isinstance(x, str) and x.strip():
                        read_code_block_ids.append(x.strip())
            return
        if obj.get("action") == "read_current_workflow":
            read_current_workflow_requested = True
            return
        if obj.get("action") == "web_search":
            q = obj.get("query") or obj.get("q")
            if isinstance(q, str) and q.strip():
                web_search_query = q.strip()
            mr = obj.get("max_results")
            if mr is not None:
                try:
                    n = int(mr)
                    if n >= 1:
                        web_search_max_results = min(20, n)
                except (TypeError, ValueError):
                    pass
            return
        if obj.get("action") == "browse":
            u = obj.get("url") or obj.get("URL")
            if isinstance(u, str) and u.strip():
                browse_url = u.strip()
            return
        if obj.get("action") == "github":
            payload = obj.get("payload")
            if isinstance(payload, dict) and payload.get("action"):
                github_obj = payload
            return
        if obj.get("action") == "report":
            # Full payload: path (optional), output_format, report (JSON body from LLM). No prompt.
            report_obj = obj
            return
        if obj.get("action") == "run_workflow":
            # Optional path to workflow JSON; if missing, use current graph from input
            run_workflow_obj = {"action": "run_workflow", "path": obj.get("path") if isinstance(obj.get("path"), str) else None}
            return
        if obj.get("action") == "grep":
            # pattern/command = what to search for; source = path (file) or raw text (e.g. from Debug). Omit source to use unit input.
            pat = obj.get("pattern") or obj.get("command") or obj.get("regex")
            src = obj.get("source")
            if isinstance(pat, str) and pat.strip():
                grep_obj = {"action": "grep", "pattern": pat.strip(), "source": src if isinstance(src, str) else None}
            return
        if obj.get("action") == "formulas_calc":
            formulas_calc_obj = dict(obj)
            return
        if obj.get("action") == "delegate_request":
            delegate_request_obj = dict(obj)
            return
        if obj.get("action"):
            edits.append(obj)  # any action; no filter by type here
        elif isinstance(obj.get("edits"), list):
            for e in obj["edits"]:
                if isinstance(e, dict):
                    collect_one(e)

    for parsed in parsed_blocks:
        if isinstance(parsed, list):
            for e in parsed:
                if isinstance(e, dict):
                    collect_one(e)
        elif isinstance(parsed, dict):
            collect_one(parsed)

    if (
        read_file_paths
        or rag_search_query
        or read_code_block_ids
        or read_current_workflow_requested
        or web_search_query
        or browse_url
        or github_obj is not None
        or report_obj is not None
        or run_workflow_obj is not None
        or grep_obj is not None
        or formulas_calc_obj is not None
        or delegate_request_obj is not None
    ):
        out: dict[str, Any] = {"edits": edits}
        if read_file_paths:
            out["read_file"] = list(dict.fromkeys(read_file_paths))
        if rag_search_query:
            out["rag_search"] = rag_search_query
            if rag_search_max_results is not None:
                out["rag_search_max_results"] = rag_search_max_results
            if rag_search_max_chars is not None:
                out["rag_search_max_chars"] = rag_search_max_chars
            if rag_search_snippet_max is not None:
                out["rag_search_snippet_max"] = rag_search_snippet_max
        if read_code_block_ids:
            out["read_code_block_ids"] = list(dict.fromkeys(read_code_block_ids))
        if read_current_workflow_requested:
            out["read_current_workflow"] = True
        if web_search_query:
            out["web_search"] = web_search_query
            if web_search_max_results is not None:
                out["web_search_max_results"] = web_search_max_results
        if browse_url:
            out["browse_url"] = browse_url
        if github_obj is not None:
            out["github"] = github_obj
        if report_obj is not None:
            out["report"] = report_obj
        if run_workflow_obj is not None:
            out["run_workflow"] = run_workflow_obj
        if grep_obj is not None:
            out["grep"] = grep_obj
        if formulas_calc_obj is not None:
            out["formulas_calc"] = formulas_calc_obj
        if delegate_request_obj is not None:
            out["delegate_request"] = delegate_request_obj
        return out
    return edits


def parse_workflow_edits(content: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Alias for parse_action_blocks (backward compat). Same syntax; graph-edits consumer filters by GraphEditAction."""
    return parse_action_blocks(content)
