# Assistants: roles and skills

**Roles** describe who the assistant is and which knobs apply (follow-up limits, ordered skill IDs). **Skills** are shared implementations of tools (RAG, file reads, search, …) that any role can enable by listing stable string IDs. Workflow Designer follow-ups iterate `ORDERED_WORKFLOW_DESIGNER_SKILLS` and prefer a registry runner when one exists.

Phased rollout and file inventory: [MIGRATION_ROLES_SKILLS.md](MIGRATION_ROLES_SKILLS.md).

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

# Ordered skill ids this role may use (strings only; no Python imports in YAML).
skills: []

```

Rules enforced by the loader (`assistants/roles/registry.py`):

- **`id`** must equal the directory name.
- **`skills`** is an ordered list of non-empty strings; unknown IDs are fine until you wire runners.
- **`follow_up_max_rounds`**: omit to mean “use app settings”; if set, it is clamped to 1–50.
- Any other top-level keys are preserved on `RoleConfig.extra` for forward-compatible extensions.

### 3. Role prompts (optional)

Default system / fragment strings for a role can live in `assistants/roles/<role_id>/prompts.py`. The package root `assistants/prompts.py` re-exports known roles so the rest of the codebase keeps `from assistants.prompts import …`. Run `PYTHONPATH=. python scripts/write_prompt_templates.py` after editing Workflow Designer / RL Coach / create-filename prompt sources.

### 4. Co-locate workflows (optional)

Put assistant-specific workflow JSON next to the role when the product expects it, for example:

- `assistants/roles/workflow_designer/assistant_workflow.json`
- `assistants/roles/rl_coach/rl_coach_workflow.json`

If the GUI has a default path for that assistant, update the settings helper (see `gui/flet/components/settings.py`) and, if needed, a legacy path remap for older saved `app_settings.json` values.

### 5. Wire the chat / GUI

`get_role` only loads YAML; nothing runs until something calls it. Today `workflow_designer` is read in `gui/flet/chat_with_the_assistants/chat.py` for follow-up limits and skill lists. For a **new** assistant profile, you still need to hook the same pattern: resolve the profile’s `role_id`, call `get_role(role_id)`, and pass the fields your follow-up path expects.

---

## Creating a new skill (Workflow Designer follow-ups)

Workflow Designer parser output is normalized to a dict of lists/flags (`gui/flet/tools/workflow_output_normalizer.normalize_follow_up_parser_output`). Each **skill** consumes one slice of that dict, keyed by a stable **parser key** (see catalog below).

### 1. Pick IDs and parser key

- **`skill_id`**: short snake_case name used in `role.yaml` and the registry (`read_file`, `grep`, …).
- **`parser_key`**: key on the normalized `parser_output` dict for that tool.

For Workflow Designer, add a row to `ORDERED_WORKFLOW_DESIGNER_SKILLS` in `assistants/skills/catalog.py`. **Order is the execution order** for `_run_workflow_designer_ordered_follow_ups` in `workflow_designer_followups.py`.

Mirror the same order in `assistants/roles/workflow_designer/role.yaml` under `skills:`.

Run `python scripts/test_role_skills.py` after changing catalog or role skills so the two stay aligned.

### 2. Implement the skill package

Create a package directory:

```text
assistants/skills/<skill_id>/
  __init__.py   # exports the follow-up runner (and helpers if needed)
```

The follow-up runner should be an **async** callable compatible with:

```python
async def run_<skill>_follow_up(ctx, po, *, language_hint) -> FollowUpContribution
```

- **`ctx`**: narrow context object from the follow-up chain (e.g. `assistant_label`, optional status callbacks). Workflow Designer sets **`follow_up_source_response`** on `ParserFollowUpContext` each round so skills can read fields outside normalized `parser_output` (e.g. **`grep_output`** for grep).
- **`po`**: normalized parser output dict.
- **`language_hint`**: zero-argument callable returning the session language string for prompt suffixes.

Return `FollowUpContribution` from `assistants/skills/types.py` (`context_chunks`, `any_empty_tool`, optional `extra`).

**Do not** import roles or `get_role` from skill code; roles list skill IDs only.

### 3. Register the runner

In `assistants/skills/registry.py`, inside `_ensure_builtin_follow_up_skills`, import your runner and assign:

```python
SKILLS["<skill_id>"] = run_<skill>_follow_up
```

Callers resolve implementations with `get_follow_up_runner("<skill_id>")`.

### 4. Wire into the follow-up chain

Register the runner in `assistants/skills/registry.py`. The ordered loop in `workflow_designer_followups.py` calls it when `parser_output` includes your parser key. Use `FollowUpContribution.extra` with `FOLLOW_UP_EXTRA_READ_CODE_IDS` / `FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES` from `assistants/skills/types.py` only if the orchestrator must update `read_code_ids_for_msg` or `implementation_links_for_types` (same pattern as `read_code_block`).

### 5. Tests

- `python scripts/test_role_skills.py` checks every `ORDERED_WORKFLOW_DESIGNER_SKILLS` id has a registered runner and that `workflow_designer/role.yaml` matches the catalog.
- After adding a skill: update `catalog.py`, `role.yaml`, the new package, and `registry.py`, then run the script.

---

## Quick reference

| What | Where |
|------|--------|
| Role schema / loader | `assistants/roles/types.py`, `assistants/roles/registry.py` |
| Role prompt defaults | `assistants/roles/<id>/prompts.py`; re-export `assistants/prompts.py` |
| Example roles | `assistants/roles/workflow_designer/`, `rl_coach/`, … |
| WD skill order + parser keys | `assistants/skills/catalog.py` |
| Skill implementations | `assistants/skills/<skill_id>/` |
| Runner registry | `assistants/skills/registry.py` |
| WD follow-up orchestration | `gui/flet/chat_with_the_assistants/workflow_designer_followups.py` |
