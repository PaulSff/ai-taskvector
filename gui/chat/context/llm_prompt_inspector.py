"""
Dev inspector: extract system_prompt / user_message from role chat workflow outputs.

Role workflows conventionally use a ``Prompt`` unit (often id ``prompt_llm``) before ``LLMAgent``.
``attach_llm_prompt_debug_from_outputs`` copies those strings onto the response dict the GUI consumes;
``record_llm_prompt_view_if_present`` forwards them to the dev tab hook when present.
"""

from __future__ import annotations

from typing import Any, Callable

# Common Prompt unit ids in assistants/roles/*/…_workflow.json graphs.
_DEFAULT_PROMPT_UNIT_IDS: tuple[str, ...] = ("prompt_llm", "prompt")


def attach_llm_prompt_debug_from_outputs(
    outputs: dict[str, Any],
    data: dict[str, Any],
    *,
    prompt_unit_ids: tuple[str, ...] = _DEFAULT_PROMPT_UNIT_IDS,
) -> None:
    """Merge Prompt unit outputs into ``data`` as ``llm_system_prompt`` / ``llm_user_message``."""
    if not isinstance(outputs, dict) or not isinstance(data, dict):
        return
    for uid in prompt_unit_ids:
        pl = outputs.get(uid)
        if not isinstance(pl, dict):
            continue
        sp = pl.get("system_prompt")
        um = pl.get("user_message")
        if isinstance(sp, str):
            data["llm_system_prompt"] = sp
        if isinstance(um, str):
            data["llm_user_message"] = um
        if isinstance(sp, str) or isinstance(um, str):
            return


def record_llm_prompt_view_if_present(
    response: dict[str, Any],
    hook: Callable[[dict[str, Any]], None] | None,
) -> None:
    """Invoke ``hook(response)`` when response includes dev LLM prompt fields."""
    if hook is None or not isinstance(response, dict):
        return
    if "llm_system_prompt" not in response and "llm_user_message" not in response:
        return
    hook(response)
