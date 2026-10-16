# Analyst turn handler

Implements `AnalystChatHandler` (`handler.py`): one agents-chat turn for the **analyst** role.

## Behaviour

### Execution Flow
The handler follows a three-phase execution cycle:
1. **Initial Workflow**: Runs the analyst workflow to generate the first response and potential edits.
2. **Execution Follow-ups**: If the parser identifies actions, it enters a follow-up chain (`parser_output_follow_up_chain`) to execute tool actions and refine the response.
3. **Post-Execution Follow-ups**: A final phase (`run_post_execution_follow_up_chain_async`) for post-apply rounds and final reconciliation.

### Key Logic
- **Cancellation**: The handler monitors `response.cancelled`. If a user cancels the turn during the initial run or follow-up chain, the process stops immediately, and subsequent phases (like post-execution follow-ups) are skipped.
- **Graph Integrity**: Employs `validate_graph_to_apply_inline` to ensure the graph is valid before execution and before applying the `after_graph` returned by the workflow.
- **Client-Side Augmentation**: Uses `augment_graph_with_client_tasks` to inject client-side tasks into the graph based on the parsed edits.
- **Overrides**: Uses analyst-specific overrides including a slim graph summary (TODOs and comments only) and `light_graph_mode` for follow-ups.
- **Error Handling**: Specifically handles `WorkflowTimeoutError` and general exceptions, ensuring the UI receives a clean error message via toasts and the state is published as a failure result.

## Related config

- Role: `agents/roles/analyst/role.yaml`
- Workflow: `agents/roles/analyst/analyst_workflow.json`
- Prompt source: `agents/roles/analyst/prompts.py` (`analyst_prompt_template_dict`, section constants)
- Prompt file (generated): `config/prompts/analyst.json` — refresh via **Build prompts** or `agents/build_prompt_templates.py`

## Registry

Registered in `agents/chat/role_turns/registry.py` as a built-in handler for `analyst`.
