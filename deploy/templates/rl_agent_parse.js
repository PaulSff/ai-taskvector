// RLAgent parse: extract action from inference service response.
// Input: msg.payload from http request = { action: [float, ...] } or { action: float }
// Output: msg.payload = action (array or scalar) for downstream action targets.

const body = msg.payload;
if (!body || typeof body !== 'object') {
  node.warn('RLAgent: invalid response, expected { action: [...] }');
  return null;
}
const action = body.action;
if (action === undefined || action === null) {
  node.warn('RLAgent: response missing action field');
  return null;
}
msg.payload = Array.isArray(action) ? action : [Number(action)];
return msg;
