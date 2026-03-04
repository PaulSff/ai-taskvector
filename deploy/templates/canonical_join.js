// Canonical Join: accumulate in_0..in_{n-1} from msg.topic, output observation array.
// Placeholders: __TPL_NUM_INPUTS__, __TPL_UNIT_ID__
const _n = __TPL_NUM_INPUTS__;
const _id = __TPL_UNIT_ID__ || 'collector';
const key = (msg.topic || '').toString();
let idx = -1;
if (/^in_\d+$/.test(key)) idx = parseInt(key.replace('in_', ''), 10);
else if (key) idx = 0;
if (idx < 0 || idx >= _n) return null;
const state = flow.get(_id + '_join') || {};
let val = msg.payload;
if (typeof val === 'object' && val !== null && 'value' in val) val = val.value;
if (typeof val === 'object' && val !== null && 'temp' in val) val = val.temp;
state['in_' + idx] = typeof val === 'number' ? val : parseFloat(val) || 0;
flow.set(_id + '_join', state);
const obs = [];
for (let i = 0; i < _n; i++) obs.push(state['in_' + i] != null ? state['in_' + i] : 0);
return { payload: obs };
