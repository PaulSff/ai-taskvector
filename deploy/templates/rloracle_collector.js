// RLOracle collector: builds observation vector, computes reward from config, sends response.
// All params from training config. No embedded simulation.
// Convention: (a) sensors send msgs with topic=observation_name, payload=value; or
// (b) process writes flow.set(OBS_PREFIX + name, value).
// Placeholders (replaced by oracle_inject): __TPL_OBS_NAMES__, __TPL_REWARD__, __TPL_MAX_STEPS__, __TPL_OBS_PREFIX__, __TPL_STEP_KEY__

const _obs = __TPL_OBS_NAMES__;
const _reward = __TPL_REWARD__;
const _maxSteps = __TPL_MAX_STEPS__;
const _prefix = __TPL_OBS_PREFIX__;
const _stepKey = __TPL_STEP_KEY__;

function getVal(payload) {
  if (typeof payload === 'number') return payload;
  if (payload && typeof payload.value === 'number') return payload.value;
  if (payload && payload.temp != null) return payload.temp;
  if (payload && payload.volRatio != null) return payload.volRatio;
  return 0;
}

let obs = flow.get('obs') || {};
const name = msg.topic || msg.obs_name;
if (name) obs[name] = getVal(msg.payload);
for (let i = 0; i < _obs.length; i++) {
  const n = _obs[i];
  if (!(n in obs)) {
    const ctxVal = flow.get(_prefix + n);
    if (typeof ctxVal === 'number') obs[n] = ctxVal;
  }
}
flow.set('obs', obs);

const haveAll = _obs.every(n => n in obs);
if (!haveAll) return null;

flow.set('obs', {});

const observation = _obs.map(n => (typeof obs[n] === 'number' ? obs[n] : 0));

const stepCount = (flow.get(_stepKey) || 0) + 1;
flow.set(_stepKey, stepCount);

let reward = 0;
const rtype = _reward && _reward.type ? _reward.type : 'setpoint';
if (rtype === 'setpoint') {
  const idx = _reward.observation_index != null ? _reward.observation_index : 0;
  const target = _reward.target != null ? _reward.target : (_reward.target_temp != null ? _reward.target_temp : 0);
  reward = -Math.abs((observation[idx] || 0) - target);
} else if (_reward && typeof _reward.reward === 'number') {
  reward = _reward.reward;
}

let done = flow.get('done');
if (done === undefined || done === null) {
  done = stepCount >= _maxSteps;
}

const httpMsg = flow.get('http_msg') || msg;
httpMsg.payload = { observation, reward, done };
httpMsg.headers = { 'Content-Type': 'application/json' };
return httpMsg;
