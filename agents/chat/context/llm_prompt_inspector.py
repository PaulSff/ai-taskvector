"""
Dev inspector: extract system_prompt / user_message from role chat workflow outputs.

Role workflows conventionally use a ``Prompt`` unit (often id ``prompt_llm``) before ``LLMAgent``.
``attach_llm_prompt_debug_from_outputs`` copies those strings onto the response dict the GUI consumes;
``record_llm_prompt_view_if_present`` forwards them to the dev tab hook when present.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

# Common Prompt unit ids in agents/roles/*/…_workflow.json graphs.
_DEFAULT_PROMPT_UNIT_IDS: tuple[str, ...] = ("prompt_llm", "prompt")


def attach_llm_prompt_debug_from_outputs(
    outputs: dict[str, object],
    data: dict[str, object],
    *,
    prompt_unit_ids: tuple[str, ...] = _DEFAULT_PROMPT_UNIT_IDS,
) -> None:
    """Merge Prompt unit outputs into ``data`` as
    ``llm_system_prompt`` / ``llm_user_message``.
    """
    for uid in prompt_unit_ids:
        pl = outputs.get(uid)

        if not isinstance(pl, dict):
            continue

        prompt_output = cast(dict[str, object], pl)

        sp = prompt_output.get("system_prompt")
        um = prompt_output.get("user_message")

        if isinstance(sp, str):
            data["llm_system_prompt"] = sp

        if isinstance(um, str):
            data["llm_user_message"] = um

        if isinstance(sp, str) or isinstance(um, str):
            return

def record_llm_prompt_view_if_present(
    response: dict[str, object],
    hook: Callable[[dict[str, object]], None] | None,
) -> None:
    """Invoke ``hook(response)`` when response includes dev LLM prompt fields."""
    if hook is None:
        return

    if (
        "llm_system_prompt" not in response
        and "llm_user_message" not in response
    ):
        return

    hook(response)
