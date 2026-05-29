# RL Coach turn handler

Implements `RlCoachChatHandler` (`handler.py`): one agents-chat turn for the **rl_coach** role.

## Behaviour

- Builds inputs with `build_rl_coach_initial_inputs` (user message, training config summary, results snippet, previous turn, config dict).
- Runs `run_rl_coach_workflow` (see `workflow_runner.py`) with `build_rl_coach_unit_param_overrides` (LLM settings from chat profile); execution delegates to `gui.chat.agent_workflow.run_agent_workflow`.
- Normalizes `add_comment` edits via `canonicalize_add_comment_edits`.
- If `merge_response.data.result` has `kind == "applied"`, writes `result.config` as YAML to the session training config path (when set) and toasts success or save failure.

## Related config

- Role: `agents/roles/rl_coach/role.yaml`
- Workflow: `agents/roles/rl_coach/rl_coach_workflow.json` (or `chat.workflow` override)
- Prompt: `config/prompts/rl_coach.json`
- Full graph description, `initial_inputs`, CLI, and reward/config merge pointers: **`agents/roles/rl_coach/README.md`**

## Registry

Registered in `gui/chat/role_turns/registry.py` as a built-in handler for `rl_coach`.
