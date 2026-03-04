// Canonical Split: one input → fan-out to n outputs (same message each).
// Placeholders: __TPL_NUM_OUTPUTS__, __TPL_UNIT_ID__
const _n = __TPL_NUM_OUTPUTS__;
const _id = __TPL_UNIT_ID__ || 'split';
const val = msg.payload != null ? msg.payload : msg;
const out = [];
for (let i = 0; i < _n; i++) out.push({ payload: val });
return out;
