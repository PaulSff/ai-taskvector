# Migration: roles + skills for assistants

**How to add a new role or skill:** see [README.md](README.md) in this folder.

## Goals

- **Roles** (`assistants/roles/<role_id>/`): per-assistant identity — display metadata, optional follow-up limits, ordered **skill allowlist** in YAML (Workflow Designer uses it; RL Coach lists `skills: []` until follow-ups are wired), role prompts under `roles/<id>/prompts.py`.
- **Skills** (`assistants/skills/`): reusable tools (read_file, rag_search, web_search, …) with one implementation shared by every role that enables them.
- **Chat / handlers** stay thin: resolve `role_id` → `get_role(role_id)` → pass limits and (for Workflow Designer) the ordered skill follow-up loop; RL Coach has no parser-output follow-up chain yet.

## Current state (baseline)

- **Workflow Designer**: `run_parser_output_follow_up_chain` walks `ORDERED_WORKFLOW_DESIGNER_SKILLS` and invokes each registered `get_follow_up_runner(skill_id)`; orchestration-only code stays in `workflow_designer_followups.py`. `chat.py` sets `max_rounds` from role YAML or `get_workflow_designer_max_follow_ups()`.
- **RL Coach**: no parser follow-up chain; different workflow (`rl_coach_workflow.json`). `role.yaml` declares `skills: []` until follow-ups are wired (Phase 4).
- **Parser normalization**: `gui/flet/tools/workflow_output_normalizer.normalize_follow_up_parser_output`.

## Phases

### Phase 0 — Scaffold (this PR)

- [x] Add `assistants/roles/` with `role.yaml` per role and `registry.get_role(role_id)`.
- [x] Add `assistants/skills/` package stub (`types`, empty `registry`) for upcoming modules.
- [x] Document phases in this file.
- [x] Wire **Workflow Designer** follow-up `max_rounds`: `role.follow_up_max_rounds` if set in YAML, else existing `get_workflow_designer_max_follow_ups()`.

### Phase 1 — Skill IDs on roles (no behavior change)

- [x] Add ordered `skills:` to `workflow_designer/role.yaml` (canonical list in `assistants/skills/catalog.py`).
- [x] Chat passes `workflow_designer` role `skills:` as the follow-up allowlist (`ParserFollowUpContext.follow_up_skill_ids`).
- [x] `python scripts/test_role_skills.py` asserts role skills match catalog (run in CI or locally).

### Phase 2 — Extract first skill

- [x] `assistants/skills/read_file/`: RAG + optional .xlsx tables → `FollowUpContribution`; registered via `get_follow_up_runner("read_file")`.
- [x] `workflow_designer_followups` delegates read_file to runner; on missing runner / exception, empty-result chunk (same UX as before).

### Phase 3 — Generic runner

- [x] `run_parser_output_follow_up_chain` uses `ORDERED_WORKFLOW_DESIGNER_SKILLS` and registered runners only; merges `FollowUpContribution.extra` for `read_code_block` (`read_code_ids_for_msg`, `implementation_links_for_types`).
- [x] All Workflow Designer follow-up tools live under `assistants/skills/<skill_id>/` and are registered in `registry.py`.
- [x] Removed `use_legacy_followups` from `RoleConfig` / role YAML (ignored key still stripped in loader `known` set for older files).

### Phase 4 — RL Coach and prompts

- [x] **`rl_coach/role.yaml` `skills:`** — Explicitly `[]`. RL Coach uses `rl_coach_workflow.json` only (Inject → RAG → …); there is no Workflow Designer–style parser-output follow-up chain or `ParserFollowUpContext.follow_up_skill_ids` for this role today. When product wants shared tool follow-ups for RL Coach, add the same string ids as in `assistants/skills/catalog.py` and wire chat to a runner loop (parallel to WD).
- [x] Role-specific default prompts live in `assistants/roles/<role_id>/prompts.py` (`workflow_designer`, `rl_coach`, `chat_name_creator`). `assistants/prompts.py` re-exports them, loads optional `workflow_designer.json` `fragments`, applies role overrides via `apply_workflow_designer_role_fragments` in `roles/workflow_designer/prompts.py`, applies skill follow-up overrides via `apply_workflow_designer_json_skill_fragments`, and keeps `get_fragment` / JSON loaders. `scripts/write_prompt_templates.py` still imports via `assistants.prompts`.

**Phases 0–4 in this document are complete.** Headless apply tests use `gui/flet/components/workflow/core_workflows.py` (`run_apply_edits` / `run_apply_training_config_edits`); there is no `python -m assistants` CLI.

## Assistant workflow JSON layout

Workflow graphs for chat assistants live next to each role under `assistants/roles/<role_id>/`. App defaults point there; saved `app_settings.json` paths that still use the old `assistants/*.json` locations are remapped in `get_assistant_workflow_path`, `get_create_filename_workflow_path`, and `get_rl_coach_workflow_path`.

## Conventions

- **Role IDs** match chat profile keys where wired: `workflow_designer`, `rl_coach` (see `chat._assistant_profile_key`). Additional roles exist for registry / future UI: `chat_name_creator` (create_filename / chat title), `analyst` (placeholder).
- **Skills** must not import roles; roles list skill IDs as strings only.
- **Breaking changes**: extend parser JSON only with backward-compatible keys; skills read normalized `po` from `normalize_follow_up_parser_output`.

## Files

| Path | Purpose |
|------|---------|
| `assistants/roles/types.py` | `RoleConfig` dataclass |
| `assistants/roles/registry.py` | `get_role`, load/cache YAML |
| `assistants/roles/workflow_designer/prompts.py` | Workflow Designer default prompt strings + `apply_workflow_designer_role_fragments` (re-exported from `assistants.prompts`) |
| `assistants/roles/workflow_designer/role.yaml` | WD role config |
| `assistants/roles/workflow_designer/assistant_workflow.json` | Workflow Designer graph (was `assistants/assistant_workflow.json`) |
| `assistants/roles/rl_coach/rl_coach_workflow.json` | RL Coach workflow (was `assistants/rl_coach_workflow.json`) |
| `assistants/roles/chat_name_creator/create_filename.json` | Chat title workflow (was `assistants/create_filename.json`) |
| `assistants/roles/rl_coach/prompts.py` | RL Coach default prompt strings |
| `assistants/roles/rl_coach/role.yaml` | RL Coach role config |
| `assistants/roles/chat_name_creator/prompts.py` | create_filename system prompt default |
| `assistants/roles/chat_name_creator/role.yaml` | Chat title / create_filename persona |
| `assistants/roles/analyst/role.yaml` | Analyst persona (placeholder) |
| `assistants/prompts.py` | JSON loaders, `get_fragment`, WD `fragments` load + role/skill appliers; re-exports role `prompts.py` |
| `assistants/skills/follow_up_common.py` | Shared tool follow-up lines (`TOOL_EMPTY_*`, session-language suffix) |
| `assistants/skills/follow_up_fragment_overrides.py` | Maps WD JSON `fragments` keys → skill `follow_ups` module attributes |
| `assistants/skills/types.py` | Shared types / protocols for skills |
| `assistants/skills/catalog.py` | WD follow-up skill ids + parser key map |
| `assistants/skills/registry.py` | `SKILLS`, `get_follow_up_runner`, lazy builtins |
| `assistants/skills/read_code_block/` | read_code_block follow-up (graph todos + RAG for missing blocks) |
| `assistants/skills/run_workflow/` | run_workflow follow-up (`run_output`) |
| `assistants/skills/grep/` | grep follow-up (`grep_output`) |
| `assistants/skills/read_file/` | read_file (RAG + .xlsx tables) |
| `assistants/skills/rag_search/` | rag_search follow-up |
| `assistants/skills/web_search/` | web_search follow-up |
| `assistants/skills/browse/` | browse follow-up (`browse_url`) |
| `assistants/skills/github/` | github follow-up |
| `assistants/skills/report/` | report follow-up (`report_output`) |
| `scripts/test_role_skills.py` | Catalog ↔ `role.yaml` + every catalog skill has a runner |
| `gui/flet/components/workflow/core/apply_edits_single.json` | ApplyEdits unit workflow (WD apply path; `core_workflows.run_apply_edits`) |
| `gui/flet/components/workflow/core/apply_training_config_edits_single.json` | ApplyTrainingConfigEdits workflow (`core_workflows.run_apply_training_config_edits`) |
| `scripts/test_assistants.py` | Graph + training apply via those workflows (see README) |
