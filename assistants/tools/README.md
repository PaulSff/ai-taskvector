# Assistant tools (`assistants/tools/`)

**Tools** are shared follow-up implementations (RAG, file reads, search, …) that any role can enable by listing stable string IDs in `role.yaml`. Workflow Designer follow-ups iterate `ORDERED_WORKFLOW_DESIGNER_TOOLS` and prefer a registry runner when one exists.

For the role side (YAML, chat wiring), see [roles/README.md](../roles/README.md).

---

## Creating a new tool (Workflow Designer follow-ups)

Workflow Designer parser output is normalized to a dict of lists/flags (`gui/utils/workflow_output_normalizer.normalize_follow_up_parser_output`). Each **tool** consumes one slice of that dict, keyed by a stable **parser key** (see catalog below).

### 1. Pick IDs and parser key

- **`tool_id`**: short snake_case name used in `role.yaml` and the registry (`read_file`, `grep`, …).
- **`parser_key`**: key on the normalized `parser_output` dict for that tool.

For Workflow Designer, add a row to `ORDERED_WORKFLOW_DESIGNER_TOOLS` in `assistants/tools/catalog.py`. **Order is the execution order** for `_run_workflow_designer_ordered_follow_ups` in `gui/chat/parser_follow_up/chain.py`.

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

Register the runner in `assistants/tools/registry.py`. The ordered loop in `gui/chat/parser_follow_up/chain.py` calls it when `parser_output` includes your parser key. Use `FollowUpContribution.extra` with `FOLLOW_UP_EXTRA_READ_CODE_IDS` / `FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES` from `assistants/tools/types.py` only if the orchestrator must update `read_code_ids_for_msg` or `implementation_links_for_types` (same pattern as `read_code_block`).

### 5. Tests

- `python scripts/test_role_tools.py` checks every `ORDERED_WORKFLOW_DESIGNER_TOOLS` id has a registered runner and that `workflow_designer/role.yaml` matches the catalog.
- After adding a tool: update `catalog.py`, `role.yaml`, the new package, and `registry.py`, then run the script.

---

## Quick reference (tools)

| What | Where |
|------|-------|
| WD tool order + parser keys | `assistants/tools/catalog.py` |
| Tool implementations | `assistants/tools/<tool_id>/` |
| Runner registry | `assistants/tools/registry.py` |
| WD follow-up orchestration | `gui/chat/parser_follow_up/` |
