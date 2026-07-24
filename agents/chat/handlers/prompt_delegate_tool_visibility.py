"""When auto-delegation is on, strip the manual ``delegate_request`` tool line from JSON prompt sections."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def _strip_delegate_tool_lines(text: str) -> str:
    """Remove lines that document the manual delegate_request JSON action (built prompts use ``- delegate_request:``)."""
    lines = text.split("\n")
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- delegate_request:"):
            continue
        kept.append(line)
    return "\n".join(kept)


def prompt_llm_params_strip_delegate_tool_line_if_auto_on(template_path: Path) -> dict[str, Any] | None:
    """
    If ``auto_delegation_is_allowed`` is True, return ``prompt_llm`` params with ``sections`` (and ``format_keys``)
    read from the JSON template with delegate_request lines removed from each section. Otherwise return None
    (keep ``template_path``-only loading).
    """
    from gui.components.settings import get_auto_delegation_is_allowed

    if not get_auto_delegation_is_allowed():
        return None
    path = Path(template_path)
    if not path.is_file() or path.suffix.lower() != ".json":
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sections = obj.get("sections")
    if not isinstance(sections, list):
        return None
    fk = obj.get("format_keys") or []
    format_keys = [str(k) for k in fk] if isinstance(fk, list) else []
    new_sections: list[Any] = []
    for s in sections:
        if isinstance(s, dict):
            c = s.get("content")
            if isinstance(c, str):
                ns = deepcopy(s)
                ns["content"] = _strip_delegate_tool_lines(c)
                new_sections.append(ns)
            else:
                new_sections.append(deepcopy(s))
        else:
            new_sections.append(deepcopy(s))
    return {"sections": new_sections, "format_keys": format_keys}


def merge_prompt_llm_strip_delegate_when_auto(overrides: dict[str, Any], template_path: Path) -> None:
    """Mutate ``overrides`` in place: merge ``prompt_llm`` sections when auto-delegation hides the manual tool line."""
    extra = prompt_llm_params_strip_delegate_tool_line_if_auto_on(template_path)
    if not extra:
        return
    pl = dict(overrides.get("prompt_llm") or {})
    pl.update(extra)
    overrides["prompt_llm"] = pl
