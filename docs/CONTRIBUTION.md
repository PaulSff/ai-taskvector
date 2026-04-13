# Contribution guidelines

Thanks for helping improve AI TaskVector. This document describes how we expect changes to be proposed and structured so they stay reviewable and aligned with the architecture.

## Before you start

- Read the root **[README.md](../README.md)** for setup, Python version, and optional installs (GUI, RAG, unit extras).
- **Python:** use **3.10–3.12** (see `requirements.txt`; PyTorch wheels may not support newer Python yet).
- **License:** contributions are accepted under the same terms as the project ([MIT](../LICENSE)).

## Architecture at a glance

Keep boundaries in mind when choosing where code belongs:

| Area | Responsibility |
|------|----------------|
| **`core/`** | Canonical graph and training-config models, normalization, graph edits—single source of truth. |
| **`runtime/`** | Executing workflow JSON and wiring units to Core. |
| **`units/`** | Unit implementations invoked by the runtime. |
| **`gui/`** | Flet UI; prefer reaching Core via packaged workflows under `gui/components/workflow_tab/workflows/` instead of duplicating graph logic. |
| **`rag/`** | Indexing and retrieval; optional deps in `rag/requirements.txt`. |
| **`assistants/`** | Roles, tools, prompts for Workflow Designer / RL Coach. |

More detail: **`core/README.md`**, **`runtime/README.md`**, **`gui/components/workflow_tab/README.md`**.

## Pull requests

- **Scope:** one coherent change per PR (feature, fix, or doc update). Avoid mixing unrelated refactors with behavior changes.
- **Size:** smaller diffs are easier to review. If a large change is necessary, split it or explain the sequence in the PR description.
- **Description:** state **what** changed and **why** in full sentences. Link issues if applicable.
- **Breaking changes:** call them out explicitly and note any migration steps.

## Code style

- **Match the surrounding file:** imports, naming, typing, and comment density should look like the rest of the module.
- **Focused edits:** do not reformat or rename unrelated code. Every line in the diff should support the stated goal.
- **Types:** use type hints where the file already does; follow existing `Optional` / `|` union style.
- **Dependencies:** new libraries belong in the appropriate `requirements.txt` (root, `gui/`, `rag/`, or unit-specific) with a short comment if non-obvious.

## Tests and manual checks

There is no single unified test runner documented here; the repo uses scripts and modules under **`scripts/`**. Before opening a PR:

- Run any script or workflow that exercises your change (e.g. `scripts/test_assistants.py`, `python -m gui.main` for GUI touches, `python -m runtime …` for workflow changes) and mention what you ran in the PR.
- If you add automated tests, place them consistently with existing patterns in the tree and document how to run them in the PR.

## Documentation

- Update **README** or **package READMEs** when you change install steps, public entry points, or user-visible behavior.
- Prefer linking to existing docs under **`docs/`** and **`core/`** / **`runtime/`** rather than duplicating long explanations.

## Security and config

- **Do not commit** API keys, tokens, personal paths, or large binary artifacts.
- Use **`config/`** examples and environment variables as documented; keep secrets in local untracked files or your environment.

## Commits

- Prefer **clear, imperative** subject lines (`Fix load dialog path`, `Add RAG tab empty state`).
- Optional: multiple small commits per PR are fine; maintainers may squash on merge depending on project practice.

## Getting help

- Open an issue for design questions or ambiguous requirements before investing in a large implementation.
- Refer to **`docs/REWARD_RULES.md`**, **`docs/PROCESS_GRAPH_TOPOLOGY.md`**, and **`docs/DEPLOYMENT_NODERED.md`** when touching rewards, graph topology, or Node-RED deployment.
