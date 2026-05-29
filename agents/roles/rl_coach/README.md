# RL Coach role

The **RL Coach** is the TaskVector agent for **RL training configuration**: goals, reward design (presets, formulas, rules), algorithm choice, and hyperparameters. It proposes or applies **declarative edits** to the training config (YAML/JSON). It does **not** edit `runtime/train.py` or hand-written reward Python; the training runtime reads the merged config file.

| Item | Location |
|------|----------|
| Role config (`tools`, `chat`, LLM defaults) | `agents/roles/rl_coach/role.yaml` |
| Chat process graph (canonical JSON) | `agents/roles/rl_coach/rl_coach_workflow.json` |
| `initial_inputs` builders (headless-friendly) | `agents/roles/rl_coach/workflow_inputs.py` — `build_rl_coach_initial_inputs`, `build_rl_coach_training_inject_updates`, `build_rl_coach_agent_aligned_initial_inputs` (WD-aligned graph + training injects) |
| Default system prompt text | `agents/prompts.py` → `RL_COACH_SYSTEM`; template path often `config/prompts/rl_coach.json` (overridable via settings / `build_rl_coach_unit_param_overrides`) |
| Flet chat turn (stream, save config, toasts) | `gui/chat/role_turns/rl_coach/` — `handler.py` |
| Training summary / dict loaders, overrides, `run_rl_coach_workflow` | `gui/chat/role_turns/rl_coach/workflow_runner.py` |
| Shared JSON runner | `gui/chat/agent_workflow/run.py` → `run_agent_workflow()` |

Resolve the workflow file with `agents.roles.workflow_path.get_role_chat_workflow_path` (`RL_COACH_ROLE_ID` / `role.yaml` `chat.workflow`).

---

## Using it in the app

1. Set **training config path** (and optionally **best model path**) in app settings so `workflow_runner.get_training_config_summary`, `get_training_config_dict`, and `get_training_results_follow_up` return real content.
2. Enable the role in **`role.yaml`** (`chat.enabled`, `chat.workflow` if you override the filename).
3. In the Flet agents UI, pick **RL Coach** (same dropdown rules as other main roles; see `agents/roles/registry.py`).

The handler builds inputs with **`build_rl_coach_agent_aligned_initial_inputs`** (or the slimmer **`build_rl_coach_initial_inputs`** when you do not need the full WD-style graph injects), **`build_rl_coach_unit_param_overrides`**, then runs **`run_rl_coach_workflow`**. When **`merge_response.data.result`** has **`kind == "applied"`**, it persists **`result.config`** as YAML to the session training config path (when set) and toasts success or save failure.

---

## What the chat graph does

High-level flow (from `rl_coach_workflow.json` metadata): **CleanText + LanguageDetector + IsAQuestion** align with the Analyst / Workflow Designer chat contract; **RAG** (user message → RagSearch → Filter → FormatRagPrompt) feeds context; **training injects** (config summary, results snippet, full config dict) feed the prompt; **LLM** → **TrainingConfigParser** → **ApplyTrainingConfigEdits**; **ProcessAgent** parses tool-style actions; same-turn tools include **grep**, **run_workflow**, **report**, **formulas_calc**, **delegate_request**. Output is normalized to **`merge_response.data`** like other role chat workflows.

**Reward shaping:** the model may emit actions such as `reward_formula_add`, `reward_formula_set`, `reward_rules_add`, `reward_rules_set`; these are expanded by **`expand_reward_actions`** and merged into the training config. For scripted application of edits outside this graph, use **`apply_training_config_edit`** (`gui/components/workflow_tab/workflows/edit_workflows/training_edit_runner.py`, re-exported from **`agents`**) or the **ApplyTrainingConfigEdits** workflow **`gui/components/workflow_tab/workflows/core_workflows/apply_training_config_edits_single.json`**.

Deeper reward semantics: **`rewards/README.md`** and **`docs/REWARD_RULES.md`**.

---

## `initial_inputs`

**Minimal** (`build_rl_coach_initial_inputs`): `inject_user_message`, `inject_training_config`, `inject_training_results`, `inject_previous_turn`, optional `inject_training_config_dict`, `inject_empty_diff`.

**Full chat parity with Workflow Designer graph fields** (`build_rl_coach_agent_aligned_initial_inputs`): starts from `build_agent_workflow_initial_inputs` (graph, follow-up, language, …) then **`update(..., build_rl_coach_training_inject_updates(...))`** so the same RAG + merge path can run with training ports filled.

Rule: each **Inject** id maps to `initial_inputs[id] = {"data": value}` when calling `run_workflow` / `run_agent_workflow`.

---

## Running the workflow yourself

### Python (preferred wrapper)

```python
from gui.chat.role_turns.rl_coach.workflow_runner import (
    build_rl_coach_unit_param_overrides,
    run_rl_coach_workflow,
    get_training_config_dict,
    get_training_config_summary,
    get_training_results_follow_up,
)
from agents.roles.rl_coach.workflow_inputs import build_rl_coach_initial_inputs

initial_inputs = build_rl_coach_initial_inputs(
    "Penalize dumping more strongly.",
    training_config=get_training_config_summary(),
    training_results=get_training_results_follow_up(),
    previous_turn="",
    training_config_dict=get_training_config_dict(),
)
overrides = build_rl_coach_unit_param_overrides("ollama", {"model": "llama3.2", "host": "http://127.0.0.1:11434"})
data = run_rl_coach_workflow(initial_inputs, unit_param_overrides=overrides)
```

`run_rl_coach_workflow` delegates to **`run_agent_workflow(..., workflow_path=RL_COACH_WORKFLOW_PATH)`**.

### CLI

```bash
python -m runtime agents/roles/rl_coach/rl_coach_workflow.json --format dict --initial-inputs @inputs.json
```

---

## `merge_response.data` and saving config

Same surface as Workflow Designer: **`reply`**, **`result`**, **`status`**, **`parser_output`**, **`workflow_errors`**, etc.

When the training edit path applies successfully, **`result`** contains **`kind`**, **`config`**, and related fields; the Flet handler writes **`result.config`** when **`kind == "applied"`**.

---

## `unit_param_overrides` (`build_rl_coach_unit_param_overrides`)

Typical keys: **`llm_agent`** (model, provider, host, generation options), **`rag_search`** / **`rag_filter`** / **`format_rag`** (RAG caps and score), **`prompt_llm`** (`template_path` from `get_rl_coach_prompt_path()`), optional **`report`** `output_dir`. Delegate-tool visibility is merged via **`merge_prompt_llm_strip_delegate_when_auto`** when relevant.

---

## Config edit shape (reminder)

The model should emit a **partial** training config (only keys that change) or structured actions for rewards. The backend **deep-merges** into the current config. Example weight tweak:

```json
{
  "rewards": {
    "weights": {
      "dumping": -0.2
    }
  }
}
```

Use **`{ "action": "no_edit", "reason": "..." }`** when no config change is requested. Full goal/reward/algorithm vocabulary lives in **`RL_COACH_SYSTEM`** / `config/prompts/rl_coach.json` and in **`docs/REWARD_RULES.md`**.

---

## See also

- **All roles** (YAML schema): [`../README.md`](../README.md)
- **Flet handler** (toasts, save path): [`../../../gui/chat/role_turns/rl_coach/README.md`](../../../gui/chat/role_turns/rl_coach/README.md)
- **Workflow Designer** (shared inject pattern): [`../workflow_designer/README.md`](../workflow_designer/README.md)
- **Runtime** (`run_workflow`): [`../../../runtime/README.md`](../../../runtime/README.md)
