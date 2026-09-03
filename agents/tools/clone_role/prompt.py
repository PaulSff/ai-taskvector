"""JSON action line for clone_role."""

TOOL_ACTION_PROMPT_LINE = """- clone_role: Create a new role by cloning an existing one:
{
  "action": "clone_role",
  "new_role_name": "lowercase_new_role_name",
  "character_name": "e.g. Alex",
  "responsibility": "Responsible for...",
  "intro_brief": "Hello, I'm Admin...<one sentence maximum>",
  "prompt_duties": "e.g. You analyze files, ...",
  "prompt_conversational_behavior": "e.g. Ask focused follow-ups when the request is vague...",
  "prompt_reasoning": "e.g. Break down tasks into smaller steps...",
  "tools": ["grep", "read_file", "formulas_calc"]
}"""
