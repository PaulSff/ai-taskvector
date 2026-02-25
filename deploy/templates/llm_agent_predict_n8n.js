// LLMAgent predict for n8n Code node.
// Placeholders: __TPL_INFERENCE_URL__, __TPL_OBS_IDS__, __TPL_SYSTEM_PROMPT__,
//              __TPL_USER_PROMPT_TEMPLATE__, __TPL_MODEL_NAME__, __TPL_PROVIDER__, __TPL_HOST__
// Server: python -m server.llm_inference_server --port 8001

const _url = __TPL_INFERENCE_URL__;
const _obsIds = __TPL_OBS_IDS__;
const _systemPrompt = __TPL_SYSTEM_PROMPT__;
const _userPromptTemplate = __TPL_USER_PROMPT_TEMPLATE__;
const _modelName = __TPL_MODEL_NAME__;
const _provider = __TPL_PROVIDER__;
const _host = __TPL_HOST__;
const _prefix = 'llm_obs_';

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
  body: {
    observation,
    system_prompt: _systemPrompt,
    user_prompt_template: _userPromptTemplate,
    model_name: _modelName,
    provider: _provider,
    host: _host || ''
  },
  json: true,
});

let action = response && response.action;
if (action === undefined || action === null) action = [0];
const out = Array.isArray(action) ? action : [Number(action)];

return [{ json: { payload: out } }];
