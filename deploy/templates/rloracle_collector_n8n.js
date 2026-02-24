// RLOracle collector for n8n. Aggregates observations, computes reward, returns response.
// For formula/rules reward: requires expr-eval. Set NODE_FUNCTION_ALLOW_EXTERNAL=expr-eval and:
//   npm install expr-eval (in n8n environment)
// Placeholders: __TPL_OBS_NAMES__, __TPL_REWARD__, __TPL_MAX_STEPS__, __TPL_OBS_PREFIX__, __TPL_STEP_KEY__

const _obs = __TPL_OBS_NAMES__;
const _reward = __TPL_REWARD__;
const _maxSteps = __TPL_MAX_STEPS__;
const _prefix = __TPL_OBS_PREFIX__;
const _stepKey = __TPL_STEP_KEY__;
const state = $getWorkflowStaticData('global');

function getVal(obj) {
  if (typeof obj === 'number') return obj;
  if (obj && typeof obj.value === 'number') return obj.value;
  if (obj && obj.temp != null) return obj.temp;
  if (obj && obj.volRatio != null) return obj.volRatio;
  return 0;
}

const acc = state._obs_acc || {};
for (const item of $input.all()) {
  const j = item.json;
  const name = j.topic || j.obs_name || j.name;
  if (name) acc[name] = getVal(j.payload ?? (j.value !== undefined ? { value: j.value } : j));
}
for (const n of _obs) {
  if (!(n in acc) && typeof state[_prefix + n] === 'number') acc[n] = state[_prefix + n];
}
state._obs_acc = acc;

const haveAll = _obs.every(n => n in acc);
if (!haveAll) return [];

state._obs_acc = {};
const observation = _obs.map(n => typeof acc[n] === 'number' ? acc[n] : 0);
const stepCount = (state[_stepKey] || 0) + 1;
state[_stepKey] = stepCount;

// Build outputs { unit_id: { port: value } } from obs names
const outputs = {};
for (const n of _obs) {
  const v = typeof acc[n] === 'number' ? acc[n] : 0;
  const parts = n.split('.');
  const uid = parts.length > 1 ? parts[0] : 'obs';
  const port = parts.length > 1 ? parts.slice(1).join('.') : n;
  if (!outputs[uid]) outputs[uid] = {};
  outputs[uid][port] = v;
}

let reward = 0;
let usedEvaluator = false;

if (_reward && typeof _reward === 'object' && (_reward.formula || _reward.rules)) {
  try {
    const exprEval = require('expr-eval');
    const Parser = exprEval.Parser;
    if (Parser) {
      const goalDict = _reward.goal || {};
      const goal = Object.assign({}, goalDict, {
        get: function(k, d) { return (k in goalDict && goalDict[k] != null) ? goalDict[k] : d; }
      });
      const get = function(obj, path, def) {
        if (obj == null || !path) return def;
        const keys = path.split('.');
        let cur = obj;
        for (let i = 0; i < keys.length; i++) {
          if (cur == null || typeof cur !== 'object') return def;
          cur = cur[keys[i]];
        }
        if (typeof cur === 'number') return cur;
        if (Array.isArray(cur) && cur.length) return typeof cur[0] === 'number' ? cur[0] : def;
        return def;
      };
      const scope = {
        outputs, goal, observation, step_count: stepCount, max_steps: _maxSteps,
        action: state.action || [],
        get, abs: Math.abs, min: Math.min, max: Math.max
      };
      const parser = new Parser();
      if (_reward.formula && Array.isArray(_reward.formula)) {
        for (const comp of _reward.formula) {
          if (!comp || !comp.expr) continue;
          try {
            const val = parser.evaluate(comp.expr, scope);
            if (comp.weight != null) reward += comp.weight * Number(val);
            else if (comp.reward != null && val) reward += comp.reward;
          } catch (e) {}
        }
      }
      if (_reward.rules && Array.isArray(_reward.rules)) {
        for (const r of _reward.rules) {
          if (!r || !r.condition) continue;
          try {
            if (parser.evaluate(r.condition, scope)) reward += Number(r.reward_delta || 0);
          } catch (e) {}
        }
      }
      usedEvaluator = true;
    }
  } catch (e) {}
}

if (!usedEvaluator) {
  const rtype = (_reward && _reward.type) ? _reward.type : 'setpoint';
  if (rtype === 'setpoint') {
    const idx = _reward.observation_index != null ? _reward.observation_index : 0;
    const target = _reward.target != null ? _reward.target : (_reward.target_temp != null ? _reward.target_temp : 0);
    reward = -Math.abs((observation[idx] || 0) - target);
  } else if (_reward && typeof _reward.reward === 'number') {
    reward = _reward.reward;
  }
}

let done = state.done;
if (done === undefined || done === null) done = stepCount >= _maxSteps;

return [{ json: { observation, reward, done } }];
