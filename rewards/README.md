# Rewards pipeline

Environment-agnostic reward evaluation. All parameters come from graph connections/ports and config. **DSL** (Somain-Specific Language) provides a safe and easy way for RL Coach (LLM) to build formulas from text. The formula represents a part of the training config (rewards), which is executed by the **Oracle collector (Unit)** to calcualte rewards diring the flow execution.   

## Pipeline

```
Graph connections/ports  →  Observations  →  DSL (formula + rules)  →  Rule engine  →  Oracle collector (Unit)  →  Flow execution
```

| Stage | Description |
|-------|-------------|
| **Graph connections/ports** | Process graph units produce outputs via ports; connections define data flow. |
| **Observations** | Assembled from wired observation sources (e.g. `observation_source_ids`). In Oracle: `[inputs.get(sid) for sid in _obs_ids]`; in GraphExecutor: sensor outputs. |
| **outputs** | `{unit_id: {port: value}}` built from graph state. Oracle collector derives from `state`; custom envs from executor `info["outputs"]`. |
| **DSL** | Formula (asteval) + rules (rule-engine). Expressions reference `get(outputs, "unit_id.port", 0)`, `goal`, `observation`, etc. |
| **Rule engine** | `evaluate_reward()`: formula components → asteval; rules → rule-engine. Sum of contributions. |
| **Oracle collector (Unit)** | RLOracle collector (PyFlow/Node-RED/n8n): builds `outputs` and `observation`, calls `evaluate_reward()`, returns `{observation, reward, done}`. |
| **Flow execution** | Graph runs; step driver injects action; collector executes; response returned to training loop. |

Callers (GraphEnv, PyFlow adapter in Oracle mode) all call `evaluate_reward(rewards_config, outputs, goal, observation, step_count, max_steps)`.

## Usage

```python
from rewards import evaluate_reward

reward = evaluate_reward(
    rewards_config,
    outputs,   # {unit_id: {port: value}} from graph
    goal,
    observation,
    step_count,
    max_steps,
)
```

## Context (available in both formula and rules)

| Variable | Type | Description |
|----------|------|-------------|
| `outputs` | dict | `{unit_id: {port_name: value}}` from graph executor |
| `goal` | dict | GoalConfig (target_temp, target_volume_ratio, target_pressure_range, etc.) |
| `observation` | list[float] | Assembled observation vector |
| `step_count` | int | Current step index |
| `max_steps` | int | Episode length |
| `action` | list[float] | Last action taken (optional) |

---

## Formula DSL (asteval)

Formula expressions use [asteval](https://github.com/newville/asteval): Python-like expressions with restricted builtins. Each component contributes `weight * eval(expr)` (numeric) or `reward` when `expr` is truthy (conditional).

### Safe value access

```
get(obj, "path.to.key", default)
```

- **obj**: `outputs`, `goal`, or any dict
- **path**: dot-separated keys (e.g. `"mixer_tank.temp"`, `"dump_valve.flow"`)
- **default**: value if path is missing (typically `0`)

Example: `get(outputs, 'mixer_tank.temp', 0)`, `goal.get('target_temp', 37)`

### Math and builtins

| Symbol | Description |
|--------|-------------|
| `abs`, `min`, `max` | Standard numeric functions |
| `sqrt`, `sin`, `cos`, `tan` | From `math` |
| `log`, `log10`, `exp`, `pow` | From `math` |

### Component types

- **weight**: Numeric term. Contribution = `weight * eval(expr)`. Use for continuous penalties/rewards.
- **reward**: Conditional bonus. Contribution = `reward` when `expr` is truthy, else 0.

### Example

```yaml
formula:
  - expr: "-abs(get(outputs, 'mixer_tank.temp', 0) - goal.get('target_temp', 37))"
    weight: 1.0
  - expr: "get(outputs, 'dump_valve.flow', 0)"
    weight: -0.1
  - expr: "get(outputs, 'mixer_tank.volume_ratio', 0) >= 0.8 and get(outputs, 'mixer_tank.volume_ratio', 0) <= 0.85"
    reward: 10.0
```

---

## Rules DSL (rule-engine)

Rules use [rule-engine](https://zerosteiner.github.io/rule-engine/): each rule has a `condition` (boolean expression) and `reward_delta`. If the condition matches the state, `reward_delta` is added to the total. State includes the same context (outputs, goal, observation, etc.) plus `get`.

### Operators

| Category | Operators |
|----------|-----------|
| Arithmetic | `+`, `-`, `*`, `/`, `//`, `%`, `**` |
| Comparison | `==`, `!=`, `>`, `>=`, `<`, `<=` |
| Logical | `and`, `or`, `not` |
| Ternary | `condition ? true_val : false_val` |
| Access | `.` (attribute), `&.` (safe), `[key]`, `&[key]` (safe) |
| Regex | `=~` (match), `=~~` (search), `!~`, `!~~` |

### Builtins (rule-engine)

`abs`, `min`, `max`, `all`, `any`, `lower`, `upper`, etc. See [rule-engine builtins](https://zerosteiner.github.io/rule-engine/syntax.html#builtin-symbols).

### Example

```yaml
rules:
  - condition: "get(outputs, 'mixer_tank.temp', 0) - goal.get('target_temp', 37) > 10"
    reward_delta: -5.0
  - condition: "get(outputs, 'dump_valve.flow', 0) > 0 and get(outputs, 'mixer_tank.volume_ratio', 0) > 0.85"
    reward_delta: -2.0
```
