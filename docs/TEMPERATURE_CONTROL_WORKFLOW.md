# Temperature control agent: current workflow

This doc walks through how the **temperature control agent** is trained and run, and how the **two paths** (config-driven custom vs external) fit together.

---

## Two paths at a glance

| Path | When used | Env comes from | Config entry |
|------|-----------|----------------|--------------|
| **Config-driven (custom)** | Default when no `environment` block or `source: custom` | Process graph + goal → **env_factory** → `TemperatureControlEnv` | `environment.source: custom` (default), `process_graph_path`, training config goal/rewards |
| **External** | When you train against Node-RED, PyFlow, etc. | Adapter (e.g. **pyflow_adapter**) wraps the external runtime as `gym.Env` | `environment.source: external`, `adapter`, `adapter_config` |

There is no separate “fully custom” path that bypasses config: **custom** is the config-driven path that builds the env from the process graph. The “fully custom” idea is that **TemperatureControlEnv** is a hand-written gym.Env, and **env_factory** is what connects the generic process graph (config) to that concrete class.

---

## Path 1: Config-driven (custom thermodynamic)

This is the default path for the temperature control agent.

### 1. Config files

- **Process graph** (what to control):  
  `config/examples/temperature_process.yaml`  
  - Canonical YAML: `environment_type: thermodynamic`, `units` (Source, Valve, Tank, Sensor), `connections`.  
  - Defines hot/cold sources, valves, mixer tank, thermometer; no code.

- **Training config**:  
  `config/examples/training_config.yaml`  
  - **goal**: e.g. `target_temp: 37.0`, `target_volume_ratio: [0.80, 0.85]`.  
  - **rewards**: preset, weights, rules.  
  - **algorithm**, **hyperparameters**, **callbacks** (e.g. `model_dir: models/temperature-control-agent`).  
  - **environment** is optional; if omitted, defaults to `source: custom` (see `schemas/training_config.py`).

### 2. Training

```bash
python train.py --config config/examples/training_config.yaml [--process-config config/examples/temperature_process.yaml]
```

- **train.py** loads:
  - `training_config` via normalizer (goal, rewards, algorithm, **environment**).
  - For `environment.source == "custom"`: resolves **process graph** from `--process-config`, or `environment.process_graph_path`, or default `config/examples/temperature_process.yaml`.
- **train.py** builds the env with:
  - **Custom path**: `build_env(process_graph, goal, rewards=..., randomize_params=...)` from **env_factory** (no `get_env` for this branch; it uses `build_env` directly).
- **env_factory.build_env** (`env_factory/factory.py`):
  - Asserts `environment_type == thermodynamic`.
  - Validates graph (e.g. ≥2 sources, ≥1 tank, 3 controllable valves).
  - Extracts params from graph + goal (temps, flows, target_temp, etc.).
  - Instantiates **TemperatureControlEnv** with those params and `rewards_config`.
- So the **same** process graph YAML and training config drive both the **structure** (sources, valves, tank) and the **physics/reward** (via **TemperatureControlEnv**).

### 3. Custom env stack (this path)

- **environments/custom/thermodynamic.py**  
  - `load_thermodynamic_env(config)`: builds env from **config** (process_graph_path, goal, rewards).  
  - Used by **environments.get_env(EnvSource.CUSTOM, config)** when you go through the registry (e.g. test_model.py).  
  - For **train.py** custom path we don’t call this; we call **env_factory.build_env** with the already-loaded process_graph and goal.

- **env_factory/factory.py**  
  - **build_env(process_graph, goal, rewards=..., **kwargs)** → **TemperatureControlEnv**.  
  - Single place that maps canonical process graph + goal → concrete env instance.

- **environments/custom/temperature_env.py**  
  - **TemperatureControlEnv**: the actual gym.Env (hot/cold/dump valves, tank, temperature, volume, rewards).  
  - Observation/action spaces, `reset`, `step`, reward logic (including **rewards_config** and rule-engine rules).  
  - No process graph parsing inside; it only receives constructor kwargs from **env_factory**.

So for the default temperature agent:

**config (process + training) → train.py → env_factory.build_env(process_graph, goal, rewards) → TemperatureControlEnv**.

### 4. Visualization (same env, different script)

- **environments/custom/water_tank_simulator.py**  
  - Standalone script: loads env from **config** (training config + optional process config), optionally loads a trained model, runs episodes.  
  - Uses **environments.get_env(EnvSource.CUSTOM, ...)** so it gets the same **TemperatureControlEnv** (via thermodynamic loader → env_factory) as training when using the same configs.  
  - Draws the tank, valves, temperature, volume; supports manual sliders or AI policy.  
  - So: **same config path** (process + training YAML) → same env type; **water_tank_simulator** is just a visual/test front-end for that env.

### 5. Models

- Trained artifacts go under **models/temperature-control-agent/** (from `callbacks.model_dir`).  
- **training_config_used.yaml** and **process_config_used.yaml** are saved there so you know exactly which config and graph were used for that run.

---

## Path 2: External (e.g. PyFlow)

Used when the “environment” is an external runtime (Node-RED, PyFlow, etc.), not our **TemperatureControlEnv**.

### 1. Config

- In **training_config.yaml** you set something like:
  - `environment.source: external`
  - `environment.adapter: pyflow`
  - `environment.adapter_config`: e.g. `flow_path`, `observation_sources`, `action_targets`, (optional) `goal`, `reward_node`.

### 2. Training

- **train.py** sees `env_cfg.source == "external"` and calls:
  - `get_env(EnvSource.EXTERNAL, { "adapter": "pyflow", "config": adapter_config, ... })`.
- **environments/__init__.py** → **load_external_env** → **environments/external/pyflow_adapter.load_pyflow_env(config)**.
- **pyflow_adapter**: loads the PyFlow graph JSON, runs it **in-process** (no separate PyFlow app), exposes observation/action/reward as a gym.Env. So the “physics” are defined by the PyFlow graph and its nodes, not by **TemperatureControlEnv**.

### 3. Relation to “custom”

- **PyFlow adapter** does not use **TemperatureControlEnv** or **env_factory**.  
- It’s a different env implementation that still obeys the same training script and config layout: **config** chooses **source** (custom vs external); **custom** → process graph + env_factory → TemperatureControlEnv; **external** → adapter (e.g. PyFlow) → its own gym.Env.

So we have **two implementations** of “temperature control–style” envs:

1. **Config + process graph → env_factory → TemperatureControlEnv** (custom).  
2. **Config + adapter_config → pyflow_adapter → PyFlowEnvWrapper** (external).

---

## Summary diagram

```
config/examples/
  temperature_process.yaml     →  process graph (units, connections)
  training_config.yaml         →  goal, rewards, algorithm, environment (source, type, paths, adapter...)

train.py
  → load training_config + (if custom) process_graph
  → if source == custom:  build_env(process_graph, goal, rewards)  → env_factory → TemperatureControlEnv
  → if source == external: get_env(EXTERNAL, adapter_config)      → e.g. pyflow_adapter → PyFlowEnvWrapper

env_factory/factory.py
  → build_env(process_graph, goal, rewards)  → validates graph, extracts params  → TemperatureControlEnv(**params)

environments/custom/
  temperature_env.py           →  TemperatureControlEnv (gym.Env)
  thermodynamic.py             →  load_thermodynamic_env(config)  → build_env(...)  [used by get_env(CUSTOM) and water_tank_simulator]
  water_tank_simulator.py      →  get_env(CUSTOM, config) + optional SB3 model; matplotlib UI

environments/external/
  pyflow_adapter.py            →  load_pyflow_env(config)  → PyFlowEnvWrapper (in-process PyFlow graph as gym.Env)

models/temperature-control-agent/
  → checkpoints, best model, training_config_used.yaml, process_config_used.yaml
```

---

## Quick reference

- **One agent (temperature), two ways to get an env**  
  - **Custom**: process graph YAML + training config → **env_factory** → **TemperatureControlEnv**.  
  - **External**: training config with `source: external` + adapter config → **adapter** (e.g. **pyflow_adapter**) → adapter’s gym.Env.

- **TemperatureControlEnv** is only used on the **custom** path; it is not used by PyFlow or other external adapters.

- **Process graph** is used only for the **custom** path (and for the GUI/Workflow Designer); external adapters use their own graph format (e.g. PyFlow JSON).

- **water_tank_simulator** is a visual/test runner for the **custom** thermodynamic env (same env as in training when using the same configs).
