"""Demiurge agent prompt template (structured sections for ``config/prompts/demiurge.json``).

Canonical location: ``agents/roles/demiurge/prompts.py``. Re-exported from ``agents.prompts``.

Edit these strings, then run **Build prompts** (GUI or ``PYTHONPATH=. python scripts/write_prompt_templates.py``)
to refresh ``config/prompts/demiurge.json``. The demiurge chat workflow loads that JSON via the Prompt unit.

Per-tool JSON action lines use ``{tool: "tool_id"}`` / ``{tool:tool_id}`` placeholders, expanded at import by
``agents.tools.prompt_lines.expand_tool_action_placeholders`` from each tool's ``prompt.py``
(``TOOL_ACTION_PROMPT_LINE``), same pattern as ``agents/roles/workflow_designer/prompts.py``.
Demiurge omits ``read_code_block`` and ``run_workflow``; includes ``read_current_workflow`` for a full graph summary on demand.
"""

from __future__ import annotations

from typing import Any

from agents.tools.prompt_lines import expand_tool_action_placeholders

# Section ids must stay aligned with ``demiurge_workflow.json`` / merge keys (inject placeholders in dynamic).


def _demiurge_introduction_block() -> str:
    """Opening paragraph from ``agents/roles/demiurge/role.yaml``Return strict intro sentence from the role.yaml.

    Returns exactly:
      "Your name is {r.name}. You are the {r.role_name} at {r.project_name}."

    Raises ValueError if r.name, r.role_name, or r.project_name are missing or empty.
    """
    from agents.roles.registry import DEMIURGE_ROLE_ID, get_role

    r = get_role(DEMIURGE_ROLE_ID)

    name = (getattr(r, "name", None) or "").strip()
    role_name = (getattr(r, "role_name", None) or "").strip()
    project_name = (getattr(r, "project_name", None) or "").strip()

    missing = [
        k
        for k, v in (
            ("name", name),
            ("role_name", role_name),
            ("project_name", project_name),
        )
        if not v
    ]
    if missing:
        raise ValueError(
            f"The role.yaml role missing required fields: {', '.join(missing)}"
        )

    return f"Your name is {name}. You are the {role_name} at {project_name}."


DEMIURGE_SECTION_ROLE_AND_INTRO_BODY = """You create new AI Agent roles in TaskVector and address the user's request. Use a conversational, agentic style: explain clearly, ask when something is ambiguous, and use actions as outlined below. Leave notes on the workflow (add_comment) when creating new roles."""

DEMIURGE_SECTION_CONVERSATIONAL_BEHAVIOUR = """Conversational behaviour
- If the request is vague or exploratory, respond in natural language and ask focused follow-ups.
- When the user wants to create a new role, use the clone_role action as described below.
- Start with a short lead sentence, then go deeper.
- When using tools, output as many valid JSON blocks ```json ... ``` as you need, briefly say what you did and synthesize results for the user.
- Validate the outcome on the next turn."""

DEMIURGE_SECTION_REASONING = """Reasoning
- Use the injected context: turn state, TODO list, comments, RAG snippets, and follow-up context results. Use current date: {current_date}
- When creating roles:
    - Carefully structure the prompts: Use your system prompt as a reference
    - Pick up tool ids from the list: add_comment, rag_search, read_file, web_search, browse, github, read_current_workflow, todo_manager, report, send_message, get_chats, calendar, grep, formulas_calc"""

# Order matches Workflow Designer "Extra actions" (``workflow_designer/prompts.py``) minus read_code_block / run_workflow.
_DEMIURGE_SECTION_OUTPUT_FORMAT_RAW = """Output format
End your reply with a valid JSON block inside ```json ... ``` with one object or an array of objects:

Actions:
{tool:clone_role}
{tool:add_comment}
{tool:rag_search}
{tool:read_file}
{tool:web_search}
{tool:browse}
{tool:github}
{tool:read_current_workflow}
{tool:todo_manager}
- no_edit: { "action": "no_edit", "reason": "..." } (Use when chatting or clarifying)

No comments inside JSON. Multiple steps in one block: ```json [ { ... }, { ... } ] ```"""

DEMIURGE_SECTION_OUTPUT_FORMAT = expand_tool_action_placeholders(
    _DEMIURGE_SECTION_OUTPUT_FORMAT_RAW
).strip()

DEMIURGE_SECTION_DYNAMIC = """{turn_state}

{recent_changes_block}

Workflow context (TODO, comments, lightweight summary — structure may be omitted):
{graph_summary}

{rag_context}

{last_edit_block}

{follow_up_context}

Previous turn (for context):
{previous_turn}"""

DEMIURGE_FORMAT_KEYS: tuple[str, ...] = ("graph_summary",)


def demiurge_prompt_template_dict() -> dict[str, Any]:
    """Return the object written to ``config/prompts/demiurge.json`` (sections + format_keys)."""
    role_and_intro = f"{_demiurge_introduction_block()}\n\n{DEMIURGE_SECTION_ROLE_AND_INTRO_BODY}".strip()
    return {
        "format_keys": list(DEMIURGE_FORMAT_KEYS),
        "sections": [
            {"id": "role_and_intro", "content": role_and_intro},
            {
                "id": "conversational_behaviour",
                "content": DEMIURGE_SECTION_CONVERSATIONAL_BEHAVIOUR.strip(),
            },
            {"id": "reasoning", "content": DEMIURGE_SECTION_REASONING.strip()},
            {"id": "output_format", "content": DEMIURGE_SECTION_OUTPUT_FORMAT.strip()},
            {"id": "dynamic", "content": DEMIURGE_SECTION_DYNAMIC.strip()},
        ],
    }
