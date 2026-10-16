# Planner turn handler

Implements `PlannerChatHandler` (`handler.py`): manages the execution of a single chat turn for the **planner** role.

## Behaviour

- **Multi-Phase Execution**: The turn is processed in several stages:
    1. **Initial Workflow**: Runs the agent workflow to generate a response and potential graph edits.
    2. **Reconciliation**: Validates the resulting graph and augments it with client-side tasks via `augment_graph_with_client_tasks`.
    3. **Execution Follow-ups**: Runs a chain of follow-up rounds if the parser output indicates further actions are needed.
    4. **Post-Execution Follow-ups**: Final rounds to refine the response or handle post-apply logic.

- **Cancellation Logic**: The handler explicitly monitors for user cancellation at multiple stages. If `response.cancelled` is true after the initial workflow run or during the transition to subsequent phases, the process is halted immediately to prevent unnecessary LLM calls or state updates.

- **Graph Management**: Ensures that the `ProcessGraph` is validated before and after application. It supports `light_graph_mode` to optimize prompt context.

## Related config

- Role: Defined by `PLANNER_ROLE_ID`.
- Workflow: Path resolved via `get_role_chat_workflow_path`.

## Registry

Registered in `agents/chat/role_turns/registry.py` as the handler for the planner role.
