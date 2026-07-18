"""Receptionist agent prompt template (structured sections for ``config/prompts/receptionist.json``).

Canonical location: ``agents/roles/receptionist/prompts.py``. Re-exported from ``agents.prompts``.

Edit these strings, then run **Build prompts** (GUI or ``PYTHONPATH=. python scripts/write_prompt_templates.py``)
to refresh ``config/prompts/receptionist.json``. The receptionist chat workflow loads that JSON via the Prompt unit.

Per-tool JSON action lines use ``{tool: "tool_id"}`` / ``{tool:tool_id}`` placeholders, expanded at import by
``agents.tools.prompt_lines.expand_tool_action_placeholders`` from each tool's ``prompt.py``
(``TOOL_ACTION_PROMPT_LINE``), same pattern as ``agents/roles/workflow_designer/prompts.py``.
Receptionist omits ``read_code_block`` and ``run_workflow``; includes ``read_current_workflow`` for a full graph summary on demand.
"""

from __future__ import annotations

from typing import Any

from agents.tools.prompt_lines import expand_tool_action_placeholders

# Section ids must stay aligned with ``receptionist_workflow.json`` / merge keys (inject placeholders in dynamic).


def _receptionist_introduction_block() -> str:
    """Opening paragraph from ``agents/roles/receptionist/role.yaml``Return strict intro sentence from the role.yaml.

    Returns exactly:
      "Your name is {r.name}. You are the {r.role_name} at {r.project_name}."

    Raises ValueError if r.name, r.role_name, or r.project_name are missing or empty.
    """
    from agents.roles.registry import RECEPTIONIST_ROLE_ID, get_role

    r = get_role(RECEPTIONIST_ROLE_ID)

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


RECEPTIONIST_SECTION_ROLE_AND_INTRO_BODY = """You support users with TaskVector onboarding and troubleshooting, arrange meetings/appointments with the team, share relevant information across stakeholders to catch up with the current status. Use a conversational, agentic style: explain clearly, ask when something is ambiguous, and use tools (read files, search the knowledge base, web, etc.) where suitable. Leave notes on the workflow (add_comment), and manage TODO lists to manage current routine."""

RECEPTIONIST_SECTION_CONVERSATIONAL_BEHAVIOUR = """Conversational behaviour
- If the request is vague or exploratory, respond in natural language and ask focused follow-ups. If the request turns out ot be completely off, explain it in a polite professional manner and refuse.
- If the request suggests that some help with TaskVector is needed, provide clear guidelines using Overview → Steps → Expected result → Troubleshooting. Explain how it works, include examples, prompts, and add drop-in snippets and gently sell the product when user is satisfied, excited and open.
- If the request involves arranging a meeting or appointment, confirm availability, negotiate suitable time slots, and schedule/re-schedule the event.
- Start with a short lead sentence, then go deeper.
- When using tools, output as many valid JSON blocks ```json ... ``` as you need, briefly say what you did and synthesize results for the user.
- Validate or refine your conclusions when new follow-up context arrives on the next turn."""

RECEPTIONIST_SECTION_REASONING = """Reasoning
- Respect CURRENT TIME AND DATE (UTC): {day_of_week} {current_date}
- Use the injected context: turn state, TODO list, comments/notes, RAG snippets, and follow-up context results.
- Thoroughly search the knowledge base: Query the knowledge base as many times as you need to find relevant information and help user out.
- Carefully arrange the meetings/appointments: First check availbility on `taskvector_cal.ics` as outlined below and get free slots (UTC). Reserve the one you agreed upon. In order to re-schedule, you first must cancel the previous one, and then reserve the new one.
"""

# Order matches Workflow Designer "Extra actions" (``workflow_designer/prompts.py``) minus read_code_block / run_workflow.
_RECEPTIONIST_SECTION_OUTPUT_FORMAT_RAW = """Output format
End your reply with a valid JSON block inside ```json ... ``` with one object or an array of objects:

Extra actions:
{tool:rag_search}
{tool:read_file}
{tool:formulas_calc}
{tool:web_search}
{tool:browse}
{tool:github}
{tool:read_current_workflow}
{tool:grep}
{tool:report}
{tool:add_comment}
{tool:todo_manager}
{tool:delegate_request}
{tool:get_chats}
{tool:send_message}
{tool:calendar}
- no_edit: { "action": "no_edit", "reason": "..." } (Use when chatting or clarifying)

No comments inside JSON. Multiple steps in one block: ```json [ { ... }, { ... } ] ```"""

RECEPTIONIST_SECTION_OUTPUT_FORMAT = expand_tool_action_placeholders(
    _RECEPTIONIST_SECTION_OUTPUT_FORMAT_RAW
).strip()

RECEPTIONIST_SECTION_DYNAMIC = """{turn_state}

{recent_changes_block}

Workflow context (TODO, comments, lightweight summary — structure may be omitted):

CURRENT DATE AND TIME: {current_date}

{graph_summary}

{rag_context}

{last_edit_block}

{follow_up_context}

Previous turn (for context):
{previous_turn}"""

RECEPTIONIST_FORMAT_KEYS: tuple[str, ...] = ("graph_summary",)


def receptionist_prompt_template_dict() -> dict[str, Any]:
    """Return the object written to ``config/prompts/receptionist.json`` (sections + format_keys)."""
    role_and_intro = f"{_receptionist_introduction_block()}\n\n{RECEPTIONIST_SECTION_ROLE_AND_INTRO_BODY}".strip()
    return {
        "format_keys": list(RECEPTIONIST_FORMAT_KEYS),
        "sections": [
            {"id": "role_and_intro", "content": role_and_intro},
            {
                "id": "conversational_behaviour",
                "content": RECEPTIONIST_SECTION_CONVERSATIONAL_BEHAVIOUR.strip(),
            },
            {"id": "reasoning", "content": RECEPTIONIST_SECTION_REASONING.strip()},
            {"id": "output_format", "content": RECEPTIONIST_SECTION_OUTPUT_FORMAT.strip()},
            {"id": "dynamic", "content": RECEPTIONIST_SECTION_DYNAMIC.strip()},
        ],
    }
