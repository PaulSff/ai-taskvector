# Reward rules: rule engines and text-to-reward

This doc covers the **reward rules** gap: we currently have **preset + weights** (no rule engine). Options: **Rule-engine**, **Clipspy**, and **text-to-reward** (LLM-based) to define or generate reward logic. See **schemas/training_config.py** (RewardsConfig) and **docs/TRAINING_ASSISTANT.md**.

---

## 1. Current state: preset + weights only

We have **RewardsConfig**: `preset` (e.g. `temperature_and_volume`) and `weights` (e.g. `temp_error: -1.0`, `volume_in_range: 10.0`, `dumping: -0.1`, `step_penalty: -0.001`). The env (e.g. `TemperatureControlEnv`) computes reward from these weights and the current state. There is **no rule engine**: no “if condition then add reward” rules, and no natural-language → reward function.

---

## 2. Rule engine options

| Option | What it does | Pros / cons |
|--------|----------------|-------------|
| **Rule-engine** | [rule-engine](https://pypi.org/project/rule-engine/) — Python rule engine; conditions as expressions (e.g. `temp > 90`), evaluate to true/false or a value. | Lightweight; rules as data (JSON or code); easy to integrate. Good for **structured reward rules** (e.g. “if temp_error > 5 then add -1”). |
| **Clipspy** | [clipspy](https://pypi.org/project/clipspy/) — CLIPS (expert system) in Python; if-then production rules. | Full expert-system power; good for complex rule sets. Heavier; CLIPS syntax to learn. Use when you need **many interdependent rules** or inference. |
| **Text-to-reward** | [text2reward](https://github.com/xlang-ai/text2reward) — LLM generates **reward function code** from natural language + env representation. [Site](https://text-to-reward.github.io/). | Natural language → executable reward; interpretable dense reward code; supports iterative refinement. Research/experimental; LLM-dependent; needs env representation. Good for **“describe goal in text → get reward function.”** |

---

## 3. Recommendation

- **Structured reward rules (if-then, conditions):** Use **Rule-engine** first. Define rules as data (e.g. list of `{ "condition": "temp_error > 5", "reward_delta": -1 }` or similar). Evaluate each rule in the env’s reward computation; sum contributions. Keeps reward logic declarative and editable without writing Python. Extend **RewardsConfig** with an optional `rules: list[RewardRule]` (or a reference to a rule-engine config); see **schemas/training_config.py** for a placeholder.
- **Complex rule sets / expert systems:** Consider **Clipspy** if you outgrow Rule-engine (many rules, inference, priorities). Likely overkill for simple reward shaping.
- **Natural language → reward function:** Use **text-to-reward** as an optional path: user describes the goal in text → LLM generates reward code (or config) → we plug it into training. Fallback: keep current preset + weights (or rule-engine rules). Integrate as a **Training Assistant** feature: “describe reward in text” → call text2reward → merge generated weights or code into config.

So: **Rule-engine** for a first step (structured rules as data); **text-to-reward** for “describe in text → reward” (optional, with fallback to preset/weights or rules).

---

**Do we need to prompt the LLM to generate rules "using the engine"?** No. The LLM (text-to-reward) already outputs rules in our schema (`condition`, `reward_delta`). The **engine** is the **runtime evaluator** that evaluates those conditions in the env (at step time). One prompt for reward config (including rules); the engine evaluates them. No extra LLM prompt needed.

---

## 4. Text-to-reward integration (Ollama)

We integrate **text-to-reward** via **Ollama**: user describes the reward in natural language → Ollama returns structured reward edit (weights, rules) as JSON → we merge into TrainingConfig. No dependency on the external text2reward repo; same pattern as Training Assistant (prompt + structured output).

**Module:** `assistants/text_to_reward.py`

- **`text_to_reward(text, current_config=None, model="llama3.2")`** — Calls Ollama with a reward-shaping system prompt; parses response for JSON with `rewards` (preset, weights, rules). Returns edit dict for `training_assistant_apply(current, edit)`.
- **`text_to_reward_apply(text, current, model="llama3.2")`** — Convenience: text → edit → merge → returns canonical TrainingConfig.

**CLI:** `python -m assistants text_to_reward --text "Penalize dumping more" [--config path] [--out path] [--model llama3.2]`

- Optional `--config`: current training config YAML (if omitted, uses default TrainingConfig).
- Optional `--stdin`: read reward description from stdin (e.g. `echo "Penalize dumping more" | python -m assistants text_to_reward --stdin`).

**Requires:** `pip install ollama`, Ollama running, and a model (e.g. `ollama pull llama3.2`). See [ollama.ai](https://ollama.ai).

---

## 5. Rule-engine evaluator (runtime)

We implement a **rule evaluator** so that `RewardsConfig.rules` are evaluated at step time. The LLM does not need a special prompt for "rules using the engine" — it already outputs rules; the engine evaluates them.

**Module:** `environments/reward_rules.py`

- **`evaluate_rules(state: dict, rules: list[RewardRule]) -> float`** — Evaluates each rule's condition against `state` using the [rule-engine](https://pypi.org/project/rule-engine/) package; returns the sum of `reward_delta` for rules that match. If `rule-engine` is not installed, returns 0.0.

**State dict:** The env (or reward computer) must build a dict of variable names to values (e.g. `temp_error`, `volume`, `hot_flow`, `cold_flow`, `dump_flow`, `target_temp`) so that rule conditions (e.g. `temp_error > 5`, `volume < 0.8`) can be evaluated.

**Wiring into the env:** Done. Training config’s `rewards` are passed from `train.py` and `test_model.py` into the env factory and into `TemperatureControlEnv`. In `step()` (and `manual_step()`), the env builds a state dict and adds `evaluate_rules(state_dict, rewards_config.rules)` to the reward. Rules from text-to-reward or manual config are used at runtime.

**Requires:** `pip install rule-engine` (optional; if not installed, `evaluate_rules` returns 0.0).

---

## 6. Schema extension (optional, non-breaking)

Add to **RewardsConfig** (see **schemas/training_config.py**):

- **`rules: list[dict] | None = None`** — Optional list of rule definitions for a rule engine. Shape TBD (e.g. `{ "condition": str, "reward_delta": float }` for Rule-engine, or `{ "rule_engine": "rule_engine" | "clipspy", "config": dict }`).
- **`reward_code: dict | None = None`** — Optional reference to generated reward (e.g. from text-to-reward): `{ "language": "python", "source": str }` or path to generated file. Env or a small runner would eval/exec in a sandbox (future).

Existing configs without `rules` or `reward_code` are unchanged; reward stays preset + weights. **rules** and **RewardRule** are already in **schemas/training_config.py**; **reward_code** is optional (future).

---

## 7. Links

- **Rule-engine:** https://pypi.org/project/rule-engine/
- **Clipspy:** https://pypi.org/project/clipspy/
- **Text-to-reward:** https://text-to-reward.github.io/ , https://github.com/xlang-ai/text2reward
