# Environments: Managing Multiple Dynamics Within the Constructor

All **dynamics** (simulators) are external from our system: we send actions and receive feedback. They can come from three sources:

| Source | Description | Example |
|--------|-------------|--------|
| **Gymnasium** | Envs from the Gymnasium API (e.g. `gym.make("CartPole-v1")`). | CartPole, Ant, Atari, third-party registered envs. |
| **External** | Simulators outside our repo, wrapped as a Gymnasium env (wrapper/connector). | IDAES, PC-Gym, SMPL, proprietary simulators. |
| **Custom** | Envs we ship (e.g. `TemperatureControlEnv`) built from our process graph + goal. | Thermodynamic temperature mixing (current). |

The constructor needs a **single entry point** to get a `gym.Env` regardless of source: **environments/**.

---

## 1. Folder structure

```
environments/
  __init__.py              # get_env(source, config) -> gym.Env, EnvSource
  registry.py              # EnvSource enum, config types (optional)
  gymnasium_loader.py      # Load from gym.make(env_id, **kwargs)
  external/
    __init__.py
    base.py                # BaseExternalWrapper(gym.Env) for any external sim
    idaes_adapter.py       # IDAES flowsheet -> gym.Env (stub until needed)
  custom/
    __init__.py
    thermodynamic.py       # build from process_graph + goal (delegate to env_factory)
```

- **Gymnasium:** Use `gymnasium.make(env_id, **kwargs)`. No wrapper needed; config = `env_id` + optional `kwargs` (render_mode, etc.).
- **External:** Each adapter implements a thin **wrapper** that talks to the external simulator (e.g. IDAES API) and exposes `reset()`, `step(action)`, `observation_space`, `action_space`. Config = adapter key + adapter-specific options (paths, params).
- **Custom:** Reuse current **env_factory**: process_graph + goal → `build_env()` → `TemperatureControlEnv`. Config = process_graph (or path) + goal.

---

## 2. How to set up an environment from Gymnasium

**Config (example):**

```yaml
environment:
  source: gymnasium
  env_id: "CartPole-v1"
  kwargs:
    render_mode: null  # or "human" for visualization
```

**Usage:**

```python
from environments import get_env, EnvSource

config = {"source": "gymnasium", "env_id": "CartPole-v1", "kwargs": {}}
env = get_env(EnvSource.GYMNASIUM, config)
obs, info = env.reset()
```

**Implementation:** `environments/gymnasium_loader.py` loads with `gym.make(config["env_id"], **config.get("kwargs", {}))`. No process graph; the constructor may still store which “logical” env (e.g. CartPole) is selected for training, but dynamics come entirely from Gymnasium.

---

## 3. External simulators: wrapper / connector

External simulators (IDAES, PC-Gym, SMPL, etc.) do not implement the Gymnasium API by default. We need an **adapter** that:

1. Takes adapter-specific config (e.g. IDAES flowsheet path, solver options).
2. Instantiates or connects to the external simulator.
3. Implements `gym.Env`: `reset()` → obs, info; `step(action)` → obs, reward, terminated, truncated, info; `observation_space`, `action_space`; optional `render()`.

**Base class:** `environments/external/base.py` can define a `BaseExternalWrapper(gym.Env)` that subclasses `gym.Env` and leaves `_connect()`, `_obs_from_sim()`, `_send_action()` to subclasses (or a single adapter class per external sim).

**Example (IDAES):** `environments/external/idaes_adapter.py` (stub) would:

- Accept config: `flowsheet_path` or in-memory model, `control_inputs` (which variables are actions), `observations` (which variables are obs).
- Build or load the IDAES model, run simulation steps.
- Map action vector → IDAES inputs; read state → observation; compute or define reward (e.g. from goal in config).

**Config (example):**

```yaml
environment:
  source: external
  adapter: idaes
  config:
    flowsheet_path: "path/to/flowsheet.json"
    control_inputs: ["valve_1", "valve_2"]
    observation_vars: ["T_tank", "flow_out"]
```

**Usage:**

```python
env = get_env(EnvSource.EXTERNAL, {"adapter": "idaes", "config": {...}})
```

Multiple externals: register adapters by name (`idaes`, `pcgym`, etc.); `get_env(EXTERNAL, config)` dispatches on `config["adapter"]`. See `environments/__init__.py` → `load_external_env()`.

---

## 4. Custom envs (our process-graph-driven envs)

Current **custom** env is thermodynamic: process_graph + goal → env_factory → `TemperatureControlEnv`. No change to env_factory; the **environments/** layer just delegates.

**Config (example):** Same as today: training config has `process_config` (path or inline) and `goal`; or a dedicated env block:

```yaml
environment:
  source: custom
  type: thermodynamic
  process_graph_path: "config/examples/temperature_process.yaml"
  goal:
    target_temp: 37.0
    target_volume_ratio: [0.80, 0.85]
```

**Usage:** `get_env(EnvSource.CUSTOM, config)` loads process graph (via normalizer), loads goal, calls `env_factory.build_env(process_graph, goal, **kwargs)`.

**Environment-specific visualization:** Visualization/simulation UIs belong to the env type. For the thermodynamic (water-tank) env, `environments/custom/water_tank_simulator.py` provides tank schematic, flow/temp display, and manual sliders. It uses config + `get_env(CUSTOM, ...)` to build the env. Universal testing (no viz) stays in `test_model.py` (config-driven, like `train.py`).

---

## 5. Unified entry point: get_env(source, config)

```python
def get_env(source: EnvSource, config: dict[str, Any], **kwargs: Any) -> gym.Env:
    if source == EnvSource.GYMNASIUM:
        return load_gymnasium_env(config)
    if source == EnvSource.EXTERNAL:
        return load_external_env(config)
    if source == EnvSource.CUSTOM:
        return load_custom_env(config, **kwargs)
    raise ValueError(f"Unknown source: {source}")
```

Training script (or constructor) can read `environment.source` and `environment.*` from the training config and call `get_env(...)` so that one config file drives which env is used (Gymnasium, external, or custom).

---

## 6. Summary

| Question | Answer |
|----------|--------|
| **1. How to set up an env from Gymnasium?** | Config: `source: gymnasium`, `env_id: "..."`, optional `kwargs`. Load with `gym.make(env_id, **kwargs)` in `environments/gymnasium_loader.py`. |
| **2. How to arrange externals (wrapper, connector)?** | Put adapters under `environments/external/`. Each adapter implements a wrapper that subclasses `gym.Env`, connects to the external sim, and maps action/obs/reward. Config: `source: external`, `adapter: idaes` (or key), `config: { ... }`. |
| **3. Custom envs?** | Keep using env_factory for process-graph-driven envs (thermodynamic). `environments/custom/` delegates to env_factory; config: `source: custom`, `type: thermodynamic`, process_graph + goal. |

All dynamics remain **external** to our system; **environments/** is the single place that decides which simulator to use and returns a `gym.Env` for training or the constructor.
