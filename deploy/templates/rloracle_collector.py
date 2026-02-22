# RLOracle collector for PyFlow. Aggregates observations, computes reward, returns {observation, reward, done}.
# Placeholders: __TPL_OBS_SOURCE_IDS__, __TPL_REWARD__, __TPL_MAX_STEPS__, __TPL_STEP_KEY__
# inputs: dict mapping upstream node_id -> value. state: shared graph state.

_obs_ids = __TPL_OBS_SOURCE_IDS__
_reward = __TPL_REWARD__
_max_steps = __TPL_MAX_STEPS__
_step_key = __TPL_STEP_KEY__

def _get_val(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)) and v:
        return float(v[0])
    if isinstance(v, dict):
        if "value" in v:
            return float(v["value"])
        if "temp" in v:
            return float(v["temp"])
        if "volRatio" in v:
            return float(v["volRatio"])
    return 0.0

observation = [_get_val(inputs.get(sid)) for sid in _obs_ids]
step_count = int(state.get(_step_key, 0)) + 1
state[_step_key] = step_count

reward = 0.0
rtype = (_reward.get("type") if isinstance(_reward, dict) else None) or "setpoint"
if rtype == "setpoint":
    idx = _reward.get("observation_index", 0) if isinstance(_reward, dict) else 0
    target = (_reward.get("target") or _reward.get("target_temp") or 0) if isinstance(_reward, dict) else 0
    reward = -abs((observation[idx] if idx < len(observation) else 0) - target)
elif isinstance(_reward, dict) and isinstance(_reward.get("reward"), (int, float)):
    reward = float(_reward["reward"])

done = step_count >= _max_steps

_result = {"observation": observation, "reward": reward, "done": done}
