# LLMAgent predict: build observation from inputs, POST to LLM inference service, return action.
# Placeholders: __TPL_INFERENCE_URL__, __TPL_OBS_SOURCE_IDS__, __TPL_SYSTEM_PROMPT__,
#              __TPL_USER_PROMPT_TEMPLATE__, __TPL_MODEL_NAME__, __TPL_PROVIDER__, __TPL_HOST__
# Server: python -m server.llm_inference_server --port 8001

import urllib.request
import json

_url = __TPL_INFERENCE_URL__
_obs_ids = __TPL_OBS_SOURCE_IDS__
_system_prompt = __TPL_SYSTEM_PROMPT__
_user_prompt_template = __TPL_USER_PROMPT_TEMPLATE__
_model_name = __TPL_MODEL_NAME__
_provider = __TPL_PROVIDER__
_host = __TPL_HOST__

def _get_val(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)) and v:
        return float(v[0])
    if isinstance(v, dict):
        if "value" in v:
            return float(v["value"])
        if "temp" in v:
            return float(v["temp"])
        if "volRatio" in v:
            return float(v["volRatio"])
    return 0.0

observation = [_get_val(inputs.get(sid)) for sid in _obs_ids]
body = json.dumps({
    "observation": observation,
    "system_prompt": _system_prompt,
    "user_prompt_template": _user_prompt_template,
    "model_name": _model_name,
    "provider": _provider,
    "host": _host or "",
}).encode("utf-8")
req = urllib.request.Request(_url, data=body, method="POST", headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60.0) as resp:
    data = json.loads(resp.read().decode())
action = data.get("action")
if action is None:
    out = [0.0] * max(1, len(_obs_ids))
elif isinstance(action, (list, tuple)):
    out = [float(x) for x in action]
else:
    out = [float(action)]
return out
