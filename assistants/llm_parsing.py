"""
Shared LLM output parsing: extract JSON blocks from model responses.

Used by Workflow Designer and RL Coach (and any assistant that emits fenced/inline JSON).
"""
import json
import re
from typing import Any


def remove_json_comments(s: str) -> str:
    """Strip // comments and trailing commas for lenient JSON parsing."""
    s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def strip_json_blocks(content: str) -> str:
    """Remove fenced JSON blocks from content. Used when preparing history for LLM context."""
    return re.sub(r"```(?:json)?[\s\S]*?```", "", content).strip()


def parse_json_blocks(content: str) -> list[Any] | dict[str, str]:
    """
    Extract and parse JSON blocks from LLM content.
    Prefers fenced ```json blocks; falls back to inline {...} scanning.

    Returns:
        list of parsed objects, or
        {parse_error: str} if fenced blocks were present but ALL failed to parse
    """
    content = content.strip()
    results: list[Any] = []
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)

    fenced_parse_attempted = False

    for block in fenced:
        fenced_parse_attempted = True
        try:
            clean = remove_json_comments(block.strip())
            obj = json.loads(clean)
            results.append(obj)
        except json.JSONDecodeError:
            continue

    if fenced_parse_attempted and not results:
        return {"parse_error": "Invalid JSON: syntax error or comments detected in fenced block"}

    if results:
        return results

    # Fallback: scan for inline JSON blocks
    i = 0
    n = len(content)
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
                            clean = remove_json_comments(raw)
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
