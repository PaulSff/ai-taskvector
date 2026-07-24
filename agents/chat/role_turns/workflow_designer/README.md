# Workflow Designer turn handler

Implements `WorkflowDesignerChatHandler` (`handler.py`): one agents-chat turn for the **workflow_designer** role.

## Behaviour

- Runs `workflow_designer_workflow.json` (or **Run current graph** when enabled) via `gui.chat.agent_workflow.run_agent_workflow` / `workflow_runner.run_current_graph`.
- Builds `initial_inputs` with `build_agent_workflow_initial_inputs` and unit overrides from `build_agent_workflow_unit_param_overrides` (LLM, RAG, prompt, graph summary, report dir).
- Chains parser-driven tool follow-ups (`gui.chat.parser_follow_up.run_parser_output_follow_up_chain`): RAG, files, web, code blocks, run_workflow, etc.
- Applies parsed graph edits to the canvas when valid; runs post-apply review rounds (import / todo / comment) and same-turn self-correction on apply failure.

## Related config

- Role: `agents/roles/workflow_designer/role.yaml`
- Workflow: `agents/roles/workflow_designer/workflow_designer_workflow.json` (or `chat.workflow` override)
- Prompt: `config/prompts/workflow_designer.json` (overridable via app settings)
- Full graph description, `initial_inputs`, and CLI: **`agents/roles/workflow_designer/README.md`**

## Registry

Registered in `gui/chat/role_turns/registry.py` as a built-in handler for `workflow_designer`.
