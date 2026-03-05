// Canonical StepRewards (Node-RED/n8n): observation from Join (msg.payload), trigger/step_count from flow.
// Same semantics as our runtime. Placeholders: __TPL_UNIT_ID__, __TPL_MAX_STEPS__, __TPL_REWARD__, __TPL_STEP_KEY__
// For formula/rules reward: Node-RED settings.js functionGlobalContext: { exprEval: require('expr-eval') }

const _id = __TPL_UNIT_ID__ || 'step_rewards';
const _maxSteps = __TPL_MAX_STEPS__;
const _reward = __TPL_REWARD__;
const _stepKey = __TPL_STEP_KEY__;

function toObs(payload) {
  if (payload == null) return [];
  if (Array.isArray(payload)) return payload.map(x => typeof x === 'number' ? x : parseFloat(x) || 0);
  return [typeof payload === 'number' ? payload : parseFloat(payload) || 0];
}

const observation = toObs(msg.payload);
const trigger = msg.trigger || flow.get(_id + '_trigger') || 'step';

let stepCount = flow.get(_stepKey) || 0;
if (trigger === 'reset') stepCount = 0;
else stepCount += 1;
flow.set(_stepKey, stepCount);

const done = stepCount >= _maxSteps;

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
      const outputs = { observation: {} };
      observation.forEach((v, i) => { outputs.observation[String(i)] = v; });
      const scope = {
        outputs, goal, observation, step_count: stepCount, max_steps: _maxSteps,
        action: flow.get('action') || [], get, abs: Math.abs, min: Math.min, max: Math.max
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

msg.payload = { observation, reward, done };
return msg;
