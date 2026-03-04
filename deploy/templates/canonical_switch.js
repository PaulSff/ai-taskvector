// Canonical Switch: action vector → out_0, out_1, ... (one msg per output).
// Placeholders: __TPL_NUM_OUTPUTS__, __TPL_UNIT_ID__
const _n = __TPL_NUM_OUTPUTS__;
const _id = __TPL_UNIT_ID__ || 'switch';
let action = msg.payload;
if (!Array.isArray(action)) action = (action != null && typeof action === 'object' && Array.isArray(action.action)) ? action.action : [action];
action = action.map(function (x) { return typeof x === 'number' ? x : parseFloat(x) || 0; });
const out = [];
for (let i = 0; i < _n; i++) {
  out.push({ payload: action[i] != null ? action[i] : 0 });
}
return out;
