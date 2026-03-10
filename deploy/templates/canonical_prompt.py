# Canonical Prompt (PyFlow): data (dict) + embedded template -> system_prompt.
# Placeholders: __TPL_TEMPLATE__ (repr of template string), __TPL_FORMAT_KEYS_JSON__ (Python list literal)
# Inputs: data (dict). Output: system_prompt (str).
import json
import re
_template = __TPL_TEMPLATE__
_format_keys = __TPL_FORMAT_KEYS_JSON__
data = inputs.get("data") if isinstance(inputs.get("data"), dict) else {}
_placeholder_re = re.compile(r"\{\w+\}")
def _repl(m):
    key = m.group(1)
    val = data.get(key)
    if key in _format_keys and val is not None:
        if isinstance(val, (dict, list)):
            return json.dumps(val, indent=2)
        return str(val)
    if val is None:
        return ""
    return str(val)
system_prompt = _placeholder_re.sub(_repl, _template)
return {"system_prompt": system_prompt}, state
