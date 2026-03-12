"""
Prompt canonical unit: merged context (data) + template → system_prompt string.

Generic: no hardcoded data keys or prompt names. Template (inline or from file) defines
placeholders {key}; each is replaced from data[key]. Use by any LLM agent. Pipeline: Merge → Prompt → LLMAgent → Switch.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

PROMPT_INPUT_PORTS = [("data", "Any")]
PROMPT_OUTPUT_PORTS = [("system_prompt", "str"), ("user_message", "str")]

# Placeholder pattern: {identifier} (word chars only)
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _section_content(item: Any) -> str:
    """Extract content from a section: string or dict with 'content' key."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and "content" in item:
        c = item["content"]
        return c if isinstance(c, str) else ""
    return ""


def _template_from_sections(sections: list[Any], join_with: str = "\n\n") -> str:
    """Build a single template string from a list of sections (strings or {content: string})."""
    parts = [_section_content(s).strip() for s in sections if _section_content(s).strip()]
    return join_with.join(parts)


def _load_template(params: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (template_string, format_keys). Template from params['template'], params['sections'], or params['template_path'] (file)."""
    format_keys = params.get("format_keys")
    if isinstance(format_keys, list):
        format_keys = [str(k) for k in format_keys]
    else:
        format_keys = []

    template = params.get("template")
    if isinstance(template, str) and template.strip():
        return template.strip(), format_keys

    sections = params.get("sections")
    if isinstance(sections, list) and sections:
        return _template_from_sections(sections), format_keys

    path = params.get("template_path")
    if not path:
        return "", format_keys
    path = Path(path)
    if not path.exists():
        return "", format_keys
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "", format_keys
    if path.suffix.lower() != ".json":
        return text, format_keys
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return "", format_keys
    if not isinstance(obj, dict):
        return "", format_keys
    format_keys = obj.get("format_keys") or []
    if isinstance(format_keys, list):
        format_keys = [str(k) for k in format_keys]
    else:
        format_keys = []
    # Structured: sections array (join into one template, then substitute)
    sections = obj.get("sections")
    if isinstance(sections, list) and sections:
        return _template_from_sections(sections), format_keys
    # Legacy: single template string
    template = obj.get("template") or ""
    return (template if isinstance(template, str) else ""), format_keys


def _substitute(template: str, data: dict[str, Any], format_keys: list[str]) -> str:
    """Replace every {key} in template with data[key]. Keys in format_keys are json.dumps'd (dict/list)."""
    if not template:
        return ""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        val = data.get(key)
        if key in format_keys and val is not None:
            if isinstance(val, (dict, list)):
                return json.dumps(val, indent=2)
            return str(val)
        if val is None:
            return ""
        return str(val)

    return _PLACEHOLDER_RE.sub(repl, template)


def _prompt_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = inputs.get("data")
    if not isinstance(data, dict):
        data = {}
    params = params or {}
    template, format_keys = _load_template(params)
    try:
        system_prompt = _substitute(template, data, format_keys)
    except Exception:
        system_prompt = ""
    raw = data.get("user_message", "")
    user_message = raw if isinstance(raw, str) else str(raw or "")
    if not user_message.strip():
        user_message = "(No message provided.)"
    return ({"system_prompt": system_prompt, "user_message": user_message}, state)


def register_prompt() -> None:
    register_unit(UnitSpec(
        type_name="Prompt",
        input_ports=PROMPT_INPUT_PORTS,
        output_ports=PROMPT_OUTPUT_PORTS,
        step_fn=_prompt_step,
        role=None,
        description="Assembles system prompt from template + merged context (data). Template has placeholders {key} filled from data. Params: template (string), or template_path (.txt or .json); JSON may use 'template' (single string) or 'sections' (array of strings or {content: string}); optional format_keys (json.dumps those keys). Use by any LLM agent.",
    ))


__all__ = ["register_prompt", "PROMPT_INPUT_PORTS", "PROMPT_OUTPUT_PORTS"]
