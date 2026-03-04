// Canonical StepDriver: trigger (reset|step) -> output 0 = start (to Split), output 1 = response.
// Placeholders: __TPL_UNIT_ID__ (optional, for flow keys)
var trigger = 'step';
if (msg.payload === 'reset' || (msg.payload && msg.payload.reset)) trigger = 'reset';
else if (msg.payload && msg.payload.action) trigger = 'step';
else if (typeof msg.payload === 'string') trigger = msg.payload;
if (trigger === 'reset') {
  return [{ payload: { action: 'start' } }, { payload: { action: 'idle' } }];
}
return [{ payload: { action: 'step' } }, {}];
