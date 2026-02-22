// RLAgent prepare: accumulate observations, build request for inference service.
// Convention: sensors send msgs with topic=observation_name, payload=value.
// Placeholders: __TPL_OBS_NAMES__, __TPL_OBS_PREFIX__
// Output: msg.url, msg.method, msg.payload, msg.headers → to http request node.

const _obs = __TPL_OBS_NAMES__;
const _prefix = __TPL_OBS_PREFIX__;

function getVal(payload) {
  if (typeof payload === 'number') return payload;
  if (payload && typeof payload.value === 'number') return payload.value;
  if (payload && payload.temp != null) return payload.temp;
  if (payload && payload.volRatio != null) return payload.volRatio;
  return 0;
}

let acc = flow.get(_prefix + 'obs') || {};
const name = msg.topic || msg.obs_name;
if (name) acc[name] = getVal(msg.payload);
flow.set(_prefix + 'obs', acc);

const haveAll = _obs.every(n => n in acc);
if (!haveAll) return null;

flow.set(_prefix + 'obs', {});
const observation = _obs.map(n => (typeof acc[n] === 'number' ? acc[n] : 0));

msg.url = __TPL_INFERENCE_URL__;
msg.method = 'POST';
msg.payload = { observation };
msg.headers = { 'Content-Type': 'application/json' };
return msg;
