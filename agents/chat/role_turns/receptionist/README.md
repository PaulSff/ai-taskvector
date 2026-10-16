# Receptionist turn handler

Implements `ReceptionistChatHandler` (`handler.py`): manages the chat turn execution for the **receptionist** role.

## Behaviour

- **Workflow Execution**: Runs the receptionist agent workflow with specific overrides for role ID and graph summaries.
- **Cancellation Logic**: The handler implements a two-phase cancellation check:
    - **Phase 1**: Immediately after the initial workflow run, if `response.cancelled` is true, the process stops and logs the cancellation.
    - **Phase 2**: Before proceeding to response reconciliation and follow-up chains, it verifies the cancellation status again to ensure the turn is aborted if requested by the user.
- **Follow-up Chains**: 
    - **Execution Follow-ups**: If the workflow produces parser output, it triggers a follow-up chain to handle tool actions or clarifications.
    - **Post-Execution Follow-ups**: After the main result is determined, it may run a post-apply follow-up chain to finalize the turn.
- **Graph Integration**: Validates the graph before and after workflow execution, applying supplements (like client-side tasks) to the graph state.

## Related config

- Role: Defined by `RECEPTIONIST_ROLE_ID`.
- Workflow: Path resolved via `get_role_chat_workflow_path` for the receptionist role.

## Registry

Registered in `agents/chat/role_turns/registry.py` as the handler for the receptionist role.
