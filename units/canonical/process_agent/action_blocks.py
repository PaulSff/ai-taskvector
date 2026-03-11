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
    """Strip // comments and trailing commas for lenient JSON parsing."""
    s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


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
      - or dict with "edits" (list) plus optional "request_file_content", "rag_search", "read_code_block_ids", "create_file_on_rag", "web_search", "browse_url",
      - or {parse_error: str} if fenced JSON was present but all blocks failed.
    """
    parsed = _parse_json_blocks(content)
    if isinstance(parsed, dict):
        return parsed
    return _parsed_blocks_to_action_blocks(parsed)


def _parsed_blocks_to_action_blocks(parsed_blocks: list[Any]) -> list[dict[str, Any]] | dict[str, Any]:
    """Convert parsed JSON blocks to flat list of action dicts; extract side-channel actions into separate keys."""
    edits: list[dict[str, Any]] = []
    request_file_content_paths: list[str] = []
    rag_search_query: str | None = None
    rag_search_max_results: int | None = None
    read_code_block_ids: list[str] = []
    web_search_query: str | None = None
    web_search_max_results: int | None = None
    browse_url: str | None = None
    create_file_on_rag_obj: dict[str, Any] | None = None

    def collect_one(obj: dict[str, Any]) -> None:
        nonlocal rag_search_query, rag_search_max_results, read_code_block_ids
        nonlocal web_search_query, web_search_max_results, browse_url
        nonlocal create_file_on_rag_obj
        if obj.get("action") == "request_file_content":
            path = obj.get("path")
            if isinstance(path, str) and path.strip():
                request_file_content_paths.append(path.strip())
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
        if obj.get("action") == "create_file_on_rag":
            # Full payload: path, prompt, output_format, report (JSON body from LLM)
            create_file_on_rag_obj = obj
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
        request_file_content_paths
        or rag_search_query
        or read_code_block_ids
        or web_search_query
        or browse_url
        or create_file_on_rag_obj is not None
    ):
        out: dict[str, Any] = {"edits": edits}
        if request_file_content_paths:
            out["request_file_content"] = list(dict.fromkeys(request_file_content_paths))
        if rag_search_query:
            out["rag_search"] = rag_search_query
            if rag_search_max_results is not None:
                out["rag_search_max_results"] = rag_search_max_results
        if read_code_block_ids:
            out["read_code_block_ids"] = list(dict.fromkeys(read_code_block_ids))
        if web_search_query:
            out["web_search"] = web_search_query
            if web_search_max_results is not None:
                out["web_search_max_results"] = web_search_max_results
        if browse_url:
            out["browse_url"] = browse_url
        if create_file_on_rag_obj is not None:
            out["create_file_on_rag"] = create_file_on_rag_obj
        return out
    return edits


def parse_workflow_edits(content: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Alias for parse_action_blocks (backward compat). Same syntax; graph-edits consumer filters by GraphEditAction."""
    return parse_action_blocks(content)
