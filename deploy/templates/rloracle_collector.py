# RLOracle collector for PyFlow. Environment-agnostic.
# Aggregates observations from wired sources, computes reward, returns {observation, reward, done}.
# Placeholders: __TPL_OBS_SOURCE_IDS__, __TPL_REWARD__, __TPL_MAX_STEPS__, __TPL_STEP_KEY__
# inputs: upstream node_id -> value. state: shared graph state.

_obs_ids = __TPL_OBS_SOURCE_IDS__
_reward = __TPL_REWARD__
_max_steps = __TPL_MAX_STEPS__
_step_key = __TPL_STEP_KEY__

def _to_float(v):
    """Extract a float from any scalar, list, or dict. Works for any graph/output structure."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)) and v:
        return _to_float(v[0])
    if isinstance(v, dict):
        for k in ("value", "out", "output", "result"):
            if k in v:
                return _to_float(v[k])
        for val in v.values():
            return _to_float(val)
    return 0.0

observation = [_to_float(inputs.get(sid)) for sid in _obs_ids]
step_count = int(state.get(_step_key, 0)) + 1
state[_step_key] = step_count

# Build outputs from state for reward evaluator. Environment-agnostic: preserve graph structure.
outputs = {}
for nid, val in state.items():
    if nid == _step_key:
        continue
    if isinstance(val, dict) and not isinstance(val, (list,)):
        outputs[nid] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in val.items()}
    elif isinstance(val, (list, tuple)):
        outputs[nid] = {str(i): float(x) if isinstance(x, (int, float)) else _to_float(x) for i, x in enumerate(val)}
    else:
        outputs[nid] = {"value": _to_float(val)}

# Use universal reward evaluator when rewards config has formula or rules
reward = 0.0
used_evaluator = False
if isinstance(_reward, dict) and (_reward.get("formula") or _reward.get("rules")):
    try:
        from schemas.training_config import RewardsConfig
        from rewards import evaluate_reward
        cfg = RewardsConfig.model_validate(_reward)
        goal = _reward.get("goal") or {}
        reward = evaluate_reward(cfg, outputs, goal, observation, step_count, _max_steps)
        used_evaluator = True
    except Exception:
        pass
if not used_evaluator:
    rtype = (_reward.get("type") if isinstance(_reward, dict) else None) or "setpoint"
    if rtype == "setpoint":
        idx = _reward.get("observation_index", 0) if isinstance(_reward, dict) else 0
        target = (_reward.get("target") or _reward.get("target_temp") or 0) if isinstance(_reward, dict) else 0
        reward = -abs((observation[idx] if idx < len(observation) else 0) - target)
    elif isinstance(_reward, dict) and isinstance(_reward.get("reward"), (int, float)):
        reward = float(_reward["reward"])

done = step_count >= _max_steps

_result = {"observation": observation, "reward": reward, "done": done}
