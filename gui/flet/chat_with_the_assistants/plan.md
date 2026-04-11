# Assistants chat: role handlers & registry

## Goal

Move per-assistant turn logic out of `chat.py` into **`role_handlers/`**: one **`RoleChatHandler`** per `role_id`, a small **registry**, and a shared **`RoleChatTurnContext`** (Flet + session closures). `assistants/roles/` stays pure (YAML, `get_role`, tools); no Flet imports there.

## Phases

### Phase A — Registry + extraction (done)

- [x] `RoleChatTurnContext` — dataclass of everything one turn needs from the panel (page, state, graph_ref, callbacks, settings snapshots).
- [x] `role_handlers/registry.py` — `get_role_chat_handler(role_id) -> RoleChatHandler | None`.
- [x] `workflow_designer.py` — `WorkflowDesignerChatHandler.run_turn` (full WD path moved from `chat.py`).
- [x] `rl_coach.py` — `RlCoachChatHandler.run_turn` (RL path moved).
- [x] `chat.py` — build `RoleChatTurnContext` once per turn, `handler = get_role_chat_handler(profile)` then `await handler.run_turn(turn_ctx, …)` when non-`None`; unsupported-role `else` branch kept.

**Next:** Phase B (pure helpers for inputs/overrides).

### Phase B — Pure helpers (assistants)

- [x] Move `build_assistant_workflow_initial_inputs` (and `default_wf_language_hint`) into `assistants/roles/workflow_designer/workflow_inputs.py`; keep `workflow_designer_handler.py` as runtime glue. **Still optional:** move `build_assistant_workflow_unit_param_overrides` defaults similarly.
- [x] Move `build_rl_coach_initial_inputs` into `assistants/roles/rl_coach/workflow_inputs.py`; `rl_coach_handler.py` re-exports it. **Still optional:** move `build_rl_coach_unit_param_overrides` or training-config loaders when paths are fully role-driven.
- [x] Resolve WD/RL main chat workflow path from `role.yaml` `chat.workflow` via `assistants.roles.get_role_chat_workflow_path` (removed `assistant_workflow_path` / `rl_coach_workflow_path` from app settings).

### Phase C — Features flags (done)

- [x] Honor `RoleConfig.chat.features`: `graph_canvas` gates dev “Run current graph” (visibility + `RoleChatTurnContext.show_run_current_graph`); `create_chat_title` gates `create_filename` on first message (slugify-only when false). Unknown keys: no effect; missing key uses default `True` via `role_chat_feature_enabled`.

### Phase D — Dynamic handlers (done)

- [x] Optional `chat.handler` or `chat.chat_handler` in `role.yaml` (`module.path:ClassName` or `module.path.ClassName`); `get_role_chat_handler` loads after built-ins, caches per `role_id`, requires `handler.role_id` to match folder id. Tests: `clear_dynamic_handler_cache()` + `clear_role_cache()`.

## Files

| Path | Role |
|------|------|
| `gui/flet/chat_with_the_assistants/plan.md` | This roadmap |
| `gui/flet/chat_with_the_assistants/role_handlers/protocol.py` | `RoleChatHandler` protocol |
| `gui/flet/chat_with_the_assistants/role_handlers/context.py` | `RoleChatTurnContext` |
| `gui/flet/chat_with_the_assistants/role_handlers/registry.py` | `role_id` → handler (built-in + optional YAML `chat.handler`) |
| `gui/flet/chat_with_the_assistants/role_handlers/workflow_designer.py` | WD turn |
| `gui/flet/chat_with_the_assistants/role_handlers/rl_coach.py` | RL turn |
| `gui/flet/chat_with_the_assistants/chat.py` | Panel UI + build context + dispatch |

## Testing

- Manual: WD apply + follow-ups + RL reply + training save.
- `python scripts/test_role_tools.py` (roles YAML + dropdown ids).
