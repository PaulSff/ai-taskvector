# Canonical StepRewards (PyFlow): observation from Join, trigger injected. Same semantics as our runtime.
# Placeholders: __TPL_MAX_STEPS__, __TPL_REWARD__, __TPL_STEP_KEY__
_max_steps = __TPL_MAX_STEPS__
_reward = __TPL_REWARD__
_step_key = __TPL_STEP_KEY__

def _to_observation(val):
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [float(x) if isinstance(x, (int, float)) else 0.0 for x in val]
    return [float(val)]

observation = _to_observation(inputs.get("observation"))
trigger = inputs.get("trigger")

step_count = int(state.get(_step_key, 0))
if trigger == "reset":
    step_count = 0
else:
    step_count += 1
new_state = {**state, _step_key: step_count}

done = step_count >= _max_steps
reward = 0.0
if _reward is not None:
    try:
        from core.schemas.training_config import GoalConfig, RewardsConfig
        from core.gym.rewards import evaluate_reward
        cfg = RewardsConfig.model_validate(_reward) if isinstance(_reward, dict) else _reward
        goal = _reward.get("goal") if isinstance(_reward, dict) else getattr(_reward, "goal", None)
        if goal is not None and isinstance(goal, dict):
            goal = GoalConfig.model_validate(goal)
        outputs = inputs.get("outputs")
        if not isinstance(outputs, dict):
            outputs = {"observation": {str(i): v for i, v in enumerate(observation)}}
        reward = evaluate_reward(cfg, outputs, goal, observation, step_count, _max_steps)
    except Exception:
        pass

payload = {"observation": observation, "reward": float(reward), "done": bool(done)}
outputs_out = {"observation": observation, "reward": float(reward), "done": bool(done), "payload": payload}
return outputs_out, new_state
