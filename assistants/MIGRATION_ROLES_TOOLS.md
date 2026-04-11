# Migration: roles + tools for assistants

**How to add a new role or tool:** see [README.md](README.md) in this folder.

## Goals

- **Roles** (`assistants/roles/<role_id>/`): per-assistant identity — display metadata, optional follow-up limits, ordered **tool allowlist** in YAML (Workflow Designer uses it; RL Coach lists `tools: []` until follow-ups are wired), role prompts under `roles/<id>/prompts.py`.
- **Tools** (`assistants/tools/`): reusable follow-up implementations (read_file, rag_search, web_search, …) with one package shared by every role that enables them via YAML `tools:`.
- **Chat / handlers** stay thin: resolve `role_id` → `get_role(role_id)` → pass limits and (for Workflow Designer) the ordered tool follow-up loop; RL Coach has no parser-output follow-up chain yet.

## Flet assistants chat (registry-driven)

**Done**

- Optional `chat:` block in each `role.yaml` (parsed into `RoleConfig.chat` / `RoleChatConfig`): `enabled`, `workflow` (filename under the role folder), `features` (booleans; Flet chat honors `graph_canvas` and `create_chat_title` via `assistants.roles.role_chat_feature_enabled`), optional `handler` / `chat_handler` (`module.path:ClassName` for a third-party `RoleChatHandler` loaded by `get_role_chat_handler` after built-ins).
- `list_chat_dropdown_role_ids()` builds the main chat dropdown: primary order from `CHAT_MAIN_ASSISTANT_ROLE_IDS` when enabled, then any other role with `chat.enabled: true`.
- `gui/flet/chat_with_the_assistants/chat.py` resolves **`profile` (`role_id` snake_case)**, calls **`get_role_chat_handler(profile)`**, builds **`RoleChatTurnContext`**, then **`await handler.run_turn(turn_ctx, …)`**. Unknown roles get a clear in-chat error.
- **`role_handlers/`**: `protocol.RoleChatHandler`, `context.RoleChatTurnContext`, `registry.get_role_chat_handler`, `workflow_designer.WorkflowDesignerChatHandler`, `rl_coach.RlCoachChatHandler` (see `gui/flet/chat_with_the_assistants/plan.md` for later phases).

**Still evolving**

- **Pure vs Flet split**: keep workflow/input shapes under `assistants/roles/<id>/`; Flet + streaming stays under `gui/flet/chat_with_the_assistants/role_handlers/<id>.py` and `workflow_designer_followups.py` until more logic moves.

## Current state (baseline)

- **Workflow Designer**: `run_parser_output_follow_up_chain` walks `ORDERED_WORKFLOW_DESIGNER_TOOLS` and invokes each registered `get_follow_up_runner(tool_id)`; orchestration-only code stays in `workflow_designer_followups.py`. `WorkflowDesignerChatHandler` sets `max_rounds` from role YAML or `get_workflow_designer_max_follow_ups()`.
- **RL Coach**: no parser follow-up chain; different workflow (`rl_coach_workflow.json`). `role.yaml` declares `tools: []` until follow-ups are wired (Phase 4).
- **Parser normalization**: `gui/flet/tools/workflow_output_normalizer.normalize_follow_up_parser_output`.

## Phases

### Phase 0 — Scaffold (this PR)

- [x] Add `assistants/roles/` with `role.yaml` per role and `registry.get_role(role_id)`.
- [x] Add `assistants/tools/` package stub (`types`, empty `registry`) for upcoming modules.
- [x] Document phases in this file.
- [x] Wire **Workflow Designer** follow-up `max_rounds`: `role.follow_up_max_rounds` if set in YAML, else existing `get_workflow_designer_max_follow_ups()`.

### Phase 1 — Tool IDs on roles (no behavior change)

- [x] Add ordered `tools:` to `workflow_designer/role.yaml` (canonical list in `assistants/tools/catalog.py`).
- [x] Chat passes `workflow_designer` role `tools:` as the follow-up allowlist (`ParserFollowUpContext.follow_up_tool_ids`).
- [x] `python scripts/test_role_tools.py` asserts role tools match catalog (run in CI or locally).

### Phase 2 — Extract first tool

- [x] `assistants/tools/read_file/`: RAG + optional .xlsx tables → `FollowUpContribution`; registered via `get_follow_up_runner("read_file")`.
- [x] `workflow_designer_followups` delegates read_file to runner; on missing runner / exception, empty-result chunk (same UX as before).

### Phase 3 — Generic runner

- [x] `run_parser_output_follow_up_chain` uses `ORDERED_WORKFLOW_DESIGNER_TOOLS` and registered runners only; merges `FollowUpContribution.extra` for `read_code_block` (`read_code_ids_for_msg`, `implementation_links_for_types`).
- [x] All Workflow Designer follow-up tools live under `assistants/tools/<tool_id>/` and are registered in `registry.py`.
- [x] Removed `use_legacy_followups` from `RoleConfig` / role YAML (ignored key still stripped in loader `known` set for older files).

### Phase 4 — RL Coach and prompts

- [x] **`rl_coach/role.yaml` `tools:`** — Explicitly `[]`. RL Coach uses `rl_coach_workflow.json` only (Inject → RAG → …); there is no Workflow Designer–style parser-output follow-up chain or `ParserFollowUpContext.follow_up_tool_ids` for this role today. When product wants shared tool follow-ups for RL Coach, add the same string ids as in `assistants/tools/catalog.py` and wire chat to a runner loop (parallel to WD).
- [x] Role-specific default prompts live in `assistants/roles/<role_id>/prompts.py` (`workflow_designer`, `rl_coach`, `chat_name_creator`). `assistants/prompts.py` re-exports them, loads optional `workflow_designer.json` `fragments`, applies role overrides via `apply_workflow_designer_role_fragments` in `roles/workflow_designer/prompts.py`, applies tool follow-up overrides via `apply_workflow_designer_json_tool_fragments`, and keeps `get_fragment` / JSON loaders. `scripts/write_prompt_templates.py` still imports via `assistants.prompts`.

**Phases 0–4 in this document are complete.** Headless apply tests use `gui/flet/components/workflow/core_workflows.py` (`run_apply_edits` / `run_apply_training_config_edits`); there is no `python -m assistants` CLI.

## Assistant workflow JSON layout

Workflow graphs for the main Workflow Designer / RL Coach chat live under each role directory; the path is **`chat.workflow`** in `assistants/roles/<role_id>/role.yaml` (resolved by `assistants.roles.get_role_chat_workflow_path`). Other tool workflows (create filename, RAG context, …) may still be configured in `config/app_settings.json` where noted in settings UI.

## Conventions

- **Role IDs** match chat profile keys where wired: `workflow_designer`, `rl_coach` (see `chat._assistant_profile_key`). Additional roles exist for registry / future UI: `chat_name_creator` (create_filename / chat title), `analyst` (placeholder).
- **Tool packages** must not import roles; roles list tool IDs as strings only.
- **Breaking changes**: extend parser JSON only with backward-compatible keys; tools read normalized `po` from `normalize_follow_up_parser_output`.

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
| `assistants/prompts.py` | JSON loaders, `get_fragment`, WD `fragments` load + role/tool appliers; re-exports role `prompts.py` |
| `assistants/tools/follow_up_common.py` | Shared tool follow-up lines (`TOOL_EMPTY_*`, session-language suffix) |
| `assistants/tools/follow_up_fragment_overrides.py` | Maps WD JSON `fragments` keys → per-tool `follow_ups` module attributes |
| `assistants/tools/types.py` | Shared types / protocols for tools |
| `assistants/tools/catalog.py` | WD follow-up tool ids + parser key map |
| `assistants/tools/registry.py` | `TOOL_RUNNERS`, `get_follow_up_runner`, lazy builtins |
| `assistants/tools/read_code_block/` | read_code_block follow-up (graph todos + RAG for missing blocks) |
| `assistants/tools/run_workflow/` | run_workflow follow-up (`run_output`) |
| `assistants/tools/grep/` | grep follow-up (`grep_output`) |
| `assistants/tools/read_file/` | read_file (RAG + .xlsx tables) |
| `assistants/tools/rag_search/` | rag_search follow-up |
| `assistants/tools/web_search/` | web_search follow-up |
| `assistants/tools/browse/` | browse follow-up (`browse_url`) |
| `assistants/tools/github/` | github follow-up |
| `assistants/tools/report/` | report follow-up (`report_output`) |
| `scripts/test_role_tools.py` | Catalog ↔ `role.yaml` + every catalog tool has a runner |
| `gui/flet/components/workflow/core/apply_edits_single.json` | ApplyEdits unit workflow (WD apply path; `core_workflows.run_apply_edits`) |
| `gui/flet/components/workflow/core/apply_training_config_edits_single.json` | ApplyTrainingConfigEdits workflow (`core_workflows.run_apply_training_config_edits`) |
| `scripts/test_assistants.py` | Graph + training apply via those workflows (see README) |
