# Assistants: roles and tools

**Roles** describe who the assistant is and which knobs apply (follow-up limits, ordered tool IDs in YAML `tools:`, optional `chat:` for the main Flet assistants panel). **Tools** (`assistants/tools/`) are shared follow-up implementations (RAG, file reads, search, …) that any role can enable by listing stable string IDs. Workflow Designer follow-ups iterate `ORDERED_WORKFLOW_DESIGNER_TOOLS` and prefer a registry runner when one exists.

The Flet chat panel resolves `role_id` with `get_role_chat_handler` in `gui/flet/chat_with_the_assistants/role_handlers/registry.py`: **Workflow Designer** and **RL Coach** are built-in; any other chat-enabled role can supply `chat.handler` / `chat.chat_handler` in YAML to load a `RoleChatHandler` on demand (see below).

Phased rollout and file inventory: [MIGRATION_ROLES_TOOLS.md](MIGRATION_ROLES_TOOLS.md).

---

## Creating a new role

### 1. Add a role folder

Create `assistants/roles/<role_id>/` where `<role_id>` is the stable key you will pass to `get_role("<role_id>")` (for example `workflow_designer`, `rl_coach`).

### 2. Add `role.yaml`

Minimum shape:

```yaml
id: my_role          # must match the parent folder name
display_name: My Role

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
- **`tools`** is an ordered list of non-empty strings; unknown IDs are fine until you wire runners.
- **`chat`**: optional; when present, `enabled`, optional `workflow` filename, `features` booleans (see `role_chat_feature_enabled` in `assistants/roles/chat_config.py`; Flet uses `graph_canvas` for “Run current graph” and `create_chat_title` for the first-message `create_filename` workflow), and optional `handler` / `chat_handler` (string `module.path:ClassName` or `module.path.ClassName`; imported on demand, zero-arg constructor, instance `role_id` must match this role’s `id`). Roles not in `CHAT_MAIN_ASSISTANT_ROLE_IDS` need `chat.enabled: true` to appear in the dropdown.
- **`follow_up_max_rounds`**: omit to mean “use app settings”; if set, it is clamped to 1–50.
- Any other top-level keys are preserved on `RoleConfig.extra` for forward-compatible extensions.

### 3. Role prompts (optional)

Default system / fragment strings for a role can live in `assistants/roles/<role_id>/prompts.py`. The package root `assistants/prompts.py` re-exports known roles so the rest of the codebase keeps `from assistants.prompts import …`. Run `PYTHONPATH=. python scripts/write_prompt_templates.py` after editing Workflow Designer / RL Coach / create-filename prompt sources.

### 4. Co-locate workflows (optional)

Put assistant-specific workflow JSON next to the role when the product expects it, for example:

- `assistants/roles/workflow_designer/assistant_workflow.json`
- `assistants/roles/rl_coach/rl_coach_workflow.json`

For **Workflow Designer** and **RL Coach**, set `chat.workflow` in that role’s `role.yaml` (see `assistants.roles.get_role_chat_workflow_path`). Other assistant-related paths may still live in `gui/flet/components/settings.py` / `app_settings.json` where the settings UI documents them.

Workflow Designer **inject initial inputs** for `assistant_workflow.json` live in `assistants/roles/workflow_designer/workflow_inputs.py` (`build_assistant_workflow_initial_inputs`, `default_wf_language_hint`); `gui/flet/chat_with_the_assistants/workflow_designer_handler.py` re-exports the builder and runs the graph.

RL Coach **inject initial inputs** for `rl_coach_workflow.json` live in `assistants/roles/rl_coach/workflow_inputs.py` (`build_rl_coach_initial_inputs`); `gui/flet/chat_with_the_assistants/rl_coach_handler.py` re-exports the builder and runs the graph (training-config loaders and overrides stay in the handler).

### 5. Wire the Flet assistants chat

`get_role` only loads YAML; the chat panel loads roles when building the dropdown and each turn.

1. **Dropdown**: `list_chat_dropdown_role_ids()` includes roles from `CHAT_MAIN_ASSISTANT_ROLE_IDS` that have `chat` enabled, then any other role with `chat.enabled: true`.
2. **Handler**: `get_role_chat_handler(role_id)` returns a `RoleChatHandler` (see `gui/flet/chat_with_the_assistants/role_handlers/protocol.py`). `workflow_designer` and `rl_coach` use fixed implementations in the registry; for a **new** `role_id`, either add a built-in branch in `role_handlers/registry.py` **or** set `chat.handler` / `chat.chat_handler` to a importable class that implements the protocol (`role_id`, `display_name`, `async run_turn(ctx, *, message_for_workflow)`). The class is instantiated with no arguments; dynamic instances are cached per `role_id` until `clear_dynamic_handler_cache()` (tests).
3. **Turn context**: `gui/flet/chat_with_the_assistants/chat.py` builds `RoleChatTurnContext` from `get_role(role_id)` (limits, tools, workflow path, feature flags) and awaits `handler.run_turn(...)`.

Follow-up chains and tool runners for Workflow Designer still use `role.yaml` `tools:` and `assistants/tools/registry.py` as in the sections below.

---

## Creating a new tool (Workflow Designer follow-ups)

Workflow Designer parser output is normalized to a dict of lists/flags (`gui/flet/tools/workflow_output_normalizer.normalize_follow_up_parser_output`). Each **tool** consumes one slice of that dict, keyed by a stable **parser key** (see catalog below).

### 1. Pick IDs and parser key

- **`tool_id`**: short snake_case name used in `role.yaml` and the registry (`read_file`, `grep`, …).
- **`parser_key`**: key on the normalized `parser_output` dict for that tool.

For Workflow Designer, add a row to `ORDERED_WORKFLOW_DESIGNER_TOOLS` in `assistants/tools/catalog.py`. **Order is the execution order** for `_run_workflow_designer_ordered_follow_ups` in `workflow_designer_followups.py`.

Mirror the same order in `assistants/roles/workflow_designer/role.yaml` under `tools:`.

Run `python scripts/test_role_tools.py` after changing catalog or role tools so the two stay aligned.

### 2. Implement the tool package

Create a package directory:

```text
assistants/tools/<tool_id>/
  __init__.py   # exports the follow-up runner (and helpers if needed)
  prompt.py     # optional: TOOL_ACTION_PROMPT_LINE for Workflow Designer "Extra actions" (see below)
```

If the tool appears in the Workflow Designer system prompt, add `prompt.py` with a module-level string
`TOOL_ACTION_PROMPT_LINE` (one bullet line, same wording as the JSON `action` the model emits). Register it in
`assistants/roles/workflow_designer/prompts.py` inside `_WORKFLOW_DESIGNER_SYSTEM_RAW` using a placeholder
`{tool: "your_tool_id"}` (or `{tool:your_tool_id}`). Placeholders are expanded at import by
`assistants.tools.prompt_lines.expand_tool_action_placeholders` (loads `prompt.py` by path to avoid import cycles).

The follow-up runner should be an **async** callable compatible with:

```python
async def run_<name>_follow_up(ctx, po, *, language_hint) -> FollowUpContribution
```

- **`ctx`**: narrow context object from the follow-up chain (e.g. `assistant_label`, optional status callbacks). Workflow Designer sets **`follow_up_source_response`** on `ParserFollowUpContext` each round so tool runners can read fields outside normalized `parser_output` (e.g. **`grep_output`** for grep).
- **`po`**: normalized parser output dict.
- **`language_hint`**: zero-argument callable returning the session language string for prompt suffixes.

Return `FollowUpContribution` from `assistants/tools/types.py` (`context_chunks`, `any_empty_tool`, optional `extra`).

**Do not** import roles or `get_role` from tool code; roles list tool IDs only.

### 3. Register the runner

In `assistants/tools/registry.py`, inside `_ensure_builtin_follow_up_tools`, import your runner and assign:

```python
TOOL_RUNNERS["<tool_id>"] = run_<name>_follow_up
```

Callers resolve implementations with `get_follow_up_runner("<tool_id>")`.

### 4. Wire into the follow-up chain

Register the runner in `assistants/tools/registry.py`. The ordered loop in `workflow_designer_followups.py` calls it when `parser_output` includes your parser key. Use `FollowUpContribution.extra` with `FOLLOW_UP_EXTRA_READ_CODE_IDS` / `FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES` from `assistants/tools/types.py` only if the orchestrator must update `read_code_ids_for_msg` or `implementation_links_for_types` (same pattern as `read_code_block`).

### 5. Tests

- `python scripts/test_role_tools.py` checks every `ORDERED_WORKFLOW_DESIGNER_TOOLS` id has a registered runner and that `workflow_designer/role.yaml` matches the catalog.
- After adding a tool: update `catalog.py`, `role.yaml`, the new package, and `registry.py`, then run the script.

---

## Quick reference

| What | Where |
|------|-------|
| Role schema / loader | `assistants/roles/types.py`, `assistants/roles/registry.py` |
| `chat:` parsing + `role_chat_feature_enabled` | `assistants/roles/chat_config.py` |
| Role prompt defaults | `assistants/roles/<id>/prompts.py`; re-export `assistants/prompts.py` |
| Example roles | `assistants/roles/workflow_designer/`, `rl_coach/`, … |
| Flet chat handler protocol + registry | `gui/flet/chat_with_the_assistants/role_handlers/protocol.py`, `…/registry.py` |
| Chat panel UI + turn dispatch | `gui/flet/chat_with_the_assistants/chat.py` |
| WD tool order + parser keys | `assistants/tools/catalog.py` |
| Tool implementations | `assistants/tools/<tool_id>/` |
| Runner registry | `assistants/tools/registry.py` |
| WD follow-up orchestration | `gui/flet/chat_with_the_assistants/workflow_designer_followups.py` |
