// RLOracle collector for n8n. Aggregates observations, computes reward, returns response.
// Placeholders: __TPL_OBS_NAMES__, __TPL_REWARD__, __TPL_MAX_STEPS__, __TPL_OBS_PREFIX__, __TPL_STEP_KEY__
// Input: items from sensor nodes (json with topic/name and value). Output: response for Respond to Webhook.

const _obs = __TPL_OBS_NAMES__;
const _reward = __TPL_REWARD__;
const _maxSteps = __TPL_MAX_STEPS__;
const _prefix = __TPL_OBS_PREFIX__;
const _stepKey = __TPL_STEP_KEY__;
const state = $getWorkflowStaticData('global');

function getVal(obj) {
  if (typeof obj === 'number') return obj;
  if (obj && typeof obj.value === 'number') return obj.value;
  if (obj && obj.temp != null) return obj.temp;
  if (obj && obj.volRatio != null) return obj.volRatio;
  return 0;
}

const acc = state._obs_acc || {};
for (const item of $input.all()) {
  const j = item.json;
  const name = j.topic || j.obs_name || j.name;
  if (name) acc[name] = getVal(j.payload ?? (j.value !== undefined ? { value: j.value } : j));
}
for (const n of _obs) {
  if (!(n in acc) && typeof state[_prefix + n] === 'number') acc[n] = state[_prefix + n];
}
state._obs_acc = acc;

const haveAll = _obs.every(n => n in acc);
if (!haveAll) return [];

state._obs_acc = {};
const observation = _obs.map(n => typeof acc[n] === 'number' ? acc[n] : 0);
const stepCount = (state[_stepKey] || 0) + 1;
state[_stepKey] = stepCount;

let reward = 0;
const rtype = (_reward && _reward.type) ? _reward.type : 'setpoint';
if (rtype === 'setpoint') {
  const idx = _reward.observation_index != null ? _reward.observation_index : 0;
  const target = _reward.target != null ? _reward.target : (_reward.target_temp != null ? _reward.target_temp : 0);
  reward = -Math.abs((observation[idx] || 0) - target);
} else if (_reward && typeof _reward.reward === 'number') {
  reward = _reward.reward;
}
let done = state.done;
if (done === undefined || done === null) done = stepCount >= _maxSteps;

return [{ json: { observation, reward, done } }];
