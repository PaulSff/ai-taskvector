# Assistant roles (`assistants/roles/`)

A **role** describes who the assistant is: display name, optional intro text, ordered **tool** IDs (`tools:` in YAML), optional **chat** settings for the Flet assistants panel, and optional follow-up limits. The loader lives in `assistants/roles/registry.py`; types are in `assistants/roles/types.py`.

Built-in chat handlers for **workflow_designer**, **analyst**, and **rl_coach** live under `gui/chat/role_turns/<role_id>/` (see `gui/chat/role_turns/README.md`). Other roles can supply a dynamic handler via `chat.handler` in YAML (see below).

---

## Creating a new role

### 1. Add a role folder

Create `assistants/roles/<role_id>/` where `<role_id>` is the stable key you will pass to `get_role("<role_id>")` (for example `workflow_designer`, `rl_coach`).

### 2. Add `role.yaml`

Minimum shape:

```yaml
id: my_role          # must match the parent folder name
role_name: My Role   # short UI label (dropdown, settings)
name: Alex           # optional: human first name for prompts
introduction_words: |  # optional: opening self-intro for the system prompt (falls back to name + role_name)
  My name is Alex. I am the My Role assistant at TaskVector.

# Optional: machine-readable scope for routing / delegation (semantic analysis); not injected into chat prompts by default.
# responsibility_description: |
#   One or two sentences on what this role should and should not handle.

# Optional: cap parser follow-up rounds (Workflow Designer path reads this).
# follow_up_max_rounds: 5

# Ordered tool ids this role may use (strings only; no Python imports in YAML).
tools: []

# Optional: main Flet assistants chat (`list_chat_dropdown_role_ids`, `RoleConfig.chat`).
# chat:
#   enabled: true
#   workflow: my_workflow.json   # file in this role folder
#   features:
#     graph_canvas: true         # dev “Run current graph” (default true if omitted)
#     create_chat_title: true    # first-message create_filename workflow (default true)
#   # Only for roles other than workflow_designer / rl_coach (built-in handlers win):
#   handler: my_package.chat_handlers:MyRoleChatHandler   # or my_package.chat_handlers.MyRoleChatHandler

```

Rules enforced by the loader (`assistants/roles/registry.py`):

- **`id`** must equal the directory name.
- **`role_name`**: short UI label; legacy YAML may use **`display_name`** instead (treated as `role_name`).
- **`responsibility_description`**: optional plain text for semantic task delegation / routing (`RoleConfig.responsibility_description`); empty if omitted.
- **`tools`** is an ordered list of non-empty strings; unknown IDs are fine until you wire runners.
- **`chat`**: optional; when present, `enabled`, optional `workflow` filename, `features` booleans (see `role_chat_feature_enabled` in `assistants/roles/chat_config.py`; Flet uses `graph_canvas` for “Run current graph” and `create_chat_title` for the first-message `create_filename` workflow), and optional `handler` / `chat_handler` (string `module.path:ClassName` or `module.path.ClassName`; imported on demand, zero-arg constructor, instance `role_id` must match this role’s `id`). Roles not in `CHAT_MAIN_ASSISTANT_ROLE_IDS` need `chat.enabled: true` to appear in the dropdown.
- **`follow_up_max_rounds`**: omit to mean “use app settings”; if set, it is clamped to 1–50.
- Any other top-level keys are preserved on `RoleConfig.extra` for forward-compatible extensions.

### 3. Role prompts (optional)

Default system / fragment strings for a role can live in `assistants/roles/<role_id>/prompts.py`. The package root `assistants/prompts.py` re-exports known roles so the rest of the codebase keeps `from assistants.prompts import …`. Run `PYTHONPATH=. python scripts/write_prompt_templates.py` after editing Workflow Designer / RL Coach / Analyst / create-filename prompt sources.

### 4. Co-locate workflows (optional)

Put assistant-specific workflow JSON next to the role when the product expects it, for example:

- `assistants/roles/workflow_designer/workflow_designer_workflow.json`
- `assistants/roles/rl_coach/rl_coach_workflow.json`
- `assistants/roles/analyst/analyst_workflow.json`

For **Workflow Designer** and **RL Coach**, set `chat.workflow` in that role’s `role.yaml` (see `assistants.roles.get_role_chat_workflow_path`). Other assistant-related paths may still live in `gui/components/settings/` (package) / `app_settings.json` where the settings UI documents them.

**Workflow Designer** — chat graph path, how to run it, RAG merge, and I/O: **[`workflow_designer/README.md`](workflow_designer/README.md)**. Inject builders: `workflow_inputs.py`; shared runner: `gui/chat/assistant_workflow/run.py` (`run_assistant_workflow`).

**RL Coach** — chat graph, training injects, how to run it, and config save: **[`rl_coach/README.md`](rl_coach/README.md)**. Inject builders: `workflow_inputs.py`; loaders / `run_rl_coach_workflow`: `gui/chat/role_turns/rl_coach/workflow_runner.py` (delegates to `run_assistant_workflow`).

### 5. Wire the Flet assistants chat

`get_role` only loads YAML; the chat panel loads roles when building the dropdown and each turn.

1. **Dropdown**: `list_chat_dropdown_role_ids()` includes roles from `CHAT_MAIN_ASSISTANT_ROLE_IDS` that have `chat` enabled, then any other role with `chat.enabled: true`.
2. **Handler**: `get_role_chat_handler(role_id)` returns a `RoleChatHandler` (see `gui/chat/role_turns/protocol.py`). `workflow_designer`, `analyst`, and `rl_coach` use fixed implementations under `gui/chat/role_turns/<role_id>/`; for a **new** `role_id`, either add a built-in branch in `role_turns/registry.py` **or** set `chat.handler` / `chat.chat_handler` to a importable class that implements the protocol (`role_id`, `role_name`, `async run_turn(ctx, *, message_for_workflow)`). The class is instantiated with no arguments; dynamic instances are cached per `role_id` until `clear_dynamic_handler_cache()` (tests).
3. **Turn context**: `gui/chat/chat.py` builds `RoleChatTurnContext` from `get_role(role_id)` (limits, tools, workflow path, feature flags) and awaits `handler.run_turn(...)`.

Follow-up chains and tool runners for Workflow Designer use `role.yaml` `tools:` and `assistants/tools/registry.py`; see [tools/README.md](../tools/README.md).

---

## Quick reference (roles)

| What | Where |
|------|-------|
| Role schema / loader | `assistants/roles/types.py`, `assistants/roles/registry.py` |
| `chat:` parsing + `role_chat_feature_enabled` | `assistants/roles/chat_config.py` |
| Role prompt defaults | `assistants/roles/<id>/prompts.py`; re-export `assistants/prompts.py` |
| Example roles | `assistants/roles/workflow_designer/`, `rl_coach/`, … |
| Flet chat handler protocol + registry | `gui/chat/role_turns/README.md`, `…/protocol.py`, `…/registry.py` |
| Chat panel UI + turn dispatch | `gui/chat/chat.py` |
