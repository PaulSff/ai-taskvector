# TrainingConfigParser unit

Canonical unit that **parses the RL Coach LLM response** into a list of training-config edit blocks.

- **Inputs**
  - `action` (Any) — Raw LLM response string (may contain markdown and fenced `\`\`\`json` or inline `{ ... }`).
- **Outputs**
  - `edits` (Any) — List of dicts, each one an edit (e.g. `{"action": "no_edit", "reason": "..."}`, `{"goal": {"target_temp": 80}}`, `{"action": "reward_formula_add", "expr": "...", "weight": -0.1}`).
  - `error` (str) — Set when fenced JSON was present but parsing failed.

Same JSON extraction as ProcessAgent (no workflow-designer side channels like web_search). Used in `assistants/roles/rl_coach/rl_coach_workflow.json`: LLMAgent → TrainingConfigParser → ApplyTrainingConfigEdits.
