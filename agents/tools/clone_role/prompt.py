"""JSON action line for clone_role."""

TOOL_ACTION_PROMPT_LINE = (
    """ - clone_role - create new role by clonnig an existing one (Analyst):
        {
          action: "clone_role",
          new_role_name: "e.g. administrator",
          character_name: "e.g. Alex",
          responsibility: "Responsible for...",
          intro_brief: "Hello, I'm Admin...<one sentence at max>",
          prompt_duties: "e.g. You analyse files, ...",
          prompt_conversational_behavior: "e.g. - If the request is vague or exploratory, respond in natural language and ask focused follow-ups...",
          prompt_reasoning: "e.g. - Break down tasks..., -...",
          tools: ["grep", "read_file", "formulas_calc", ...]
        }"""
)
