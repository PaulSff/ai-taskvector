// RLOracle collector: builds observation vector, computes reward from config, sends response.
// All params from training config. No embedded simulation.
// For formula/rules reward: requires expr-eval. Node-RED: add to settings.js functionGlobalContext:
//   exprEval: require('expr-eval')
// Then: cd ~/.node-red && npm install expr-eval
// Placeholders: __TPL_OBS_NAMES__, __TPL_REWARD__, __TPL_MAX_STEPS__, __TPL_OBS_PREFIX__, __TPL_STEP_KEY__

const _obs = __TPL_OBS_NAMES__;
const _reward = __TPL_REWARD__;
const _maxSteps = __TPL_MAX_STEPS__;
const _prefix = __TPL_OBS_PREFIX__;
const _stepKey = __TPL_STEP_KEY__;

function getVal(payload) {
  if (typeof payload === 'number') return payload;
  if (payload && typeof payload.value === 'number') return payload.value;
  if (payload && payload.temp != null) return payload.temp;
  if (payload && payload.volRatio != null) return payload.volRatio;
  return 0;
}

let obs = flow.get('obs') || {};
const name = msg.topic || msg.obs_name;
if (name) obs[name] = getVal(msg.payload);
for (let i = 0; i < _obs.length; i++) {
  const n = _obs[i];
  if (!(n in obs)) {
    const ctxVal = flow.get(_prefix + n);
    if (typeof ctxVal === 'number') obs[n] = ctxVal;
  }
}
flow.set('obs', obs);

const haveAll = _obs.every(n => n in obs);
if (!haveAll) return null;

flow.set('obs', {});

const observation = _obs.map(n => (typeof obs[n] === 'number' ? obs[n] : 0));

const stepCount = (flow.get(_stepKey) || 0) + 1;
flow.set(_stepKey, stepCount);

// Build outputs { unit_id: { port: value } } from obs names (e.g. "mixer_tank.temp" -> outputs.mixer_tank.temp)
const outputs = {};
for (const n of _obs) {
  const v = typeof obs[n] === 'number' ? obs[n] : 0;
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
    const exprEval = global.get('exprEval');
    if (exprEval && exprEval.Parser) {
      const Parser = exprEval.Parser;
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
        action: flow.get('action') || [],
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
  const rtype = _reward && _reward.type ? _reward.type : 'setpoint';
  if (rtype === 'setpoint') {
    const idx = _reward.observation_index != null ? _reward.observation_index : 0;
    const target = _reward.target != null ? _reward.target : (_reward.target_temp != null ? _reward.target_temp : 0);
    reward = -Math.abs((observation[idx] || 0) - target);
  } else if (_reward && typeof _reward.reward === 'number') {
    reward = _reward.reward;
  }
}

let done = flow.get('done');
if (done === undefined || done === null) {
  done = stepCount >= _maxSteps;
}

const httpMsg = flow.get('http_msg') || msg;
httpMsg.payload = { observation, reward, done };
httpMsg.headers = { 'Content-Type': 'application/json' };
return httpMsg;
