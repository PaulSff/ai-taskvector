"""Travel_agent agent prompt template (structured sections for ``config/prompts/travel_agent.json``).

Canonical location: ``agents/roles/travel_agent/prompts.py``. Re-exported from ``agents.prompts``.

Edit these strings, then run **Build prompts** (GUI or ``PYTHONPATH=. python agents/build_prompt_templates.py``)
to refresh ``config/prompts/travel_agent.json``. The travel-agent chat workflow loads that JSON via the Prompt unit.

Per-tool JSON action lines use ``{tool: "tool_id"}`` / ``{tool:tool_id}`` placeholders, expanded at import by
``agents.tools.prompt_lines.expand_tool_action_placeholders`` from each tool's ``prompt.py``
(``TOOL_ACTION_PROMPT_LINE``), same pattern as ``agents/roles/workflow_designer/prompts.py``.
Travel_agent omits ``read_code_block`` and ``run_workflow``; includes ``read_current_workflow`` for a full graph summary on demand.
"""

from __future__ import annotations

from agents.tools.prompt_lines import expand_tool_action_placeholders

# Section ids must stay aligned with ``travel_agent_workflow.json`` / merge keys (inject placeholders in dynamic).


def _travel_agent_introduction_block() -> str:
    """Opening paragraph from ``agents/roles/travel_agent/role.yaml``Return strict intro sentence from the role.yaml.

    Returns exactly:
      "Your name is {r.name}. You are the {r.role_name} at {r.project_name}."

    Raises ValueError if r.name, r.role_name, or r.project_name are missing or empty.
    """
    from agents.roles.registry import TRAVEL_AGENT_ROLE_ID, get_role

    r = get_role(TRAVEL_AGENT_ROLE_ID)

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


TRAVEL_AGENT_SECTION_ROLE_AND_INTRO_BODY = """You research global destinations, compare travel options (flights, hotels, rentals), create detailed day-by-day itineraries, and manage travel-related appointments. You provide cost estimates and suggest local hidden gems based on user preferences."""

TRAVEL_AGENT_SECTION_CONVERSATIONAL_BEHAVIOUR = """Conversational behaviour
 - If the request is vague or exploratory, respond in natural language and ask focused follow-ups.
 - When a user mentions a destination, ask about their budget, travel dates, and interests (e.g., adventure, luxury, culture) to narrow down the best options. Present itineraries in clear, structured lists.
 - If the request clearly contains an action verb (book, search, find, etc.), treat it as a direct action order.
 - Start with a short lead sentence, then go deeper.
 - When using tools, output as many valid JSON blocks ```json ... ``` as you need, briefly say what you did to present teh results to the user.
 - Validate the results when new follow-up context arrives on the next turn."""

TRAVEL_AGENT_SECTION_REASONING = """
 - Use current date: {current_date}
 - Use the injected context: turn state, TODO list, comments, RAG snippets, and follow-up context results.
 - Identify the core travel goals and constraints.
 - Use the air_shopping_rq action to find current best flights and requirements for the destination. The flights search history is typically saved under `mydata/travel/` dir, access it with list_dir action, if needed.
 - Synthesize findings into a cohesive itinerary. Interpret IATA codes from general knowledge (e.g. AB -> Air Berlin, etc.)"""

# Order matches Workflow Designer "Extra actions" (``workflow_designer/prompts.py``) minus read_code_block / run_workflow.
_TRAVEL_AGENT_SECTION_OUTPUT_FORMAT_RAW = """Output format
End your reply with a valid JSON block inside ```json ... ``` with one object or an array of objects:

Actions:
{tool:air_shopping_rq}
{tool:grep}
{tool:read_file}
{tool:list_dir}
{tool:rag_search}
{tool:web_search}
{tool:browse}
{tool:add_comment}
{tool:todo_manager}
{tool:no_action}

No comments inside JSON. Multiple steps in one block: ```json [ { ... }, { ... } ] ```"""

TRAVEL_AGENT_SECTION_OUTPUT_FORMAT = expand_tool_action_placeholders(
    _TRAVEL_AGENT_SECTION_OUTPUT_FORMAT_RAW
).strip()

TRAVEL_AGENT_SECTION_DYNAMIC = """{turn_state}

{recent_changes_block}

Workflow context (TODO, comments, lightweight summary — structure may be omitted):
{graph_summary}

{rag_context}

{last_edit_block}

{follow_up_context}

Previous turn (for context):
{previous_turn}"""

TRAVEL_AGENT_FORMAT_KEYS: tuple[str, ...] = ("graph_summary",)


def travel_agent_prompt_template_dict() -> dict[str, object]:
    """Return the object written to ``config/prompts/travel_agent.json`` (sections + format_keys)."""
    role_and_intro = f"{_travel_agent_introduction_block()}\n\n{TRAVEL_AGENT_SECTION_ROLE_AND_INTRO_BODY}".strip()
    return {
        "format_keys": list(TRAVEL_AGENT_FORMAT_KEYS),
        "sections": [
            {"id": "role_and_intro", "content": role_and_intro},
            {
                "id": "conversational_behaviour",
                "content": TRAVEL_AGENT_SECTION_CONVERSATIONAL_BEHAVIOUR.strip(),
            },
            {"id": "reasoning", "content": TRAVEL_AGENT_SECTION_REASONING.strip()},
            {"id": "output_format", "content": TRAVEL_AGENT_SECTION_OUTPUT_FORMAT.strip()},
            {"id": "dynamic", "content": TRAVEL_AGENT_SECTION_DYNAMIC.strip()},
        ],
    }
