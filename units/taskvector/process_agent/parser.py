from __future__ import annotations

import json
import re

from core.schemas.primitives import (
    JsonValue,
    is_json_object,
    is_json_value,
)

# the same as in GUI message renderer
_CLOSE_FENCE_LINE = re.compile(r"(?m)^```\s*$")


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


def _is_action_oriented(obj: JsonValue) -> bool:
    """Check if the parsed JSON object is a dict with 'action' or 'edits', or a list containing such a dict."""
    if is_json_object(obj):
        return "action" in obj or "edits" in obj

    if isinstance(obj, list):
        return any(
            is_json_object(item)
            and ("action" in item or "edits" in item)
            for item in obj
        )

    return False

def parse_json_blocks(content: str) -> list[JsonValue] | str:
    """
    Extract and parse JSON blocks from LLM content.
    Prefers fenced ```json blocks; falls back to inline {...} scanning.
    Fenced extraction is JSON-aware to ignore ``` sequences that appear inside JSON payloads/strings.
    Returns list of parsed objects, or {parse_error: str} if fenced blocks were present but all failed.
    """
    content = content.strip()
    results: list[JsonValue] = []

    # --- Fenced JSON extraction (JSON-aware closing fence) ---
    open_re = re.compile(r"(?m)^```(?:json)?[ \t]*\n")
    close_re = _CLOSE_FENCE_LINE  # (?m)^```\s*$

    fenced_blocks: list[str] = []
    pos = 0
    while True:
        m_open = open_re.search(content, pos)
        if not m_open:
            break

        body_start = m_open.end()
        j = body_start

        json_depth = 0
        in_string = False
        escape = False

        while j < len(content):
            if content.startswith("```", j):
                m_close = close_re.match(content, j)
                if m_close and json_depth == 0 and not in_string:
                    fenced_blocks.append(content[body_start:j])
                    pos = m_close.end()
                    break

            ch = content[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch in "{[":
                    json_depth += 1
                elif ch in "}]" and json_depth > 0:
                    json_depth -= 1
            j += 1
        else:
            break

    fenced_parse_attempted = len(fenced_blocks) > 0
    for block in fenced_blocks:
        try:
            clean = _remove_json_comments(block.strip())

            raw_obj: object = json.loads(clean)
            if not is_json_value(raw_obj):
                continue

            obj = raw_obj


            if _is_action_oriented(obj):
                results.append(obj)
        except json.JSONDecodeError:
            continue

    if fenced_parse_attempted and not results:
        return "Invalid JSON: syntax error or comments detected in fenced block"

    if results:
        return results

    # --- Fallback: scan for inline JSON blocks ---
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
                            if _is_action_oriented(obj):
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
