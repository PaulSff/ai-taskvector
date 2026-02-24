# Temperature control agent: current workflow

This doc walks through how the **temperature control agent** is trained and run, and how the **two paths** (config-driven custom vs external) fit together.

---

## Two paths at a glance

| Path | When used | Env comes from | Config entry |
|------|-----------|----------------|--------------|
| **Config-driven (custom)** | Default when no `environment` block or `source: custom` | Process graph + goal → **env_factory** → `GraphEnv` | `environment.source: custom` (default), `process_graph_path`, training config goal/rewards |
| **External** | When you train against Node-RED, PyFlow, ComfyUI, etc. | Adapter (e.g. **pyflow_adapter**, **comfyui_adapter**) wraps the external runtime as `gym.Env` | `environment.source: external`, `adapter`, `adapter_config` |

There is no separate “fully custom” path that bypasses config: **custom** is the config-driven path that builds the env from the process graph. **env_factory** connects the process graph (config) to **GraphEnv**.

---

## RLAgent node: required and wired before training

For **both** the custom and external paths, the process graph must include an **RLAgent** node, and it must be **wired before training begins**. The agent is not added only at deployment time.

- **Required**: The graph must contain exactly one unit of type `RLAgent` (e.g. `id: ai_tank_operator` or `rl_agent`).
- **Inputs (observations)**: Connections **into** the RLAgent node define its observations (e.g. sensors → RLAgent: thermometer, water_level, etc.).
- **Outputs (actions)**: Connections **from** the RLAgent node define its actions (e.g. RLAgent → hot_valve, cold_valve, dump_valve).

So at config/design time you define *which* signals the agent observes and *which* actuators it controls. Training and deployment then use this same wiring. Example: `config/examples/ai_water_tank_operator_workflow_wired.json` shows a fully wired graph including the RLAgent; `config/examples/temperature_process.yaml` must also include the RLAgent unit and its connections (see below).

---

## Path 1: Config-driven (custom thermodynamic)

This is the default path for the temperature control agent.

### 1. Config files

- **Process graph** (what to control):  
  `config/examples/temperature_process.yaml` (or the copy under **config/examples/custom_runtime_factory/custom_AI_temperature-control-agent/temperature_process.yaml**).  
  - Canonical YAML: `environment_type: thermodynamic`, `units` (Source, Valve, Tank, Sensor, **RLAgent**), `connections`.  
  - Defines hot/cold sources, valves, mixer tank, sensors, and the **RLAgent** node with its **inputs** (e.g. thermometer, water_level → agent) and **outputs** (agent → valves) wired; no code.

- **Training config**:  
  `config/examples/training_config.yaml` (generic), or **config/examples/custom_runtime_factory/custom_AI_temperature-control-agent/training_config_custom.yaml** (custom env with process_graph_path set).  
  - **goal**: e.g. `target_temp: 37.0`, `target_volume_ratio: [0.80, 0.85]`.  
  - **rewards**: preset, weights, rules.  
  - **algorithm**, **hyperparameters**, **callbacks** (e.g. `model_dir: models/temperature-control-agent`).  
  - **environment** is optional; if omitted, defaults to `source: custom` (see `schemas/training_config.py`).

### 2. Training

```bash
python train.py --config config/examples/training_config.yaml [--process-config config/examples/temperature_process.yaml]
```

  **By runtime:** Examples are grouped under `config/examples/` by runtime: **custom_runtime_factory/** (env_factory), **node-red_runtime/** (Node-RED), **pyflow_runtime/** (PyFlow). Each agent folder contains its process/flow and training_config; use that config path for training.

- **train.py** loads:
  - `training_config` via normalizer (goal, rewards, algorithm, **environment**).
  - For `environment.source == "custom"`: resolves **process graph** from `--process-config`, or `environment.process_graph_path`, or default `config/examples/temperature_process.yaml`.
- **train.py** builds the env with:
  - **Custom path**: `build_env(process_graph, goal, rewards=..., randomize_params=...)` from **env_factory** (no `get_env` for this branch; it uses `build_env` directly).
- **env_factory.build_env** (`env_factory/factory.py`):
  - Asserts `environment_type == thermodynamic`.
  - Validates graph (e.g. ≥2 sources, ≥1 tank, 3 controllable valves, **RLAgent present and wired**).
  - Extracts params from graph + goal (temps, flows, target_temp, etc.).
  - Passes **process_graph** into **GraphEnv** so observation/action spaces and step logic follow the agent wiring.
- **GraphEnv** (`environments/graph_env.py`):
  - If **process_graph** is provided: **observation_space** size = number of connections into the RLAgent (sensors → agent); **action_space** size = number of connections from the RLAgent (agent → valves). Observation vector is built from sensor ids (e.g. thermometer_hot, thermometer_cold, thermometer_tank, water_level → normalized temps and volume ratio). Actions are applied to valves in the order defined by the graph (sorted by target valve id).
  - So the **same** process graph drives **structure**, **agent I/O**, **physics/reward**, and **training/deployment** end to end.

### 3. Custom env stack (this path)

- **environments/custom/thermodynamics/**  
  - `load_thermodynamic_env(config)`: builds env from **config** (process_graph_path, goal, rewards).  
  - Used by **environments.get_env(EnvSource.CUSTOM, config)** when you go through the registry (e.g. test_model.py).  
  - For **train.py** custom path we don’t call this; we call **env_factory.build_env** with the already-loaded process_graph and goal.

- **env_factory/factory.py**  
  - **build_env(process_graph, goal, rewards=..., **kwargs)** → **GraphEnv**.  
  - Single place that maps canonical process graph + goal → concrete env instance.

- **environments/graph_env.py**  
  - **GraphEnv**: gym.Env backed by GraphExecutor (hot/cold/dump valves, tank, temperature, volume, rewards).  
  - Observation/action spaces, `reset`, `step`, reward logic (including **rewards_config** and rule-engine rules).  
  - Reads unit registry and process graph; no monolithic physics in the env class.

So for the default temperature agent:

**config (process + training) → train.py → env_factory.build_env(process_graph, goal, rewards) → GraphEnv**.

### 4. Visualization (same env, different script)

- **environments/custom/water_tank_simulator.py**  
  - Standalone script: loads env from **config** (training config + optional process config), optionally loads a trained model, runs episodes.  
  - Uses **environments.get_env(EnvSource.CUSTOM, ...)** so it gets the same **GraphEnv** (via thermodynamic loader → env_factory) as training when using the same configs.  
  - Draws the tank, valves, temperature, volume; supports manual sliders or AI policy.  
  - So: **same config path** (process + training YAML) → same env type; **water_tank_simulator** is just a visual/test front-end for that env.

### 5. Models

- Trained artifacts go under **models/temperature-control-agent/** (from `callbacks.model_dir`).  
- **training_config_used.yaml** and **process_config_used.yaml** are saved there so you know exactly which config and graph were used for that run.

---

## Path 2: External (e.g. PyFlow)

Used when the “environment” is an external runtime (Node-RED, PyFlow, etc.), not our **GraphEnv**.

### 1. Config

- The **external** graph (e.g. PyFlow/Node-RED flow JSON) must include the **RLAgent** node with **inputs and outputs wired** before training (same requirement as the custom path).
- In **training_config.yaml** you set something like:
  - `environment.source: external`
  - `environment.adapter: pyflow`
  - `environment.adapter_config`: e.g. `flow_path`, `observation_sources`, `action_targets`, (optional) `goal`, `reward_node`.

### 2. Training

- **train.py** sees `env_cfg.source == "external"` and calls:
  - `get_env(EnvSource.EXTERNAL, { "adapter": "pyflow", "config": adapter_config, ... })`.
- **environments/__init__.py** → **load_external_env** → **environments/external/pyflow_adapter.load_pyflow_env(config)**.
- **pyflow_adapter**: loads the PyFlow graph JSON, runs it **in-process** (no separate PyFlow app), exposes observation/action/reward as a gym.Env. So the “physics” are defined by the PyFlow graph and its nodes, not by **GraphEnv**.

### 3. Relation to “custom”

- **PyFlow adapter** does not use **GraphEnv** or **env_factory**.  
- It’s a different env implementation that still obeys the same training script and config layout: **config** chooses **source** (custom vs external); **custom** → process graph + env_factory → GraphEnv; **external** → adapter (e.g. PyFlow) → its own gym.Env.

So we have **two implementations** of “temperature control–style” envs:

1. **Config + process graph → env_factory → GraphEnv** (custom).  
2. **Config + adapter_config → pyflow_adapter → PyFlowEnvWrapper** (external).

---

## Summary diagram

```
config/examples/
  temperature_process.yaml     →  process graph (units, connections)
  training_config.yaml         →  goal, rewards, algorithm, environment (source, type, paths, adapter...)

train.py
  → load training_config + (if custom) process_graph
  → if source == custom:  build_env(process_graph, goal, rewards)  → env_factory → GraphEnv
  → if source == external: get_env(EXTERNAL, adapter_config)      → e.g. pyflow_adapter → PyFlowEnvWrapper

env_factory/factory.py
  → build_env(process_graph, goal, rewards)  → validates graph  → GraphEnv(process_graph, goal, ...)

environments/custom/
  graph_env.py                 →  GraphEnv (generic)
  custom/thermodynamics/       →  ThermodynamicEnvSpec, load_thermodynamic_env  → build_env(...)  [used by get_env(CUSTOM)]
  water_tank_simulator.py      →  get_env(CUSTOM, config) + optional SB3 model; matplotlib UI

environments/external/
  pyflow_adapter.py            →  load_pyflow_env(config)  → PyFlowEnvWrapper (in-process PyFlow graph as gym.Env)

models/temperature-control-agent/
  → checkpoints, best model, training_config_used.yaml, process_config_used.yaml
```

---

## Quick reference

- **One agent (temperature), two ways to get an env**  
  - **Custom**: process graph YAML + training config → **env_factory** → **GraphEnv**.  
  - **External**: training config with `source: external` + adapter config → **adapter** (e.g. **pyflow_adapter**) → adapter’s gym.Env.

- **GraphEnv** is only used on the **custom** path; it is not used by PyFlow or other external adapters.

- **Process graph** is used only for the **custom** path (and for the GUI/Workflow Designer); external adapters use their own graph format (e.g. PyFlow JSON).

- **water_tank_simulator** is a visual/test runner for the **custom** thermodynamic env (same env as in training when using the same configs).
