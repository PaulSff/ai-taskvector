# Demiurge turn handler

Implements `DemiurgeChatHandler` (`handler.py`): one agents-chat turn for the **Demiurge** (Workflow Designer) role.

## Behaviour

- **Workflow Execution**: Runs the Demiurge agent workflow to process user requests, apply graph edits, and execute tool actions.
- **Multi-Phase Process**:
    1. **Initial Workflow**: Executes the primary agent workflow.
    2. **Execution Follow-ups**: Runs a chain of follow-up rounds based on parser output to refine actions or seek clarification.
    3. **Post-Execution Follow-ups**: Final rounds to verify the result or perform cleanup.
- **Cancellation Logic**: 
    - The handler monitors for user cancellation at multiple stages (Phase 1, Phase 2, and during follow-up chains).
    - If a cancellation is detected, the handler logs the event and immediately halts further execution, skipping subsequent follow-up phases to ensure responsiveness.
- **Graph Integration**: Validates the graph before and after application, augmenting it with client-side tasks (TODOs) where applicable.

## Related config

- Role: `agents/roles/demiurge/role.yaml`
- Workflow: Defined via `get_role_chat_workflow_path(DEMIURGE_ROLE_ID)`
- Registry: Registered in `agents/chat/role_turns/registry.py` as the handler for `demiurge`.
