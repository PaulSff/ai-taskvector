"""When auto-delegation is on, strip the manual ``delegate_request`` tool line from JSON prompt sections."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

from core.schemas.primitives import (
    JsonValue,
    WorkflowInputs,
    is_json_object_keyed_dict,
    is_string_keyed_dict,
)


def _strip_delegate_tool_lines(text: str) -> str:
    """Remove manual delegate_request action lines from prompt text."""
    lines = text.split("\n")
    kept: list[str] = []

    for line in lines:
        if line.strip().startswith("- delegate_request:"):
            continue
        kept.append(line)

    return "\n".join(kept)


def prompt_llm_params_strip_delegate_tool_line_if_auto_on(
    template_path: Path,
) -> dict[str, JsonValue] | None:
    """
    If auto delegation is enabled, return prompt_llm parameters with
    delegate_request lines removed from each section.

    Otherwise return None.
    """
    from gui.components.settings import get_auto_delegation_is_allowed

    if not get_auto_delegation_is_allowed():
        return None

    path = Path(template_path)

    if not path.is_file() or path.suffix.lower() != ".json":
        return None

    try:
        parsed = cast(
            JsonValue,
            json.loads(path.read_text(encoding="utf-8")),
        )
    except (OSError, json.JSONDecodeError):
        return None

    if not is_json_object_keyed_dict(parsed):
        return None

    sections_raw = parsed.get("sections")

    if not isinstance(sections_raw, list):
        return None

    sections = cast(list[JsonValue], sections_raw)

    format_keys_raw = parsed.get("format_keys")
    format_keys: list[JsonValue] = []

    if isinstance(format_keys_raw, list):
        for item in format_keys_raw:
            if isinstance(item, str):
                format_keys.append(item)

    new_sections: list[JsonValue] = []

    for section in sections:
        if not is_json_object_keyed_dict(section):
            new_sections.append(deepcopy(section))
            continue

        content = section.get("content")

        if not isinstance(content, str):
            new_sections.append(deepcopy(section))
            continue

        new_section = deepcopy(section)
        new_section["content"] = _strip_delegate_tool_lines(content)
        new_sections.append(new_section)

    result: dict[str, JsonValue] = {
        "sections": new_sections,
        "format_keys": format_keys,
    }

    return result


def merge_prompt_llm_strip_delegate_when_auto(
    overrides: WorkflowInputs,
    template_path: Path,
) -> None:
    """
    Mutate ``overrides`` in place by merging prompt_llm sections when
    auto-delegation hides the manual tool line.
    """
    extra = prompt_llm_params_strip_delegate_tool_line_if_auto_on(template_path)

    if not extra:
        return

    existing_prompt_llm = overrides.get("prompt_llm")

    prompt_llm: dict[str, JsonValue]

    if is_string_keyed_dict(existing_prompt_llm):
        prompt_llm = cast(
            dict[str, JsonValue],
            dict(existing_prompt_llm),
        )
    else:
        prompt_llm = {}

    prompt_llm.update(extra)
    overrides["prompt_llm"] = prompt_llm
