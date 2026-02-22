// RLOracle template: thermodynamic mixing tank (Node-RED / EdgeLinkd)
// Step API: reset -> { observation, reward: 0, done: false }; step(action) -> { observation, reward, done }
// Placeholders (replaced by inject): {{PARAMS}}, {{OBSERVATION_NAMES}}, {{ACTION_NAMES}}

const PARAMS = {{PARAMS}};
const OBSERVATION_NAMES = {{OBSERVATION_NAMES}};
const ACTION_NAMES = {{ACTION_NAMES}};
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

if (msg.payload && msg.payload.reset) {
  const volRatio = Math.random() * 0.95;
  flow.set('hot_supply_temp', PARAMS.hot_water_temp);
  flow.set('cold_supply_temp', PARAMS.cold_water_temp);
  flow.set('hot_flow', 0);
  flow.set('cold_flow', 0);
  flow.set('dump_flow', 0);
  flow.set('volume', Math.max(0.01, PARAMS.tank_capacity * volRatio));
  flow.set('current_temp', PARAMS.initial_temp);
  flow.set('step_count', 0);
  const tMax = PARAMS.temp_max || 100;
  const obs = [
    PARAMS.cold_water_temp / tMax,
    PARAMS.hot_water_temp / tMax,
    PARAMS.initial_temp / tMax,
    flow.get('volume') / PARAMS.tank_capacity
  ];
  msg.payload = {
    observation: obs,
    observation_names: OBSERVATION_NAMES,
    action_names: ACTION_NAMES,
    reward: 0,
    done: false
  };
  msg.headers = { 'Content-Type': 'application/json' };
  return [msg, null];
}

const action = msg.payload.action || [0, 0, 0];
flow.set('action', action);
flow.set('http_msg', msg);

// One-step physics
const dt = PARAMS.dt || 0.1;
const cooling = PARAMS.mixed_water_cooling_rate || 0.01;
const ambient = PARAMS.ambient_temp || 20;
const cap = PARAMS.tank_capacity || 1;
const tMin = PARAMS.temp_min || 0;
const tMax = PARAMS.temp_max || 100;
const target = PARAMS.target_temp || 37;

let hotF = flow.get('hot_flow') || 0;
let coldF = flow.get('cold_flow') || 0;
let dumpF = flow.get('dump_flow') || 0;
hotF = clamp(hotF + (action[2] || 0) * 0.6, 0, 1);
coldF = clamp(coldF + (action[0] || 0) * 0.6, 0, 1);
dumpF = clamp(dumpF + (action[1] || 0) * 0.6, 0, 1);
flow.set('hot_flow', hotF);
flow.set('cold_flow', coldF);
flow.set('dump_flow', dumpF);

let hotT = flow.get('hot_supply_temp') || PARAMS.hot_water_temp;
let coldT = flow.get('cold_supply_temp') || PARAMS.cold_water_temp;
hotT = clamp(hotT + (Math.random() - 0.5) * 0.4, tMin, tMax);
coldT = clamp(coldT + (Math.random() - 0.5) * 0.4, tMin, tMax);
flow.set('hot_supply_temp', hotT);
flow.set('cold_supply_temp', coldT);

let vol = flow.get('volume') || 0.5;
let curTemp = flow.get('current_temp') || PARAMS.initial_temp;
const totIn = hotF + coldF;
const mixT = totIn > 0.001 ? (hotF * hotT + coldF * coldT) / totIn : curTemp;
const prevVol = Math.max(vol, 1e-6);
vol = clamp(prevVol - dumpF * dt + totIn * dt, 0.01, cap);
curTemp = (curTemp * Math.max(prevVol - dumpF * dt, 0) + mixT * totIn * dt) / vol;
curTemp = clamp(curTemp - cooling * (curTemp - ambient), tMin, tMax);
flow.set('volume', vol);
flow.set('current_temp', curTemp);

const step = (flow.get('step_count') || 0) + 1;
flow.set('step_count', step);

const tempErr = Math.abs(curTemp - target);
const volRatio = vol / cap;
let reward = -tempErr;
if (volRatio < 0.8) reward -= 0.5 * (0.8 - volRatio);
if (tempErr < 0.5) reward += 10; else if (tempErr < 1) reward += 5;
if (volRatio >= 0.8 && volRatio <= 0.85) reward += 10; else if (volRatio >= 0.75) reward += 5; else if (volRatio >= 0.7) reward += 2;
if (volRatio > 0.85) reward -= 2 * (volRatio - 0.85);
if (tempErr < 0.1 && volRatio >= 0.8 && volRatio <= 0.85) reward += 20;
reward -= 0.01 * (hotF + coldF) + 0.1 * dumpF;
if (dumpF < 0.05) reward += 0.3;

const done = (tempErr < 0.1 && volRatio >= 0.8 && volRatio <= 0.85) || step >= (PARAMS.max_steps || 600);

const obs = [
  clamp(coldT / tMax, 0, 1),
  clamp(hotT / tMax, 0, 1),
  clamp(curTemp / tMax, 0, 1),
  clamp(volRatio, 0, 1)
];

const httpMsg = flow.get('http_msg') || msg;
httpMsg.payload = { observation: obs, reward, done };
httpMsg.headers = { 'Content-Type': 'application/json' };
return [httpMsg, null];
