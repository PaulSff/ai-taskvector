# RL Coach (Training Assistant) — Formal Approach

This document formalizes the **RL Coach** (also called Training Assistant): its role, input/output, recommended implementation (start with prompt-only; fine-tune later if needed), and integration with the training pipeline.

**Implementation:** The system prompt used for the RL Coach is in **`assistants/prompts.py`** as `RL_COACH_SYSTEM`. The app runs `rl_coach_workflow.json`; the backend applies edits via `apply_config_edit` (and related merge paths). **Reward shaping:** the RL Coach outputs direct config edits such as `reward_formula_add`, `reward_formula_set`, `reward_rules_add`, `reward_rules_set`, which are expanded by `expand_reward_actions` and merged into the training config. For **scripted** merges, use **`gui.components.workflow_tab.core_workflows.run_apply_training_config_edits`** (workflow **`gui/components/workflow_tab/core_workflows/apply_training_config_edits_single.json`**, same **ApplyTrainingConfigEdits** unit as this workflow) or the thin helper **`apply_training_config_edit`** in **`gui/components/workflow_tab/edit_workflows/training_edit_runner.py`** (re-exported from **`assistants`**). For graphs, **`run_apply_edits`** + **`run_normalize_graph`** ( **`apply_edits_single.json`** ). See **rewards/README.md** and **docs/REWARD_RULES.md**.

---

## 1. Role

The **RL Coach** helps users (and the system) **configure and improve training** without writing code:

- **Suggest or apply**: **goals** (e.g. "keep pressure in 2–5 bar", "target temperature 37°C"), **reward design** (presets, weights, custom components), **algorithm** (PPO, SAC, etc.), **hyperparameters** (learning rate, batch size, steps), and **testing** (run evaluation, compare checkpoints).
- **Operates on**: training config (YAML/JSON: goal, rewards, algorithm, hyperparameters), **not** `runtime/train.py` or raw reward code.
- **Does not**: write Python; it only proposes or applies **declarative edits** to the training config.

---

## 2. Input and Output

| | Description |
|---|-------------|
| **Input** | User message (natural language) + **current training config** (and optionally current process graph or env type). Example: "Make the reward penalize dumping more" + current config YAML. |
| **Output** | (1) **Natural language response** (explanation, confirmation). (2) **Structured edit**: for **reward-shaping** the RL Coach outputs `reward_formula_add`, `reward_formula_set`, `reward_rules_add`, or `reward_rules_set` with formula/rules payload; for goal/algorithm/hyperparameter changes it outputs a direct config edit (e.g. `{"goal": {"target_temp": 40.0}}`). The backend merges edits via `apply_config_edit`; training reads the updated config. |

The assistant **never** outputs raw code; it outputs **config edits** (goal, rewards, algorithm, hyperparameters) in a defined schema.

---

## 3. Recommended Approach: Start with Prompt-Only, Fine-Tune Later

**Do not train from scratch.** Use an **existing open-source LLM** and steer it with prompts (and optional RAG). Fine-tune only if accuracy is insufficient.

### 3.1 Why not train from scratch?

- Same as Workflow Designer: base LLMs are sufficient for instruction-following on "edit training config."
- Reward presets and goal types are **finite**; a good system prompt + few-shot covers most cases.
- Collect (user request, correct config edit) from usage; fine-tune later if needed for consistency or domain jargon.

### 3.2 Best option to start: Prompt-only + structured output

| Step | What to do |
|------|-------------|
| **Base model** | Use an **existing open-source LLM** via **Ollama** (e.g. Llama 3.2 3B, Mistral 7B, Qwen2.5 7B) or another local/cloud API. No training. |
| **System prompt** | Define the assistant's role, **goal types** (setpoint, range, multi-objective), **reward presets** (temperature_and_volume, pressure_control, etc.), **reward components** (temp_error, volume_in_range, dumping, step_penalty), **algorithms** (PPO, SAC), and **output format** (JSON for config edits). See §5. |
| **Few-shot examples** | Include 1–3 examples: user request → assistant reply + structured config edit (e.g. "penalize dumping more" → `{"rewards": {"weights": {"dumping": -0.2}}}`). |
| **Structured output** | Require the model to output a **JSON block** for the edit (e.g. `{"rewards": {...}, "goal": {...}}`). Parse in the backend and merge into training config. |
| **Optional RAG** | Index reward presets, goal schemas, and example configs; retrieve by query and add to prompt. |

### 3.3 When to fine-tune

- **Fine-tune later** if: (1) prompt-only often suggests invalid or suboptimal rewards/hyperparameters, or (2) you need strict JSON schema compliance.
- **How**: Collect (user message, current config, correct config edit). Fine-tune a small model (e.g. Llama 3.2 3B, Qwen2.5-7B) with LoRA for "given user message + config → output config edit (JSON)."

---

## 4. What You Implement (No New Model Training to Start)

| Component | Description |
|-----------|-------------|
| **System prompt** | Role, goal types, reward presets and components, algorithms, hyperparameter ranges, output JSON schema. |
| **Few-shot examples** | 1–3 (user request → response + JSON config edit). |
| **Structured output parser** | Parse model reply for JSON block; validate against schema; merge edit into training config (deep merge for nested keys). |
| **Config merge API** | Backend that applies the parsed edit to the current training config and saves it (e.g. `training_config.yaml`). Training script reads this file. |
| **Optional RAG** | Index: reward presets, goal schemas, example configs, docs. Retrieve by query; add to prompt. |

---

## 5. System Prompt Outline (RL Coach)

The canonical prompt is in **`assistants/prompts.py`** (`RL_COACH_SYSTEM`). Below is the same content as a reference; customize to your reward presets and goal types if needed.

```text
You are the RL Coach. You help users configure RL training: goals, rewards, algorithm, and hyperparameters. You never write code; you only output structured edits (JSON) to the training config.

## Goal types
- setpoint: target_temp, target_volume_ratio (e.g. [0.80, 0.85])
- range: target_pressure_range [min, max], target_temp_range
- multi_objective: list of objectives with weights

## Reward presets
- temperature_and_volume: temp_error (negative), volume_in_range (bonus), dumping (penalty), step_penalty
- pressure_control: pressure_error, pressure_in_range, flow_penalty
- custom: user-defined weights over components

## Reward components (weights: negative = penalty, positive = bonus)
- temp_error: weight typically -1.0
- volume_in_range: weight typically 10.0
- dumping: weight typically -0.1 (increase magnitude to penalize dumping more)
- step_penalty: weight typically -0.001
- exploration_bonus: optional

## Algorithms
- PPO: learning_rate (e.g. 3e-4), n_steps (2048), batch_size (64), n_epochs (10)
- SAC: learning_rate, buffer_size, batch_size

## Output format
Always end your reply with a JSON block for the config edit, inside ```json ... ```. Only include keys you are changing. Examples:
- Change reward weight: { "rewards": { "weights": { "dumping": -0.2 } } }
- Add formula component: { "action": "reward_formula_add", "expr": "-abs(get(outputs, 'tank.temp', 0) - goal.get('target_temp', 37))", "weight": 1.0 }
- Change goal: { "goal": { "target_temp": 40.0 } }
- Change algorithm hyperparams: { "hyperparameters": { "learning_rate": 1e-4 } }
- No change: { "action": "no_edit", "reason": "..." }

If the user message does not request a config change, output { "action": "no_edit", "reason": "..." } and explain in natural language.
```

---

## 6. Output Schema (Training Config Edit)

The assistant's **structured output** should be a **partial training config** (only keys that change). Backend **merges** this into the current config (deep merge).

```yaml
# Example full config (for reference); assistant outputs only the subset it changes
goal:
  type: setpoint
  target_temp: 37.0
  target_volume_ratio: [0.80, 0.85]
rewards:
  preset: temperature_and_volume
  weights:
    temp_error: -1.0
    volume_in_range: 10.0
    dumping: -0.1
    step_penalty: -0.001
algorithm: PPO
hyperparameters:
  learning_rate: 3e-4
  n_steps: 2048
  batch_size: 64
  n_epochs: 10
```

Example assistant output (edit only):

```json
{
  "rewards": {
    "weights": {
      "dumping": -0.2
    }
  }
}
```

Backend merges into current config; training script reads the merged file.

---

## 7. Reward Presets Reference (for prompt and RAG)

Include this in the system prompt or RAG index so the assistant knows valid presets and components.

| Preset | Components | Typical use |
|--------|------------|-------------|
| **temperature_and_volume** | temp_error, volume_in_range, dumping, step_penalty | Temperature mixing (current repo). |
| **pressure_control** | pressure_error, pressure_in_range, flow_penalty, step_penalty | Pressure setpoint/range. |
| **goal_reaching** | state_reach_reward, step_penalty | Generic goal state (e.g. qontinui-gym style). |
| **exploration** | exploration_bonus, novelty_bonus, step_penalty | Exploration-heavy tasks. |

Weights: negative = penalty, positive = bonus. Assistant suggests numeric values within reasonable ranges (e.g. step_penalty -0.001 to -0.01, volume_in_range 5.0 to 20.0).

---

## 8. Base Model Suggestion (Start)

| Option | Model | Use case |
|--------|-------|----------|
| **Local (Ollama)** | Llama 3.2 3B, Mistral 7B, Qwen2.5-7B | Same stack as Workflow Designer and model-operator; no API keys. |
| **Larger / cloud** | Llama 3.1 8B, GPT-4o-mini, Claude Haiku | If 3B/7B underperforms on complex reward design. |

Start with **Ollama + Llama 3.2 3B or Mistral 7B**; align with Workflow Designer and RL Coach (Flet GUI chat).

---

## 9. Integration with Training Pipeline

- **Config-driven runtime/train.py**: Training script reads `training_config.yaml` (or JSON) for goal, rewards, algorithm, hyperparameters. When the user asks the RL Coach for a change, backend calls the LLM with (user message + current config), parses JSON edit, **merges** into config, saves file. User (or GUI) runs "Train" which invokes `runtime/train.py` with the updated config.
- **Run / test**: Assistant can suggest "run training" or "test current model"; the actual run is triggered by the user or GUI (e.g. "Train" button), not by the assistant executing code. Assistant only edits config; execution is separate.

---

## 10. Summary

| Question | Answer |
|----------|--------|
| **Train from scratch?** | No. Use an existing open-source LLM (Ollama: Llama, Mistral, Qwen). |
| **Fine-tune from the start?** | No. Start with **prompt-only + structured output** (system prompt + few-shot + JSON schema). |
| **When to fine-tune?** | When prompt-only is not accurate or consistent; then fine-tune a small model (LoRA) on (user message, config, correct edit) pairs. |
| **Best option to start** | **Prompt-only + structured output** with Ollama (Llama 3.2 3B or Mistral 7B) + system prompt from `assistants.prompts.RL_COACH_SYSTEM` (§5) + output schema (§6) + config merge API. Optional RAG over reward presets and goal schemas. |

This keeps the RL Coach **simple to start** and **easy to improve** later with RAG or fine-tuning.
