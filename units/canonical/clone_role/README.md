# Unit: CloneRole

Creates new roles by means of clonnig an exesting one - the Analyst. The unit is a wrapper around the following script: `agent/roles/clone_role.py`

## Input (single data port):

```json
{
  action: "clone_role",
  new_role_name: "administrator",
  character_name: "Alex",
  responsibility: "Responsible for...",
  intro_brief: "Hello, I'm Admin.",
  prompt_duties: "You analyse files...",
  prompt_conversational_behavior: "If the request is vague or exploratory, respond in natural language and ask focused follow-ups...",
  prompt_reasoning: "Break down tasks...",
  tools: ["grep", "read_file", "formulas_calc"]
}
```

## Output ports:
- data (Any): success payload or None
- error (str): empty on success, populated on failure

Success response payload:

```json
{
  success: true,
  new_role: "<new_role>",
  config_path: "agents/roles/<new_role>/role.yaml",
  workflow_path: "agents/roles/<new_role>/<new_role>_workflow.json",
  prompt_script_path: "agents/roles/<new_role>/prompts.py",
  tools: [...]
}
```

## Params
- `clone_script_path` - a path to the script, defaults to `agent/roles/clone_role.py`, if not set
