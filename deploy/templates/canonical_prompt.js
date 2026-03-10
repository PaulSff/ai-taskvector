// Canonical Prompt (Node-RED/n8n): msg.payload.data + embedded template -> system_prompt.
// Placeholders: __TPL_TEMPLATE__ (JSON.stringify(template)), __TPL_FORMAT_KEYS_JSON__ (JSON array string), __TPL_UNIT_ID__
const _template = __TPL_TEMPLATE__;
const _formatKeys = typeof __TPL_FORMAT_KEYS_JSON__ === 'string' ? JSON.parse(__TPL_FORMAT_KEYS_JSON__) : __TPL_FORMAT_KEYS_JSON__;
const data = (msg.payload && typeof msg.payload.data === 'object') ? msg.payload.data : {};
const placeholderRe = /\{(\w+)\}/g;
function repl(_, key) {
  const val = data[key];
  if (_formatKeys.indexOf(key) >= 0 && val != null) {
    if (typeof val === 'object') return JSON.stringify(val, null, 2);
    return String(val);
  }
  if (val == null) return '';
  return String(val);
}
const systemPrompt = _template.replace(placeholderRe, repl);
return { payload: { system_prompt: systemPrompt } };
