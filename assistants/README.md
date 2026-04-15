# Assistants: roles and tools

**Roles** (`assistants/roles/`) describe who the assistant is: stable `id`, UI labels, optional intro text, ordered **tool** IDs (`tools:` in YAML), optional **chat** block (workflow file, feature flags, optional custom handler), and optional follow-up limits. **Tools** (`assistants/tools/`) are shared follow-up implementations (RAG, files, grep, web, …); roles enable them by listing stable string IDs that match `assistants/tools/catalog.py` / `assistants/tools/registry.py`.

The Flet assistants panel resolves each turn with **`get_role_chat_handler(role_id)`** (`gui/chat/role_turns/registry.py`). **workflow_designer**, **analyst**, and **rl_coach** use built-in handlers under `gui/chat/role_turns/<role_id>/` (see `gui/chat/role_turns/README.md`). Other roles can set **`chat.handler`** / **`chat.chat_handler`** in `role.yaml` to a `RoleChatHandler` import path.

Main chat workflow JSON files (default filenames; override with `chat.workflow` in each role’s `role.yaml`):

- `assistants/roles/workflow_designer/workflow_designer_workflow.json`
- `assistants/roles/rl_coach/rl_coach_workflow.json`
- `assistants/roles/analyst/analyst_workflow.json`

Resolve paths at runtime with **`assistants.roles.workflow_path.get_role_chat_workflow_path`**.

---

## Documentation

| Topic | Guide |
|--------|--------|
| **Roles** — `role.yaml`, loader, creating a role, Flet wiring | [roles/README.md](roles/README.md) |
| **Workflow Designer** — chat graph, `initial_inputs`, run / CLI | [roles/workflow_designer/README.md](roles/workflow_designer/README.md) |
| **RL Coach** — training injects, config merge, run / CLI | [roles/rl_coach/README.md](roles/rl_coach/README.md) |
| **Tools** — catalog, follow-up runners, registry | [tools/README.md](tools/README.md) |

---

## Prompts

Role-facing default strings live in **`assistants/roles/<role_id>/prompts.py`**; **`assistants/prompts.py`** re-exports them for imports elsewhere. Prompt **templates** wired in graphs often live under **`config/prompts/`** (e.g. `workflow_designer.json`, `rl_coach.json`). After editing those sources, run:

`PYTHONPATH=. python scripts/write_prompt_templates.py`

---

## Quick reference

| What | Where |
|------|-------|
| Role schema / loader | `assistants/roles/types.py`, `assistants/roles/registry.py` |
| Chat dropdown order + main role ids | `list_chat_dropdown_role_ids()`, `CHAT_MAIN_ASSISTANT_ROLE_IDS` in `assistants/roles/registry.py` |
| `chat:` parsing + feature flags | `assistants/roles/chat_config.py` |
| Chat workflow path resolution | `assistants/roles/workflow_path.py` |
| Tools: order + parser keys | `assistants/tools/catalog.py` |
| Tools: runner registry | `assistants/tools/registry.py` |
| Flet chat handlers | `gui/chat/role_turns/README.md`, `…/protocol.py`, `…/registry.py` |
| Chat panel + turn dispatch | `gui/chat/chat.py` |
| WD-style parser follow-ups | `gui/chat/parser_follow_up/` |
| Shared `run_workflow` entry for role JSON | `gui/chat/assistant_workflow/` (`run_assistant_workflow`, paths, overrides) |
