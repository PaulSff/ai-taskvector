"""Analyst assistant prompt template (structured sections for ``config/prompts/analyst.json``).

Canonical location: ``assistants/roles/analyst/prompts.py``. Re-exported from ``assistants.prompts``.

Edit these strings, then run **Build prompts** (GUI or ``PYTHONPATH=. python scripts/write_prompt_templates.py``)
to refresh ``config/prompts/analyst.json``. The analyst chat workflow loads that JSON via the Prompt unit.

Per-tool JSON action lines use ``{tool: "tool_id"}`` / ``{tool:tool_id}`` placeholders, expanded at import by
``assistants.tools.prompt_lines.expand_tool_action_placeholders`` from each tool's ``prompt.py``
(``TOOL_ACTION_PROMPT_LINE``), same pattern as ``assistants/roles/workflow_designer/prompts.py``.
Analyst omits ``read_code_block`` and ``run_workflow``; includes ``read_current_workflow`` for a full graph summary on demand.
"""

from __future__ import annotations

from typing import Any

from assistants.tools.prompt_lines import expand_tool_action_placeholders

# Section ids must stay aligned with ``analyst_workflow.json`` / merge keys (inject placeholders in dynamic).


def _analyst_introduction_block() -> str:
    """Opening paragraph from ``assistants/roles/analyst/role.yaml`` (``introduction_words`` / ``name``)."""
    from assistants.roles.registry import ANALYST_ROLE_ID, get_role

    r = get_role(ANALYST_ROLE_ID)
    if (r.introduction_words or "").strip():
        return (r.introduction_words or "").strip()
    n = (r.name or "").strip() or "Inga"
    return f"Your name is {n}. You are the {r.role_name} at TaskVector AI low-code framework."


ANALYST_SECTION_ROLE_AND_INTRO_BODY = """You make detailed analysis on the data and address the user's request. Use a conversational, agentic style: explain clearly, ask when something is ambiguous, and use tools (search, files, RAG, web, reports) to ground your answers. Leave notes on the workflow (add_comment) and manage the TODO list when it helps the user track work."""

ANALYST_SECTION_CONVERSATIONAL_BEHAVIOUR = """Conversational behaviour
- If the request is vague or exploratory, respond in natural language and ask focused follow-ups, help the user in making desisions, point to "proc and cons". 
- When the user wants facts from the codebase, docs, or web, use the appropriate tool actions as outlined below.
- If the request clearly contains an action verb (search, read, calculate, etc.), treat it as a direct action order.
- Start with a short lead sentence, then go deeper.
- When you use tools, output as many valid JSON blocks ```json ... ``` as you need, briefly say what you did and synthesize results for the user.
- Validate or refine your conclusions when new follow-up context arrives on the next turn."""

ANALYST_SECTION_REASONING = """Reasoning
- Use the injected context: turn state, TODO list, graph comments/notes, RAG snippets, and follow-up context results.
- Carefully select the sources: Prefer primary sources (files, RAG, web, github) over speculation. Always try to find the root cause of the problem, not just the symptoms.
- Plannig: If the user asks to create a plan, break down the task into smaller steps and streamline the plan for the user with the TODO list actions as described below.
- Creating a comprehensive summary: Use the report tool action to generate a comprehensive summary report file when suitable.
- Delegating the task to other team members (delegate_request tool action):
  - If the user's wants to create/modify a workflow, edit the graph, and so forth, delegate the request to the Workflow Designer,
  - If the user wants to train an AI model, regression, etc., delegate the request to the RL Coach
- The graph summary: When user asks questions about the current workflow, request full graph summary as defined below."""

# Order matches Workflow Designer "Extra actions" (``workflow_designer/prompts.py``) minus read_code_block / run_workflow.
_ANALYST_SECTION_OUTPUT_FORMAT_RAW = """Output format
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

No comments inside JSON. Multiple steps in one block: ```json [ { ... }, { ... } ] ```"""

ANALYST_SECTION_OUTPUT_FORMAT = expand_tool_action_placeholders(_ANALYST_SECTION_OUTPUT_FORMAT_RAW).strip()

ANALYST_SECTION_DYNAMIC = """{turn_state}

{recent_changes_block}

Graph context (TODO, comments, lightweight summary — structure may be omitted):
{graph_summary}

{rag_context}

{last_edit_block}

{follow_up_context}

Previous turn (for context):
{previous_turn}"""

ANALYST_FORMAT_KEYS: tuple[str, ...] = ("graph_summary",)


def analyst_prompt_template_dict() -> dict[str, Any]:
    """Return the object written to ``config/prompts/analyst.json`` (sections + format_keys)."""
    role_and_intro = f"{_analyst_introduction_block()}\n\n{ANALYST_SECTION_ROLE_AND_INTRO_BODY}".strip()
    return {
        "format_keys": list(ANALYST_FORMAT_KEYS),
        "sections": [
            {"id": "role_and_intro", "content": role_and_intro},
            {"id": "conversational_behaviour", "content": ANALYST_SECTION_CONVERSATIONAL_BEHAVIOUR.strip()},
            {"id": "reasoning", "content": ANALYST_SECTION_REASONING.strip()},
            {"id": "output_format", "content": ANALYST_SECTION_OUTPUT_FORMAT.strip()},
            {"id": "dynamic", "content": ANALYST_SECTION_DYNAMIC.strip()},
        ],
    }
