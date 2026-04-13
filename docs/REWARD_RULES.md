# Reward rules: formula and rule engine

This doc covers the **universal rewards pipeline**: config-driven formula and rule-engine rules. All reward calculation flows through **rewards/**; envs and Oracle collectors delegate to it. See **rewards/README.md** (formula + rules DSL), **schemas/training_config.py** (RewardsConfig), and **assistants/roles/rl_coach/TRAINING_ASSISTANT.md** (RL Coach edits).

---

## 1. Universal rewards pipeline

**Single path**: All reward calculation goes through `rewards.evaluate_reward()`. Envs and Oracle collectors build context (outputs from graph, goal, observation, step_count, max_steps) and call the evaluator. **100% environment-agnostic**: no hardcoded params; formula and rules reference `get(outputs, "unit_id.port", default)` and `goal`. **Config**: RewardsConfig has `formula` (FormulaComponent: expr + weight/reward), `rules` (rule-engine). When `formula` or `rules` are present, the Oracle collector (Node-RED, n8n, PyFlow, ComfyUI) uses them; otherwise it falls back to preset/weights or setpoint.

_Custom env (GraphEnv)_ uses preset + weights. _Oracle pipelines_ use formula and rules from the rewards pipeline. The **RL Coach** (in-app assistant) edits rewards via natural language → config edit JSON: `reward_formula_add`, `reward_formula_set`, `reward_rules_add`, `reward_rules_set`; the backend merges these into the config. For **headless** merges from a JSON edit, use `gui.components.workflow_tab.core_workflows.run_apply_training_config_edits(current_config, [edit])` (workflow `apply_training_config_edits_single.json`), or `apply_training_config_edit` from `gui.components.workflow_tab.edit_workflows` (re-exported as `assistants.apply_training_config_edit`) for a thin merge helper without running the workflow.

---

## 2. Rule engine options

| Option | What it does | Pros / cons |
|--------|----------------|-------------|
| **Rule-engine** | [rule-engine](https://pypi.org/project/rule-engine/) — Python rule engine; conditions as expressions (e.g. `temp > 90`), evaluate to true/false or a value. | Lightweight; rules as data (JSON or code); easy to integrate. Good for **structured reward rules** (e.g. “if temp_error > 5 then add -1”). |
| **Clipspy** | [clipspy](https://pypi.org/project/clipspy/) — CLIPS (expert system) in Python; if-then production rules. | Full expert-system power; good for complex rule sets. Heavier; CLIPS syntax to learn. Use when you need **many interdependent rules** or inference. |
| **text2reward (research)** | [text2reward](https://github.com/xlang-ai/text2reward) — external project: LLM generates **reward function code** from natural language + env representation. [Site](https://text-to-reward.github.io/). | Inspiration for “describe goal → reward”; not shipped as a separate CLI here — use **RL Coach** for natural language reward edits in this repo. |

---

## 3. Recommendation

- **Structured reward rules (if-then, conditions):** Use **Rule-engine** first. Define rules as data (e.g. list of `{ "condition": "temp_error > 5", "reward_delta": -1 }` or similar). Evaluate each rule in the env’s reward computation; sum contributions. Keeps reward logic declarative and editable without writing Python. Extend **RewardsConfig** with an optional `rules: list[RewardRule]` (or a reference to a rule-engine config); see **schemas/training_config.py** for a placeholder.
- **Complex rule sets / expert systems:** Consider **Clipspy** if you outgrow Rule-engine (many rules, inference, priorities). Likely overkill for simple reward shaping.
- **Natural language → reward edits:** Use the **RL Coach** in the app (system prompt in `assistants/roles/rl_coach/prompts.py` / `assistants.prompts`). It emits structured config edits that merge into the training config. Fallback: preset + weights or hand-authored formula/rules in YAML.

So: **Rule-engine** for structured rules as data; **RL Coach** for “describe in text → reward” edits in product workflows.

---

**Do we need to prompt the LLM to generate rules "using the engine"?** No. The LLM (RL Coach) outputs rules in our schema (`condition`, `reward_delta`). The **engine** is the **runtime evaluator** that evaluates those conditions in the env (at step time). One prompt for reward config (including rules); the engine evaluates them. No extra LLM prompt needed.

---

## 4. Natural language → rewards (RL Coach)

Use the **RL Coach** assistant in the app: it runs `rl_coach_workflow.json` and produces training config edits (including reward formula/rules actions). Prompt defaults live under `assistants/roles/rl_coach/`; see **assistants/roles/rl_coach/TRAINING_ASSISTANT.md**.

For **scripted** merges without the chat UI, load the YAML into a config object (or dict), build the edit dict, then call `run_apply_training_config_edits(config, [edit])` from `gui.components.workflow_tab.core_workflows` (same **ApplyTrainingConfigEdits** unit as `rl_coach_workflow.json`). Alternatively use `apply_training_config_edit` from `edit_workflows/training_edit_runner.py` for direct merge + normalize without a workflow run.

---

## 5. Rule-engine evaluator (runtime)

We implement a **rule evaluator** so that `RewardsConfig.rules` are evaluated at step time. The LLM does not need a special prompt for "rules using the engine" — it already outputs rules; the engine evaluates them.

**Module:** `rewards/rules.py`

- **`evaluate_rules(state: dict, rules: list[RewardRule]) -> float`** — Evaluates each rule's condition against `state` using the [rule-engine](https://pypi.org/project/rule-engine/) package; returns the sum of `reward_delta` for rules that match. If `rule-engine` is not installed, returns 0.0.

**State dict:** The env (or reward computer) must build a dict of variable names to values (e.g. `temp_error`, `volume`, `hot_flow`, `cold_flow`, `dump_flow`, `target_temp`) so that rule conditions (e.g. `temp_error > 5`, `volume < 0.8`) can be evaluated.

**Wiring into the env:** Done. Training config’s `rewards` are passed from `runtime/train.py` and `scripts/test_model.py` into the env factory and into `GraphEnv`. In `step()` (and `manual_step()`), the env builds a state dict and adds `evaluate_rules(state_dict, rewards_config.rules)` to the reward. Rules from the RL Coach, YAML, or other edits are used at runtime.

**Requires:** `pip install rule-engine` (optional; if not installed, `evaluate_rules` returns 0.0).

---

## 6. Schema extension (optional, non-breaking)

Add to **RewardsConfig** (see **schemas/training_config.py**):

- **`rules: list[dict] | None = None`** — Optional list of rule definitions for a rule engine. Shape TBD (e.g. `{ "condition": str, "reward_delta": float }` for Rule-engine, or `{ "rule_engine": "rule_engine" | "clipspy", "config": dict }`).
- **`reward_code: dict | None = None`** — Optional reference to generated reward (e.g. from an external code generator): `{ "language": "python", "source": str }` or path to generated file. Env or a small runner would eval/exec in a sandbox (future).

Existing configs without `rules` or `reward_code` are unchanged; reward stays preset + weights. **rules** and **RewardRule** are already in **schemas/training_config.py**; **reward_code** is optional (future).

---

## 7. Links

- **Rule-engine:** https://pypi.org/project/rule-engine/
- **Clipspy:** https://pypi.org/project/clipspy/
- **Text-to-reward:** https://text-to-reward.github.io/ , https://github.com/xlang-ai/text2reward
