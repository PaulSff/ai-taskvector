// RLAgent predict for n8n Code node.
// Uses $input.all(), $getWorkflowStaticData, this.helpers.httpRequest.
// Placeholders: __TPL_INFERENCE_URL__, __TPL_OBS_IDS__
// Convention: upstream items have json.topic = observation_source_id, json.payload/value.

const _url = __TPL_INFERENCE_URL__;
const _obsIds = __TPL_OBS_IDS__;
const _prefix = 'rl_obs_';

function getVal(obj) {
  if (typeof obj === 'number') return obj;
  if (obj && typeof obj.value === 'number') return obj.value;
  if (obj && obj.temp != null) return obj.temp;
  if (obj && obj.volRatio != null) return obj.volRatio;
  return 0;
}

const state = $getWorkflowStaticData('global');
const acc = state[_prefix + 'obs'] || {};

for (const item of $input.all()) {
  const j = item.json;
  const key = j.topic || j.obs_id || '';
  if (key) acc[key] = getVal(j.payload !== undefined ? j.payload : (j.value !== undefined ? { value: j.value } : j));
}

state[_prefix + 'obs'] = acc;

const haveAll = _obsIds.every(function(id) { return id in acc; });
if (!haveAll) return [];

state[_prefix + 'obs'] = {};
const observation = _obsIds.map(function(id) { return typeof acc[id] === 'number' ? acc[id] : 0; });

const response = await this.helpers.httpRequest({
  method: 'POST',
  url: _url,
  body: { observation },
  json: true,
});

let action = response && response.action;
if (action === undefined || action === null) action = [0];
const out = Array.isArray(action) ? action : [Number(action)];

return [{ json: { payload: out } }];
