# agent tools (`agents/tools/`)

**Tools** are shared follow-up implementations (RAG, file reads, search, …) that any role can enable by listing stable string IDs in `role.yaml`. Workflow Designer follow-ups iterate `ORDERED_WORKFLOW_DESIGNER_TOOLS` and prefer a registry runner when one exists.

For the role side (YAML, chat wiring), see [roles/README.md](../roles/README.md).

---

## Creating a new tool (Agent follow-ups)

Agent parser output is normalized to a dict of lists/flags (`gui/utils/workflow_output_normalizer.normalize_follow_up_parser_output`). Each **tool** consumes one slice of that dict, keyed by a stable **parser key** (see catalog below).

### 1. Pick IDs and parser key

- **`tool_id`**: short snake_case name used in `role.yaml` and the registry (`read_file`, `grep`, …).
- **`parser_key`**: key on the normalized `parser_output` dict for that tool.

For Agent, add a row to `ORDERED_WORKFLOW_DESIGNER_TOOLS` in `agents/tools/catalog.py`. **Order is the execution order** for `_run_role_ordered_follow_ups` in `gui/chat/parser_follow_up/chain.py`.

Mirror the same order in `agents/roles/workflow_designer/role.yaml` under `tools:`.

Run `python scripts/test_role_tools.py` after changing catalog or role tools so the two stay aligned.

### 2. Implement the tool package

Create a package directory:

```text
agents/tools/<tool_id>/
  __init__.py   # exports the follow-up runner (and helpers if needed)
  prompt.py     # optional: TOOL_ACTION_PROMPT_LINE for the role "Extra actions" (see below)
  follow-ups.py # optional: <TOOL>_FOLLOW_UP_PREFIX, <TOOL>_FOLLOW_UP_SUFFIX and <TOOL>_FOLLOW_UP_USER_MESSAGE
```

### 2.1. Add the tool prompt lines
- In the tool `prompt.py` create this module-level string
`TOOL_ACTION_PROMPT_LINE`  - one bullet line descibing the JSON `action` the model emits to call the tool.

- Add extra lines for the context (optional):
In the `follow-ups.py`: 
`<TOOL>_FOLLOW_UP_PREFIX` - inserted in the context right above the tool output 
`<TOOL>_FOLLOW_UP_SUFFIX` - inserted in the context below the tool output 

LLM reads it as follows: 

```
<TOOL>_FOLLOW_UP_PREFIX
---
your tool output
---
<TOOL>_FOLLOW_UP_SUFFIX
```

`<TOOL>_FOLLOW_UP_USER_MESSAGE` - optionally set a custom user message, which is automatically appended for the user each follow-up turn (typically to make the model accomplish the task)

You must add the flag in the tool runner that tells the follow-up chain to use this message instead of dafault one (DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE).

Register the type in `/agents/tools/types.py` as `FOLLOW_UP_EXTRA_<YOUR_TOOL>_FOLLOW_UP = "<your_tool>_follow_up"`

- Register all the prompt lines in the `_WORKFLOW_DESIGNER_TOOL_FRAGMENT_MAP` inside the `follow_up_fragment_overrides.py`


- Insert the tool in the agent prompt `agents/roles/<role>/prompts.py` as `{tool: "your_tool_id"}` (or `{tool:your_tool_id}`). 

Note: Placeholders are expanded at import by
`agents.tools.prompt_lines.expand_tool_action_placeholders` (loads `prompt.py` by path to avoid import cycles).


### 2.3. Create the tool runner
The follow-up runner should live in __init__.py as an **async** callable compatible with:

```python
async def run_<name>_follow_up(ctx, po, *, language_hint) -> FollowUpContribution
```

- **`ctx`**: narrow context object from the follow-up chain (e.g. `agent_label`, optional status callbacks). Agent sets **`follow_up_source_response`** on `ParserFollowUpContext` each round so tool runners can read fields outside normalized `parser_output` (e.g. **`grep_output`** for grep).
- **`po`**: normalized parser output dict.
- **`language_hint`**: zero-argument callable returning the session language string for prompt suffixes.

Return `FollowUpContribution` from `agents/tools/types.py` (`context_chunks`, `any_empty_tool`, optional `extra`).

Pass the `extra` flag in order to enable custom user_message: 
```python
return FollowUpContribution(
        context_chunks=[chunk_ws],
        any_empty_tool=False,
        extra={FOLLOW_UP_EXTRA_YOUR_TOOL_FOLLOW_UP: True},
    )
```

**Do not** import roles or `get_role` from tool code; roles list tool IDs only.

### 3. Register the runner

In `agents/tools/registry.py`, inside `_ensure_builtin_follow_up_tools`, import your runner and assign:

```python
TOOL_RUNNERS["<tool_id>"] = run_<name>_follow_up
```

Callers resolve implementations with `get_follow_up_runner("<tool_id>")`.

### 4. Wire into the follow-up chain

Register the runner in `agents/tools/registry.py`. The ordered loop in `gui/chat/parser_follow_up/chain.py` calls it when `parser_output` includes your parser key. Use `FollowUpContribution.extra` with `FOLLOW_UP_EXTRA_READ_CODE_IDS` / `FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES` from `agents/tools/types.py` only if the orchestrator must update `read_code_ids_for_msg` or `implementation_links_for_types`.

Handle the extra user message in the follow up `chain.py`:

- Define you type to the `WDFollowUpAcc`:

```python
your_tool_follow_up: bool = False
```

- Add condition into `_merge_follow_up_contribution_into_acc`
```python
if ex.get(FOLLOW_UP_EXTRA_YOUR_TOOL_FOLLOW_UP):
        acc.your_tool_follow_up = True
```

- Wire into the `run_parser_output_follow_up_chain_async`: 
```python
calendar_follow_up = acc.your_tool_follow_up
...
elif calendar_follow_up:
    follow_up_msg = YOUR_TOOL_FOLLOW_UP_USER_MESSAGE.format(
        language=_hint(),
        session_language=_hint(),
    )
...
```

### 5. Tests

- `python scripts/test_role_tools.py` checks every `ORDERED_WORKFLOW_DESIGNER_TOOLS` id has a registered runner and that `workflow_designer/role.yaml` matches the catalog.
- After adding a tool: update `catalog.py`, `role.yaml`, the new package, and `registry.py`, then run the script.

---

## Quick reference (tools)

| What | Where |
|------|-------|
| Agent tool order + parser keys | `agents/tools/catalog.py` |
| Tool implementations | `agents/tools/<tool_id>/` |
| Runner registry | `agents/tools/registry.py` |
| WD follow-up orchestration | `gui/chat/parser_follow_up/` |
