// RLAgent predict: single function node (Node-RED).
// Accumulates observations by msg.topic, POSTs to inference service, outputs action.
// Placeholders: __TPL_INFERENCE_URL__, __TPL_OBS_IDS__
// Convention: upstream nodes send msg.topic = observation_source_id, msg.payload = value.

const _url = __TPL_INFERENCE_URL__;
const _obsIds = __TPL_OBS_IDS__;
const _prefix = 'rl_obs_';

function getVal(payload) {
  if (typeof payload === 'number') return payload;
  if (payload && typeof payload.value === 'number') return payload.value;
  if (payload && payload.temp != null) return payload.temp;
  if (payload && payload.volRatio != null) return payload.volRatio;
  return 0;
}

let acc = flow.get(_prefix + 'obs') || {};
const key = msg.topic || msg.obs_id || '';
if (key) acc[key] = getVal(msg.payload);
flow.set(_prefix + 'obs', acc);

const haveAll = _obsIds.every(function(id) { return id in acc; });
if (!haveAll) return null;

flow.set(_prefix + 'obs', {});
const observation = _obsIds.map(function(id) { return typeof acc[id] === 'number' ? acc[id] : 0; });

return new Promise(function(resolve, reject) {
  const opts = require('url').parse(_url);
  opts.method = 'POST';
  opts.headers = { 'Content-Type': 'application/json' };
  const lib = opts.protocol === 'https:' ? require('https') : require('http');
  const body = JSON.stringify({ observation: observation });
  const req = lib.request(opts, function(res) {
    let data = '';
    res.on('data', function(chunk) { data += chunk; });
    res.on('end', function() {
      try {
        const parsed = JSON.parse(data || '{}');
        let action = parsed.action;
        if (action === undefined || action === null) {
          action = [0];
        }
        msg.payload = Array.isArray(action) ? action : [Number(action)];
        resolve([msg]);
      } catch (e) {
        node.warn('RLAgent: parse error ' + e.message);
        msg.payload = [0];
        resolve([msg]);
      }
    });
  });
  req.on('error', function(e) {
    node.warn('RLAgent: request error ' + e.message);
    msg.payload = [0];
    resolve([msg]);
  });
  req.write(body);
  req.end();
});
