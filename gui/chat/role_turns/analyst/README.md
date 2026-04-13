# Analyst turn handler

Implements `AnalystChatHandler` (`handler.py`): one assistants-chat turn for the **analyst** role.

## Behaviour

- Runs `analyst_workflow.json` with analyst-specific overrides: slim graph summary (TODO + comments, no full structure), analyst prompt path, and `analyst_mode` injects in follow-ups. The analyst prompt does not include the units library (unlike Workflow Designer).
- Tool follow-ups use `ORDERED_ANALYST_TOOLS` (grep, read_file, RAG, web, browse, GitHub, report, add_comment, todo_manager) — no `read_code_block` or `run_workflow` in the ordered chain.
- `ApplyEdits` in the workflow only allows comment and TODO actions; successful applies still update the canvas for those changes, with optional post-apply rounds.

## Related config

- Role: `assistants/roles/analyst/role.yaml`
- Workflow: `assistants/roles/analyst/analyst_workflow.json`
- Prompt source: `assistants/roles/analyst/prompts.py` (`analyst_prompt_template_dict`, section constants)
- Prompt file (generated): `config/prompts/analyst.json` — refresh via **Build prompts** or `scripts/write_prompt_templates.py`

## Registry

Registered in `gui/chat/role_turns/registry.py` as a built-in handler for `analyst`.
