# RL Coach turn handler

Implements `RlCoachChatHandler` (`handler.py`): one assistants-chat turn for the **rl_coach** role.

## Behaviour

- Builds inputs with `build_rl_coach_initial_inputs` (user message, training config summary, results snippet, previous turn, config dict).
- Runs `run_rl_coach_workflow` with `build_rl_coach_unit_param_overrides` (LLM settings from chat profile).
- Normalizes `add_comment` edits via `canonicalize_add_comment_edits`.
- If the workflow returns `applied_config`, writes YAML to the session training config path (when set) and toasts success or save failure.

## Related config

- Role: `assistants/roles/rl_coach/role.yaml`
- Workflow: `assistants/roles/rl_coach/rl_coach_workflow.json` (or `chat.workflow` override)
- Prompt: `config/prompts/rl_coach.json`

## Registry

Registered in `gui/chat/role_turns/registry.py` as a built-in handler for `rl_coach`.
