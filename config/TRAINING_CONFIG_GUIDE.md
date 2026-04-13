# Training config guide

How to create a training config for each pipeline (custom, Node-RED, PyFlow, ComfyUI) and how to set reward behaviour: **preset + weights**, **formula DSL**, and **rule-engine rules** (natural-language reward edits use the **RL Coach** in the app).

---

## 1. Pipeline overview

| Pipeline | `environment.source` | When to use |
|----------|----------------------|-------------|
| **Native** | `native` | In-process `GraphEnv` from a canonical process graph (YAML). No external runtime. |
| **Node-RED** | `external` + `adapter: node_red` | Flow runs in Node-RED; training talks to it via HTTP `POST /step`. |
| **n8n** | `external` + `adapter: n8n` | Flow runs in n8n; training talks to webhook via HTTP (same step/reset contract as Node-RED). |
| **PyFlow** | `external` + `adapter: pyflow` | Graph runs in-process via our executor; no Node-RED or PyFlow app. |
| **ComfyUI** | `external` + `adapter: comfyui` | Workflow runs in ComfyUI; training talks to the bridge via HTTP `POST /step`. |

Examples for each pipeline live under `config/examples/`:

- `native_runtime_factory/native_AI_temperature-control-agent/`
- `node-red_runtime/node-red_AI_temperature-control-agent/`
- `pyflow_runtime/pyflow_AI_temperature-control-agent/`

---

## 2. Creating a training config per pipeline

Every training config shares the same top-level keys: **environment**, **goal**, **rewards**, **algorithm**, **hyperparameters**, **total_timesteps**, **run**, **callbacks**. Only the **environment** block and a few run settings differ by pipeline.

### 2.1 Custom (env_factory)

Use when the env is built from a **canonical process graph** (YAML) by `env_factory`; no Node-RED or PyFlow.

```yaml
environment:
  source: native
  type: thermodynamic
  process_graph_path: "config/examples/native_runtime_factory/native_AI_temperature-control-agent/temperature_process.yaml"
goal:
  type: setpoint
  target_temp: 37.0
  target_volume_ratio: [0.80, 0.85]
rewards:
  preset: temperature_and_volume
  weights:
    temp_error: -1.0
    volume_in_range: 10.0
    dumping: -0.1
    step_penalty: -0.001
# ... algorithm, hyperparameters, run, callbacks (see examples)
callbacks:
  model_dir: "models/native_AI_temperature-control-agent"
```

- **process_graph_path**: Path to the process graph YAML (relative to repo root when you run `runtime/train.py`). Can be overridden by CLI `--process-config`.
- **type**: `thermodynamic`, `data_bi`, or `web` for native.
- The process graph must contain exactly one **RLAgent** unit with inputs and outputs wired; see `env_factory/factory.py` and `docs/TEMPERATURE_CONTROL_WORKFLOW.md`.

**Run:**  
`python runtime/train.py --config <path-to-this-config.yaml>`

---

### 2.2 Node-RED

Use when the temperature flow runs in **Node-RED** and exposes `POST /step` (reset + action → observation, reward, done).

```yaml
environment:
  source: external
  adapter: node_red
  adapter_config:
    step_url: "http://127.0.0.1:1880/step"
    # timeout: 10   # optional, seconds
goal:
  type: setpoint
  target_temp: 37.0
  target_volume_ratio: [0.80, 0.85]
rewards:
  preset: temperature_and_volume
  weights:
    temp_error: -1.0
    volume_in_range: 10.0
    dumping: -0.1
    step_penalty: -0.001
run:
  n_envs: 1   # external runtime is single-instance
  randomize_params: false
callbacks:
  model_dir: "models/node-red_AI_temperature-control-agent"
```

- **step_url**: URL of the Node-RED flow’s step endpoint. Must match the flow you deployed.
- **n_envs**: For external adapters, use `1`.
- Deploy the **wired** flow in Node-RED so observation/action order matches the agent; see `config/examples/node-red_runtime/.../temperature_process_node_red_wired.json`.

**Run:**  
Start Node-RED with the wired flow deployed, then:  
`python runtime/train.py --config config/examples/node-red_runtime/node-red_AI_temperature-control-agent/training_config_node_red.yaml`

---

### 2.2a n8n

Use when the flow runs in **n8n** and exposes the same step/reset contract via a webhook (e.g. after adding RLOracle via add_pipeline and exporting the graph to n8n). The workflow must be **active**; use the production webhook URL.

```yaml
environment:
  source: external
  adapter: n8n
  adapter_config:
    step_url: "https://your-n8n.example.com/webhook/step"   # or http://127.0.0.1:5678/webhook/step
    timeout: 10
    observation_spec:
      - name: sensor1
      - name: sensor2
    action_spec:
      - name: actuator1
        min: 0.0
        max: 1.0
goal:
  type: setpoint
  # ...
rewards:
  preset: temperature_and_volume
  # ...
run:
  n_envs: 1
callbacks:
  model_dir: "models/n8n_AI_my-agent"
```

- **step_url**: Production webhook URL of the n8n workflow (path from the Webhook node when the workflow is active).
- Same **adapter_config** shape as Node-RED: `observation_spec`, `action_spec`, optional `reward_config`, `max_steps`, `timeout`.

---

### 2.3 PyFlow

Use when the graph is run **in-process** by our PyFlow adapter (no PyFlow app or HTTP).

```yaml
environment:
  source: external
  adapter: pyflow
  adapter_config:
    flow_path: "config/examples/pyflow_runtime/pyflow_AI_temperature-control-agent/temperature_process_pyflow_wired.json"
    observation_sources: ["cold_supply", "hot_supply", "thermometer_tank", "water_level"]
    action_targets: ["cold_valve", "dump_valve", "hot_valve"]
    reward_node: "reward"
    goal:
      target_temp: 37.0
goal:
  type: setpoint
  target_temp: 37.0
  target_volume_ratio: [0.80, 0.85]
rewards:
  preset: temperature_and_volume
  weights:
    temp_error: -1.0
    volume_in_range: 10.0
    dumping: -0.1
    step_penalty: -0.001
run:
  n_envs: 1
  randomize_params: false
callbacks:
  model_dir: "models/pyflow_AI_temperature-control-agent"
```

- **flow_path**: Path to the PyFlow JSON (wired graph recommended).
- **observation_sources**: Node ids whose outputs are concatenated into the observation vector (order matters).
- **action_targets**: Node ids that receive the action vector (e.g. the three valves).
- **reward_node**: Optional; node id whose output is the step reward. If omitted, goal-based reward can be used.
- **done_node**: Optional; node id whose output is the episode-terminated flag (for episodic envs, e.g. filter step flow).

**Run:**  
`python runtime/train.py --config config/examples/pyflow_runtime/pyflow_AI_temperature-control-agent/training_config_pyflow.yaml`

---

### 2.4 ComfyUI

Use when the workflow runs in **ComfyUI** and you drive it via the RL bridge (which exposes `POST /step`).

```yaml
environment:
  source: external
  adapter: comfyui
  adapter_config:
    step_url: "http://127.0.0.1:8189/step"
    observation_spec: [{ "name": "obs_0" }, ...]
    action_spec: [{ "name": "act_0" }, ...]
run:
  n_envs: 1
callbacks:
  model_dir: "models/comfyui_AI_my-agent"
```

- **step_url**: URL of the ComfyUI bridge (run `python -m server.comfyui_bridge --workflow workflow.json --port 8189`).
- **observation_spec** / **action_spec**: Same as Node-RED; defines observation and action names for the Oracle.

See **deploy/README.md** for ComfyUI setup (custom nodes, bridge, adapter).

---

## 3. Reward configuration options

Reward is configured under the **rewards** key. Three mechanisms in config:

1. **Preset + weights** (custom env; legacy)  
2. **Formula DSL** (Oracle pipelines: Node-RED, n8n, PyFlow, ComfyUI; primary for RL Coach edits)  
3. **Rule-engine rules** (optional; condition → reward_delta)  

Natural language → reward edits are done in-app via the **RL Coach**. To merge a hand-written JSON edit from scripts, use `gui.components.workflow_tab.workflows.core_workflows.run_apply_training_config_edits` (see `scripts/test_assistants.py`) or `runtime.run.run_workflow` on `gui/components/workflow_tab/workflows/core_workflows/apply_training_config_edits_single.json`.

### 3.1 Preset and weights

Standard option; used by all pipelines.

```yaml
rewards:
  preset: temperature_and_volume   # temperature_and_volume | pressure_control | goal_reaching | exploration
  weights:
    temp_error: -1.0
    volume_in_range: 10.0
    dumping: -0.1
    step_penalty: -0.001
```

- **preset**: Selects the reward *structure* the env uses (e.g. which terms exist).
- **weights**: Scaling of each term (negative = penalty, positive = bonus). Names depend on the preset and env (e.g. `temp_error`, `volume_in_range`, `dumping`, `step_penalty` for temperature control).

Custom env (GraphEnv) uses preset+weights. Oracle-based flows (Node-RED, n8n, PyFlow, ComfyUI) use **formula** and **rules** from the rewards pipeline; when present, these override preset/weights for the collector.

### 3.2 Formula DSL (Oracle pipelines)

Oracle collector nodes use the **formula** DSL: Python-like expressions evaluated by [asteval](https://github.com/newville/asteval). Each component has `expr` plus either `weight` (continuous) or `reward` (conditional bonus). Context: `outputs`, `goal`, `observation`, `step_count`, `max_steps`.

```yaml
rewards:
  formula:
    - expr: "-abs(get(outputs, 'mixer_tank.temp', 0) - goal.get('target_temp', 37))"
      weight: 1.0
    - expr: "get(outputs, 'dump_valve.flow', 0)"
      weight: -0.1
    - expr: "0.8 <= get(outputs, 'mixer_tank.volume_ratio', 0) <= 0.85"
      reward: 10.0
```

The RL Coach edits rewards via `reward_formula_add`, `reward_formula_set`, `reward_rules_add`, `reward_rules_set`; these produce merged formula/rules. See **rewards/README.md** for full DSL reference.

### 3.3 Rule-engine rules (condition → reward_delta)

Optional **rules** list: each rule has a **condition** (expression) and a **reward_delta**. At step time the env builds a state dict; any rule whose condition matches adds its `reward_delta` to the reward. Implemented in `rewards/rules.py` using the [rule-engine](https://pypi.org/project/rule-engine/) package.

**Schema** (see `schemas/training_config.py`):

- **condition**: String expression over state variables (e.g. `temp_error > 5`, `volume_ratio < 0.8`).
- **reward_delta**: Number added to the reward when the condition is true.

**Example:**

```yaml
rewards:
  preset: temperature_and_volume
  weights:
    temp_error: -1.0
    volume_in_range: 10.0
    dumping: -0.1
    step_penalty: -0.001
  rules:
    - condition: "temp_error > 5"
      reward_delta: -2.0
    - condition: "volume_ratio >= 0.8 and volume_ratio <= 0.85"
      reward_delta: 5.0
    - condition: "dump_flow > 0.5"
      reward_delta: -0.5
```

**State variables** (for the custom thermodynamic env) available in conditions:  
`temp_error`, `volume`, `volume_ratio`, `hot_flow`, `cold_flow`, `dump_flow`, `target_temp`, `current_temp`, `step_count`.  
See `environments/graph_env.py`, `environments/native/thermodynamics/spec.py`, and `rewards/evaluate_rules` (state dict passed to `evaluate_rules`).

**Requirement:** `pip install rule-engine`. If not installed, `evaluate_rules` returns 0.0 and rules are skipped.

**Where it runs:** Custom env applies rules in `step()`. Oracle collector applies both formula and rules via `evaluate_reward()` from the rewards pipeline.

---

## 4. Full config skeleton

Use this as a template; adjust **environment** for your pipeline and **rewards** as needed.

```yaml
environment:
  source: native | external | gymnasium
  # --- if native ---
  type: thermodynamic
  process_graph_path: "path/to/process.yaml"
  # --- if external ---
  adapter: node_red | pyflow | comfyui | edgelinkd | idaes
  adapter_config:
    step_url: "..."           # Node-RED/ComfyUI: step endpoint
    flow_path: "..."          # PyFlow: wired flow JSON
    observation_spec: [...]   # optional; names + ranges (Oracle)
    action_spec: [...]        # optional; names + ranges (Oracle)
    # observation_sources, action_targets, reward_config, max_steps, etc.
  # --- if gymnasium ---
  env_id: "CartPole-v1"
  env_kwargs: {}

goal:
  type: setpoint
  target_temp: 37.0
  target_volume_ratio: [0.80, 0.85]

rewards:
  preset: temperature_and_volume
  weights:
    temp_error: -1.0
    volume_in_range: 10.0
    dumping: -0.1
    step_penalty: -0.001
  formula: []   # optional: list of { expr: "...", weight: float } or { expr: "...", reward: float }
  rules: []     # optional: list of { condition: "...", reward_delta: float }

algorithm: PPO
total_timesteps: 100000
run:
  n_envs: 4
  randomize_params: true
  verbose: 1
  test_episodes: 5
callbacks:
  model_dir: "models/my-agent"
  eval_freq: 5000
  save_freq: 10000
  name_prefix: "ppo"
hyperparameters:
  learning_rate: 3.0e-4
  n_steps: 2048
  batch_size: 64
  n_epochs: 10
  gamma: 0.99
  gae_lambda: 0.95
  clip_range: 0.2
  ent_coef: 0.01
```

---

## 5. Reference

- **Schema:** `schemas/training_config.py` (EnvironmentConfig, GoalConfig, RewardsConfig, FormulaComponent, RewardRule, etc.)
- **Rewards pipeline (formula + rules):** `rewards/README.md`
- **Reward rules and RL Coach:** `docs/REWARD_RULES.md`, `assistants/roles/rl_coach/TRAINING_ASSISTANT.md`
- **Example configs:**  
  `config/examples/native_runtime_factory/.../training_config_native.yaml`  
  `config/examples/node-red_runtime/.../training_config_node_red.yaml`  
  `config/examples/pyflow_runtime/.../training_config_pyflow.yaml`
