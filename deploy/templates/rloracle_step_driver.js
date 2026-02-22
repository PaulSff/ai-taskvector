// RLOracle step driver: universal, environment-agnostic.
// All params from training config (adapter_config). No embedded simulation.
// Reset: return initial observation (zeros or from context).
// Step: store action, store http_msg, trigger process. Collector sends response.
// Placeholders (replaced by oracle_inject): __TPL_OBS_NAMES__, __TPL_ACT_NAMES__, __TPL_OBS_PREFIX__, __TPL_STEP_KEY__

const _obs = __TPL_OBS_NAMES__;
const _act = __TPL_ACT_NAMES__;
const _prefix = __TPL_OBS_PREFIX__;
const _stepKey = __TPL_STEP_KEY__;

if (msg.payload && msg.payload.reset) {
  flow.set(_stepKey, 0);
  const obs = [];
  for (let i = 0; i < _obs.length; i++) {
    const key = _prefix + _obs[i];
    const v = flow.get(key);
    obs.push(typeof v === 'number' ? v : 0);
  }
  msg.payload = {
    observation: obs,
    observation_names: _obs,
    action_names: _act,
    reward: 0,
    done: false
  };
  msg.headers = { 'Content-Type': 'application/json' };
  return [msg, null];
}

flow.set('action', msg.payload.action || new Array(_act.length).fill(0));
flow.set('http_msg', msg);
return [null, msg];
