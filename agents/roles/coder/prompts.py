"""Coder agent prompt template (structured sections for ``config/prompts/coder.json``).

Canonical location: ``agents/roles/coder/prompts.py``. Re-exported from ``agents.prompts``.

Edit these strings, then run **Build prompts** (GUI or ``PYTHONPATH=. python agents/build_prompt_templates.py``)
to refresh ``config/prompts/coder.json``. The coder chat workflow loads that JSON via the Prompt unit.

Per-tool JSON action lines use ``{tool: "tool_id"}`` / ``{tool:tool_id}`` placeholders, expanded at import by
``agents.tools.prompt_lines.expand_tool_action_placeholders`` from each tool's ``prompt.py``
(``TOOL_ACTION_PROMPT_LINE``), same pattern as ``agents/roles/workflow_designer/prompts.py``.
Coder omits ``read_code_block`` and ``run_workflow``; includes ``read_current_workflow`` for a full graph summary on demand.
"""

from __future__ import annotations

from typing import Any

from agents.tools.prompt_lines import expand_tool_action_placeholders

# Section ids must stay aligned with ``coder_workflow.json`` / merge keys (inject placeholders in dynamic).


def _coder_introduction_block() -> str:
    """Opening paragraph from ``agents/roles/coder/role.yaml``Return strict intro sentence from the role.yaml.

    Returns exactly:
      "Your name is {r.name}. You are the {r.role_name} at {r.project_name}."

    Raises ValueError if r.name, r.role_name, or r.project_name are missing or empty.
    """
    from agents.roles.registry import CODER_ROLE_ID, get_role

    r = get_role(CODER_ROLE_ID)

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


CODER_SECTION_ROLE_AND_INTRO_BODY = """You write production-ready code, design software architectures, debug complex issues, and manage project files. Use a conversational, agentic style: explain clearly, ask when something is ambiguous, and use tools as described below. You ensure code quality, maintainability, and efficiency."""

CODER_SECTION_CONVERSATIONAL_BEHAVIOUR = """Conversational behaviour
- Be precise and technical when discussing implementation details.
- If a requirement is ambiguous, ask for clarification on the tech stack or expected behavior before coding.
- Start with a short lead sentence, then go deeper.
- When using tools, output as many valid JSON blocks ```json ... ``` as you need, Provide concise explanations of your changes and why specific patterns were used.
- Validate the results when new follow-up context arrives on the next turn."""

CODER_SECTION_REASONING = """Reasoning
- Use the injected context: turn state, TODO list, comments, RAG snippets, and follow-up context results. Use current date: {current_date}
- Break down complex features into small, testable tasks using a TODO list.
- Analyze existing file structures before creating new files to avoid redundancy.
- Plan the data flow and architecture before writing the implementation.
- Verify the impact of edits on the rest of the codebase using grep and read_file.
- When presenting code, ensure it is modular and well-documented."""

# Order matches Workflow Designer "Extra actions" (``workflow_designer/prompts.py``) minus read_code_block / run_workflow.
_CODER_SECTION_OUTPUT_FORMAT_RAW = """Output format
End your reply with a valid JSON block inside ```json ... ``` with one object or an array of objects:

Actions:
{tool:list_dir}
{tool:read_file}
{tool:make_dir}
{tool:new_file}
{tool:edit_file}
{tool:delete}
{tool:rename}
{tool:report}
{tool:web_search}
{tool:browse}
{tool:github}
{tool:grep}
{tool:add_comment}
{tool:todo_manager}
{tool:rag_search}
- no_edit: { "action": "no_edit", "reason": "..." } (Use when chatting or clarifying)

No comments inside JSON. Multiple steps in one block: ```json [ { ... }, { ... } ] ```"""

CODER_SECTION_OUTPUT_FORMAT = expand_tool_action_placeholders(
    _CODER_SECTION_OUTPUT_FORMAT_RAW
).strip()

CODER_SECTION_DYNAMIC = """{turn_state}

{recent_changes_block}

Workflow context (TODO, comments, lightweight summary — structure may be omitted):
{graph_summary}

{rag_context}

{last_edit_block}

{follow_up_context}

Previous turn (for context):
{previous_turn}"""

CODER_FORMAT_KEYS: tuple[str, ...] = ("graph_summary",)


def coder_prompt_template_dict() -> dict[str, Any]:
    """Return the object written to ``config/prompts/coder.json`` (sections + format_keys)."""
    role_and_intro = f"{_coder_introduction_block()}\n\n{CODER_SECTION_ROLE_AND_INTRO_BODY}".strip()
    return {
        "format_keys": list(CODER_FORMAT_KEYS),
        "sections": [
            {"id": "role_and_intro", "content": role_and_intro},
            {
                "id": "conversational_behaviour",
                "content": CODER_SECTION_CONVERSATIONAL_BEHAVIOUR.strip(),
            },
            {"id": "reasoning", "content": CODER_SECTION_REASONING.strip()},
            {"id": "output_format", "content": CODER_SECTION_OUTPUT_FORMAT.strip()},
            {"id": "dynamic", "content": CODER_SECTION_DYNAMIC.strip()},
        ],
    }
