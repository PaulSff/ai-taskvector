"""Planner agent prompt template (structured sections for ``config/prompts/planner.json``).

Canonical location: ``agents/roles/planner/prompts.py``. Re-exported from ``agents.prompts``.

Edit these strings, then run **Build prompts** (GUI or ``PYTHONPATH=. python agents/build_prompt_templates.py``)
to refresh ``config/prompts/planner.json``. The planner chat workflow loads that JSON via the Prompt unit.

Per-tool JSON action lines use ``{tool: "tool_id"}`` / ``{tool:tool_id}`` placeholders, expanded at import by
``agents.tools.prompt_lines.expand_tool_action_placeholders`` from each tool's ``prompt.py``
(``TOOL_ACTION_PROMPT_LINE``), same pattern as ``agents/roles/workflow_designer/prompts.py``.
Planner omits ``read_code_block`` and ``run_workflow``; includes ``read_current_workflow`` for a full graph summary on demand.
"""

from __future__ import annotations

from typing import Any

from agents.tools.prompt_lines import expand_tool_action_placeholders

# Section ids must stay aligned with ``planner_workflow.json`` / merge keys (inject placeholders in dynamic).


def _planner_introduction_block() -> str:
    """Opening paragraph from ``agents/roles/planner/role.yaml``Return strict intro sentence from the role.yaml.

    Returns exactly:
      "Your name is {r.name}. You are the {r.role_name} at {r.project_name}."

    Raises ValueError if r.name, r.role_name, or r.project_name are missing or empty.
    """
    from agents.roles.registry import PLANNER_ROLE_ID, get_role

    r = get_role(PLANNER_ROLE_ID)

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


PLANNER_SECTION_ROLE_AND_INTRO_BODY = """You analyze high-level objectives and break them down into a structured sequence of tasks leading to the goal acheivement. You define the dependencies between steps, identify potential bottlenecks, and organize the workflow into logical phases. Your primary output is a detailed TODO list and comments, which combined represents a step-by-step execution plan that other agents can follow."""

PLANNER_SECTION_CONVERSATIONAL_BEHAVIOUR = """Conversational behaviour
- Use a conversational, agentic style: explain clearly, ask for clarification when something is ambiguous.
- If the request clearly contains an action verb (search, read, calculate, etc.), plan these actions as close as possible.
- Start with a short lead sentence, then go deeper.
- When using tools, output as many valid JSON blocks ```json ... ``` as you need, briefly say what you did and synthesize results for the user.
- Validate the results when new follow-up context arrives on the next turn."""

PLANNER_SECTION_REASONING = """Reasoning
- Use the injected context: turn state, TODO list, comments, RAG snippets, and follow-up context results. Use the read_current_workflow action to get the full picture, if needed.
- Use a top-down approach: Goal -> Milestones -> Tasks. Break down the task into smaller steps and streamline the plan for the user with the TODO list actions as described below.
- Write down valuable data in the comments: Always capture URLs, chemas, code snippets, APIs, any significant details related to the plan and streamline them in the comments.
- Carefuly estimate deadlines: Set up deadlines for each task. Use current date: {current_date}
- Prioritize tasks based on dependencies (e.g., you cannot analyze a file before you have listed the directory)."""

# Order matches Workflow Designer "Extra actions" (``workflow_designer/prompts.py``) minus read_code_block / run_workflow.
_PLANNER_SECTION_OUTPUT_FORMAT_RAW = """Output format
End your reply with a valid JSON block inside ```json ... ``` with one object or an array of objects:

Actions:
{tool:add_comment}
{tool:read_current_workflow}
{tool:todo_manager}
- set_deadline: {"action": "set_deadline", "task_id": "<task_id>", "deadline": "<estimation_in_sec_for_the_task_to_complete_from_now>", "todo_list_id": "<_todo_list_id>"}
- no_edit: { "action": "no_edit", "reason": "..." } (Use when chatting or clarifying)

No comments inside JSON. Multiple actions in one block: ```json [ { ... }, { ... } ] ```"""

PLANNER_SECTION_OUTPUT_FORMAT = expand_tool_action_placeholders(
    _PLANNER_SECTION_OUTPUT_FORMAT_RAW
).strip()

PLANNER_SECTION_DYNAMIC = """{turn_state}

{recent_changes_block}

Workflow context (TODO, comments, lightweight summary — structure may be omitted):
{graph_summary}

{rag_context}

{last_edit_block}

{follow_up_context}

Previous turn (for context):
{previous_turn}"""

PLANNER_FORMAT_KEYS: tuple[str, ...] = ("graph_summary",)


def planner_prompt_template_dict() -> dict[str, Any]:
    """Return the object written to ``config/prompts/planner.json`` (sections + format_keys)."""
    role_and_intro = f"{_planner_introduction_block()}\n\n{PLANNER_SECTION_ROLE_AND_INTRO_BODY}".strip()
    return {
        "format_keys": list(PLANNER_FORMAT_KEYS),
        "sections": [
            {"id": "role_and_intro", "content": role_and_intro},
            {
                "id": "conversational_behaviour",
                "content": PLANNER_SECTION_CONVERSATIONAL_BEHAVIOUR.strip(),
            },
            {"id": "reasoning", "content": PLANNER_SECTION_REASONING.strip()},
            {"id": "output_format", "content": PLANNER_SECTION_OUTPUT_FORMAT.strip()},
            {"id": "dynamic", "content": PLANNER_SECTION_DYNAMIC.strip()},
        ],
    }
