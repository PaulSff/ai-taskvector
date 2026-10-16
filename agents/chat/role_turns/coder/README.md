# Coder turn handler

Implements `CoderChatHandler` (`handler.py`): manages a single chat turn for the **coder** role.

## Behaviour

The handler executes a multi-phase process to ensure graph consistency and allow for iterative tool use:

1. **Initial Workflow**: Runs the coder agent workflow. If the user cancels the request, the process stops immediately.
2. **Graph Reconciliation**: Validates the resulting graph and augments it with client-side tasks (e.g., coding tasks) before applying it to the state.
3. **Execution Follow-ups**: If the model produces tool actions, it enters a follow-up chain to execute those tools and refine the response.
4. **Post-Execution Follow-ups**: A final round of follow-ups to ensure the result is complete and polished.

### Cancellation Logic
- The handler monitors the `cancelled` flag from the workflow response. If `True`, it logs the cancellation and aborts subsequent phases (reconciliation and follow-ups) to prevent unnecessary state updates.

### Graph Validation
- Uses `validate_graph_to_apply_inline` to ensure that any graph modifications proposed by the LLM are structurally sound before they are persisted.

## Related config

- Role: `agents/roles/coder/role.yaml`
- Workflow: Defined by `get_role_chat_workflow_path(CODER_ROLE_ID)`
- Registry: Registered in `agents/chat/role_turns/registry.py` as the handler for the `coder` role.
