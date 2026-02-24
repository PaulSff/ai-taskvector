# Rewards pipeline

Environment-agnostic reward evaluation. All parameters come from graph connections/ports and config.

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

## Context

- **outputs**: `{unit_id: {port_name: value}}` from graph executor
- **goal**: from GoalConfig (target_temp, target_volume_ratio, etc.)
- **observation**: assembled observation vector
- **step_count**, **max_steps**, optional **action**

## Formula DSL

Use `get(outputs, "unit_id.port_name", default)` to read values. Example:

```yaml
formula:
  - expr: "-abs(get(outputs, 'mixer_tank.temp', 0) - goal.get('target_temp', 37))"
    weight: 1.0
  - expr: "get(outputs, 'dump_valve.flow', 0)"
    weight: -0.1
```

Rules use the same state (outputs, goal, observation, step_count) for condition expressions.
