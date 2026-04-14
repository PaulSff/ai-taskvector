# Assistants: roles and tools

**Roles** (`assistants/roles/`) describe who the assistant is: labels, optional intro, ordered **tool** IDs, optional **chat** settings for the Flet panel, and follow-up limits. **Tools** (`assistants/tools/`) are shared follow-up implementations (RAG, file reads, search, …) that roles enable by listing stable string IDs.

The Flet chat resolves `role_id` with `get_role_chat_handler` in `gui/chat/role_turns/registry.py`. **Workflow Designer**, **Analyst**, and **RL Coach** are built-in (see `gui/chat/role_turns/README.md`); other chat-enabled roles can supply `chat.handler` / `chat.chat_handler` in YAML to load a `RoleChatHandler` on demand.

Phased rollout and file inventory: [MIGRATION_ROLES_TOOLS.md](MIGRATION_ROLES_TOOLS.md).

---

## Documentation

| Topic | Guide |
|--------|--------|
| **Roles** — `role.yaml`, prompts, workflows, Flet wiring | [roles/README.md](roles/README.md) |
| **Tools** — catalog order, follow-up runners, registry, tests | [tools/README.md](tools/README.md) |

---

## Quick reference

| What | Where |
|------|-------|
| Roles: schema / loader | `assistants/roles/types.py`, `assistants/roles/registry.py` |
| Roles: `chat:` config | `assistants/roles/chat_config.py` |
| Tools: order + parser keys | `assistants/tools/catalog.py` |
| Tools: runner registry | `assistants/tools/registry.py` |
| Flet chat handlers | `gui/chat/role_turns/README.md`, `…/protocol.py`, `…/registry.py` |
| Chat panel + turn dispatch | `gui/chat/chat.py` |
| WD follow-up orchestration | `gui/chat/parser_follow_up/` |
| Shared role chat workflow run | `gui/chat/assistant_workflow/` |
