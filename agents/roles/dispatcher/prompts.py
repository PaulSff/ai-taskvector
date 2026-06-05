"""Dispatcher agent prompt template (structured sections for ``config/prompts/dispatcher.json``).

Canonical location: ``agents/roles/dispatcher/prompts.py``. Re-exported from ``agents.prompts``.

Edit these strings, then run **Build prompts** (GUI or ``PYTHONPATH=. python scripts/write_prompt_templates.py``)
to refresh ``config/prompts/dispatcher.json``. The dispatcher workflow loads that JSON via the Prompt unit.

The ``{roles}`` placeholder in the reasoning section is resolved at build time from the role registry
(``list_chat_dropdown_role_ids()`` minus the dispatcher itself). The ``{language}`` placeholder in the
output format is a runtime substitution filled by the Prompt unit from the ``merge_llm`` aggregate output.
"""

from __future__ import annotations

from typing import Any

from agents.tools.prompt_lines import expand_tool_action_placeholders

DISPATCHER_SECTION_ROLE_AND_INTRO_BODY = """You are the dispatcher."""

DISPATCHER_SECTION_REASONING = """You analyze the user's message and pick up the most suitable role from the list to hand over the current request. The roles are:
{roles}

IMPORTANT: If the user's request is not suitable for any of those roles or vague, doesn't contain any specific request/task to do, you just SKIP silently."""

_DISPATCHER_SECTION_OUTPUT_FORMAT_RAW = """Output format (lower-case only):
{tool:delegate_request}

 If skipping, output nothing at all."""

DISPATCHER_SECTION_OUTPUT_FORMAT = expand_tool_action_placeholders(
    _DISPATCHER_SECTION_OUTPUT_FORMAT_RAW
).strip()


def _dispatcher_roles_list() -> str:
    """Build numbered list of delegatable roles from registry for the dispatcher reasoning section.

    Roles are drawn from ``list_chat_dropdown_role_ids()`` (all chat-enabled roles) minus the
    dispatcher itself. Each entry uses the role's ``responsibility_description`` as the description.
    Resolved at build time so the emitted JSON has the actual names embedded.
    """
    from agents.roles.registry import (  # noqa: PLC0415
        DISPATCHER_ROLE_ID,
        get_role,
        list_chat_dropdown_role_ids,
    )

    def _first_sentence(text: str) -> str:
        """Return text up to and including the first sentence-ending period (split on '. ')."""
        idx = text.find(". ")
        return text[: idx + 1].strip() if idx >= 0 else text.strip()

    lines: list[str] = []
    for rid in list_chat_dropdown_role_ids():
        if rid == DISPATCHER_ROLE_ID:
            continue
        try:
            r = get_role(rid)
            desc = _first_sentence(r.responsibility_description or rid)
            lines.append(f"{rid} - {desc}")
        except Exception:
            lines.append(rid)
    return "\n".join(lines)


def dispatcher_prompt_template_dict() -> dict[str, Any]:
    """Return the object written to ``config/prompts/dispatcher.json`` (sections + format_keys).

    ``format_keys`` contains ``language`` so the Prompt unit substitutes ``{language}`` in the
    output_format section at runtime from the ``merge_llm`` aggregate data.
    """
    roles_str = _dispatcher_roles_list()
    reasoning = DISPATCHER_SECTION_REASONING.format(roles=roles_str)
    return {
        "format_keys": ["language"],
        "sections": [
            {
                "id": "role_and_intro",
                "content": DISPATCHER_SECTION_ROLE_AND_INTRO_BODY.strip(),
            },
            {"id": "reasoning", "content": reasoning.strip()},
            {"id": "output_format", "content": DISPATCHER_SECTION_OUTPUT_FORMAT},
        ],
    }
