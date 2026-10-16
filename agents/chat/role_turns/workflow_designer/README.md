# Workflow Designer turn handler

Implements `WorkflowDesignerChatHandler` (`handler.py`): one agents-chat turn for the **workflow_designer** role.

## Behaviour

- **Execution Flow**: 
    1. **Initial Run**: Executes `workflow_designer_workflow.json` (or current graph) via `run_agent_workflow`.
    2. **Parser Follow-ups**: Chains tool-driven follow-ups (RAG, files, web, etc.) via `run_execution_follow_up_chain_async` based on the `role.yaml` tool order.
    3. **Post-Execution Review**: Runs final review rounds for specific actions (import / todo / comment) via `run_post_execution_follow_up_chain_async`.
- **Cancellation**: Supports user-initiated cancellation at multiple stages (initial run, parser follow-ups, and post-execution), which halts the turn and skips subsequent phases.
- **Graph Integration**: Applies parsed edits to the canvas after validation; includes self-correction logic on apply failure.
- **Inputs**: Builds `initial_inputs` using `build_agent_workflow_initial_inputs` and role-specific unit overrides.

## Related config

- Role: `agents/roles/workflow_designer/role.yaml`
- Workflow: `agents/roles/workflow_designer/workflow_designer_workflow.json` (or `chat.workflow` override)
- Prompt: `config/prompts/workflow_designer.json` (overridable via app settings)
- Full graph description, `initial_inputs`, and CLI: **`agents/roles/workflow_designer/README.md`**

## Registry

Registered in `agents/chat/role_turns/registry.py` as a built-in handler for `workflow_designer`.
