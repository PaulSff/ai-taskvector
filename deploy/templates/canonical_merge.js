// Canonical Merge: accumulate in_0..in_{n-1} from msg.topic, output { data: { key: value, ... } }.
// Placeholders: __TPL_NUM_INPUTS__, __TPL_UNIT_ID__, __TPL_KEYS_JSON__
const _n = __TPL_NUM_INPUTS__;
const _id = __TPL_UNIT_ID__ || 'merge';
const _keys = __TPL_KEYS_JSON__;  // JSON array of key names, e.g. ["user_message","rag","graph_summary"]
const key = (msg.topic || '').toString();
let idx = -1;
if (/^in_\d+$/.test(key)) idx = parseInt(key.replace('in_', ''), 10);
else if (key) idx = 0;
if (idx < 0 || idx >= _n) return null;
const state = flow.get(_id + '_merge') || {};
state['in_' + idx] = msg.payload;
flow.set(_id + '_merge', state);
const keys = typeof _keys === 'string' ? JSON.parse(_keys) : _keys;
const data = {};
for (let i = 0; i < _n; i++) {
  const k = Array.isArray(keys) && keys[i] != null ? keys[i] : ('in_' + i);
  data[k] = state['in_' + i];
}
return { payload: { data: data } };
