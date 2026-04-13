# Role turns (`gui.chat.role_turns`)

Wires the Flet assistants chat to **one turn per role**: each built-in persona lives in its own subpackage with a `README.md` and `handler.py`.

| Subpackage | Role id | Class |
|------------|---------|--------|
| [`workflow_designer/`](workflow_designer/README.md) | `workflow_designer` | `WorkflowDesignerChatHandler` |
| [`analyst/`](analyst/README.md) | `analyst` | `AnalystChatHandler` |
| [`rl_coach/`](rl_coach/README.md) | `rl_coach` | `RlCoachChatHandler` |

Shared pieces (same directory level):

- `context.py` — `RoleChatTurnContext` passed into `run_turn`
- `protocol.py` — `RoleChatHandler` protocol
- `registry.py` — `get_role_chat_handler` and built-in registration
- `turn_edits.py` — shared edit normalization helpers

Dynamic handlers from `role.yaml` `chat.handler` / `chat.chat_handler` should use a fully qualified module path; built-ins import as `gui.chat.role_turns.<subpackage>.<ClassName>` (e.g. `gui.chat.role_turns.workflow_designer.WorkflowDesignerChatHandler`).
