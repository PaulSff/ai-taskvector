# Agents: Roles and Tools

The `agents/` directory implements a configuration-driven persona system. It separates **who** the agent is (Roles) from **what** the agent can do (Tools).

- **Roles** (`agents/roles/`): Define the persona, identity, and the specific subset of tools available to that agent via a `role.yaml` configuration.
- **Tools** (`agents/tools/`): Shared, modular capabilities (e.g., RAG, file system access, web search) that are registered globally and assigned to roles.

The Flet agents panel resolves each turn with **`get_role_chat_handler(role_id)`** (`agents/chatrole_turns/registry.py`). **workflow_designer**, **analyst**, and **rl_coach** use built-in handlers under `agents/chat/role_turns/<role_id>/` (see `agents/chat/role_turns/README.md`). Other roles can set **`chat.handler`** / **`chat.chat_handler`** in `role.yaml` to a `RoleChatHandler` import path.

### Role Configuration
Each role is defined by a `role.yaml` file containing:
- `id`: Unique identifier for the role.
- `tools`: A list of tool IDs the agent is permitted to use.
- `follow_up_limit`: Controls the conversation depth/turn limit.
- `chat`: Optional configuration for workflow files and custom handlers.

### Tool Architecture
Tools use a plugin-based registration pattern. Each tool defines **Action Blocks** (Pydantic models) that allow the AI to trigger structured, validated actions. Tools are automatically discovered and mapped in `agents/tools/registry.py`.

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

Role-facing default strings live in **`agents/roles/<role_id>/prompts.py`**; **`agents/prompts.py`** re-exports them for imports elsewhere. Prompt **templates** wired in graphs often live under **`config/prompts/`** (e.g. `workflow_designer.json`, `rl_coach.json`). After editing those sources, run:

`PYTHONPATH=. python agents/build_prompt_templates.py`

---

## Developer Guides

### How to add a new Role
1. Create a new folder in `agents/roles/<role_id>/`.
2. Add a `role.yaml` defining the `id`, `tools` list, and `follow_up_limit`.
3. (Optional) Add `prompts.py` for role-specific strings.
4. Add the role ID to `CHAT_MAIN_AGENT_ROLE_IDS` in `agents/roles/registry.py` to make it appear in the UI dropdown.

### How to add a new Tool
1. Create a tool implementation in `agents/tools/`.
2. Define the tool's `Action` models (Pydantic) for structured inputs.
3. Register the tool in `agents/tools/registry.py` (or ensure it is picked up by the automatic discovery mechanism).

---

## Quick Reference

| What | Where |
|------|-------|
| Role schema / loader | `agents/roles/types.py`, `agents/roles/registry.py` |
| Main Role IDs | `CHAT_MAIN_AGENT_ROLE_IDS` in `agents/roles/registry.py` |
| Tool Registry | `agents/tools/registry.py` |
| Tool Catalog | `agents/tools/catalog.py` |
| Agent Workflow Handlers | `agents/chat/role_turns/registry.py` |
