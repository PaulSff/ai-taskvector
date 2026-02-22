// RLOracle step driver for n8n. Uses $getWorkflowStaticData() as state.
// Placeholders: __TPL_OBS_NAMES__, __TPL_ACT_NAMES__, __TPL_OBS_PREFIX__, __TPL_STEP_KEY__
// Input: webhook body (action or reset). Output 0: response (reset); Output 1: trigger process (step)

const _obs = __TPL_OBS_NAMES__;
const _act = __TPL_ACT_NAMES__;
const _prefix = __TPL_OBS_PREFIX__;
const _stepKey = __TPL_STEP_KEY__;
const state = $getWorkflowStaticData('global');

const item = $input.first();
const payload = item.json.body || item.json;

if (payload && payload.reset) {
  state[_stepKey] = 0;
  const obs = _obs.map(n => typeof state[_prefix + n] === 'number' ? state[_prefix + n] : 0);
  return [{ json: { observation: obs, observation_names: _obs, action_names: _act, reward: 0, done: false } }];
}

state.action = payload.action || _act.map(() => 0);
state._webhookItem = item;
return [[], [item]];
