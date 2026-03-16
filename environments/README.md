# Environments

This package provides the environment layer for training and evaluation. Three sources are supported:

| Source | Description |
|--------|-------------|
| **Custom** | Process-graph-driven envs we implement (e.g. thermodynamic). Built via `GraphEnv` + `EnvSpec`. |
| **Gymnasium** | Standard gym envs via `gym.make()`. |
| **External** | Adapters to external runtimes (Node-RED, PyFlow, ComfyUI, IDAES, etc.). |

---

## Integrating Gymnasium Environments

Standard Gymnasium envs are flat (obs/action/reward) and don't use our process graph. You can either use them **raw** or **adapt** them to align with our architecture.

### Raw usage

For any Gymnasium env, load it directly:

```python
env = get_env(EnvSource.GYMNASIUM, {"env_id": "CartPole-v1"})
# or
from environments.gymnasium_loader import load_gymnasium_env
env = load_gymnasium_env({"env_id": "CartPole-v1", "kwargs": {}})
```

No process graph, no EnvSpec. The env works with `runtime/train.py` and `test_model.py` as-is, but it does not participate in graph-based tools (process designer, topology view, etc.).

### Adapted usage: mapping to our graph model

Many Gymnasium envs have structure that maps naturally to our unit model:

| Gym env concept | Our model |
|-----------------|-----------|
| Joints, actuators | Controllable units (valves, actuators) |
| Touch, pose, proprioception | Sensors |
| Physics / simulator | Process dynamics (analogous to Tank, Source) |
| Observation | Sensor outputs → RLAgent inputs |
| Action | RLAgent outputs → actuator commands |

Examples: robotic hand (Shadow Hand, Allegro), manipulation envs, locomotion. By adding a **thin adapter**, you:

1. Define a minimal process graph that describes the topology (sensors → RLAgent → actuators).
2. Wrap the Gym env in an adapter that:
   - Routes `reset` / `step` to the underlying env.
   - Maps env observation → graph sensor outputs.
   - Maps graph action outputs → env action.
3. Optionally use `GraphEnv` with a **pass-through spec** that delegates to the gym env instead of `GraphExecutor`.

**Integration options:**

- **Option A — Wrapper under Custom:** Create `environments/custom/gym_adapted/` with a loader that builds a synthetic process graph + wrapper. The wrapper implements `gym.Env`, forwards to the gym env, and exposes a graph-compatible interface for config/tooling.
- **Option B — Gymnasium adapter:** Add `environments/gymnasium_adapters/` with adapters per env (e.g. `shadow_hand_adapter.py`). Each adapter defines the graph mapping and wraps the gym env. Wire into `load_custom_env` with `type: "gym_adapted"` and `gym_env_id: "ShadowHand-v1"`.

The adapter does not run the graph via `GraphExecutor` (the gym env owns dynamics). It provides a **graph view** for our pipeline: config, rewards, topology visualization, and consistent training flow.

---

## Adding a New Custom Environment

To add a new custom environment (e.g. `chemical`, `generic_control`), you implement a tiny integration layer that plugs into the generic `GraphEnv`. The idea: **provide an `EnvSpec`** that tells `GraphEnv` how to build initial state, check done, extend info, and optionally expose compatibility attributes.

### 1. Create a folder under `custom/`

```
environments/custom/
  thermodynamics/     # Existing: temperature-mixing
    __init__.py
    spec.py
    loader.py
  your_env/           # New
    __init__.py
    spec.py
    loader.py
```

### 2. Implement an EnvSpec

Create `spec.py` with a class that implements the `EnvSpec` protocol (see `environments/spec.py`):

```python
# environments/custom/your_env/spec.py
from typing import Any
import numpy as np
from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig
# Import your unit registry, e.g. from units.your_units import register_your_units

# Canonical units (Join, Switch, StepDriver, Split, StepRewards, HttpIn, HttpResponse) and
# RLAgent, LLMAgent, RLOracle, RLGym are environment-agnostic: registered automatically
# in GraphEnv for all environments. Only register your domain-specific units here.


class YourEnvSpec:
    """EnvSpec for your process type."""

    def __init__(self, **kwargs: Any):
        self._kwargs = kwargs

    def register_units(self) -> None:
        """Register domain-specific unit types. Env-agnostic units are registered in GraphEnv."""
        # register_your_units()

    def build_initial_state(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        options: dict[str, Any] | None,
        randomize: bool,
        np_random: np.random.Generator,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Build unit_id -> state dict for executor.reset(initial_state=...).
        Keys are unit IDs; values are the internal state each unit expects.
        """
        initial_state = {}
        # e.g. for a tank: initial_state[tank_id] = {"volume": 0.5, "temp": 20.0}
        return initial_state

    def check_done(
        self,
        outputs: dict[str, Any],
        goal_override: dict[str, Any],
        step_count: int,
        max_steps: int,
        **kwargs: Any,
    ) -> tuple[bool, bool]:
        """
        Return (terminated, truncated).
        outputs: unit_id -> output dict from executor
        process_graph available via kwargs["process_graph"]
        """
        truncated = step_count >= max_steps
        terminated = False  # your success condition
        return terminated, truncated

    def extend_info(
        self,
        info: dict[str, Any],
        outputs: dict[str, Any],
        initial_state: dict[str, Any] | None,
        **kwargs: Any,
    ) -> None:
        """
        Add spec-specific keys to info (mutates info in place).
        e.g. info["temperature"] = ..., info["volume_ratio"] = ...
        """
        pass

    def get_goal_override(self, env: Any, **kwargs: Any) -> dict[str, Any]:
        """
        Return goal dict for evaluate_reward.
        e.g. {"target_temp": 37.0, "target_volume_ratio": [0.8, 0.85]}
        """
        return {}

    def get_compat_attr(self, env: Any, name: str) -> Any:
        """
        Return value for compatibility attrs (e.g. current_temp, hot_flow).
        Raise AttributeError for unknown names.
        """
        raise AttributeError(name)
```

**Optional methods:**

- `manual_step(env, hot_flow=..., cold_flow=..., ...)` — If present, `GraphEnv` exposes `env.manual_step()` (e.g. for `thermodynamics.water_tank_simulator`).
- `render(env)` — Called when `render_mode="human"`. Print or display state.

### 3. Create a loader

```python
# environments/custom/your_env/loader.py
from pathlib import Path
from typing import Any
import gymnasium as gym
from env_factory import build_env
from normalizer import load_process_graph_from_file
from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig, RewardsConfig


def load_your_env(
    config: dict[str, Any],
    *,
    process_graph: ProcessGraph | None = None,
    goal: GoalConfig | None = None,
    **kwargs: Any,
) -> gym.Env:
    """Build env from process graph + goal. Delegate to env_factory."""
    if process_graph is None:
        path = config.get("process_graph_path")
        if not path:
            raise ValueError("Config must include 'process_graph_path' or pass process_graph")
        process_graph = load_process_graph_from_file(Path(path))
    if goal is None:
        goal_raw = config.get("goal")
        if goal_raw is None:
            raise ValueError("Config must include 'goal' or pass goal")
        goal = GoalConfig.model_validate(goal_raw) if isinstance(goal_raw, dict) else goal_raw
    rewards = RewardsConfig.model_validate(config["rewards"]) if config.get("rewards") else None
    return build_env(process_graph, goal, rewards=rewards, **kwargs)
```

### 4. Add the environment type to the schema

In `schemas/process_graph.py`, add your type to `EnvironmentType`:

```python
class EnvironmentType(str, Enum):
    THERMODYNAMIC = "thermodynamic"
    CHEMICAL = "chemical"      # example
    GENERIC_CONTROL = "generic_control"
```

### 5. Wire into env_factory

In `env_factory/factory.py`:

1. Add a validator for your graph topology (e.g. `_validate_chemical_graph`).
2. Add a branch in `build_env()`:

```python
if process_graph.environment_type == EnvironmentType.CHEMICAL:
    _validate_chemical_graph(process_graph)
    from environments.graph_env import GraphEnv
    from environments.custom.your_env import YourEnvSpec
    spec = YourEnvSpec(**kwargs)
    return GraphEnv(process_graph, goal, spec, **kwargs)
```

### 6. Wire into load_custom_env

In `environments/__init__.py`, update `load_custom_env()`:

```python
def load_custom_env(config: dict[str, Any], **kwargs: Any) -> gym.Env:
    env_type = config.get("type", "thermodynamic")
    if env_type == "thermodynamic":
        return load_thermodynamic_env(config, **kwargs)
    if env_type == "chemical":
        from environments.custom.your_env import load_your_env
        return load_your_env(config, **kwargs)
    raise ValueError(f"Unknown custom env type: {env_type}")
```

### 7. Unit registry

Define your units in `units/` (e.g. `units/chemical/`) and register them in `spec.register_units()`. The process graph references unit types by name; the executor uses the registry to run each unit's `step_fn`. See `units/thermodynamic/` for the pattern.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  get_env(source, config)                                     │
│  - GYMNASIUM → gym.make()                                    │
│  - EXTERNAL  → adapters (Node-RED, PyFlow, etc.)             │
│  - CUSTOM    → load_custom_env() → load_*_env() → build_env  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  env_factory.build_env(process_graph, goal, rewards)         │
│  - Validates graph                                           │
│  - Instantiates EnvSpec for environment_type                 │
│  - Returns GraphEnv(process_graph, goal, spec, ...)          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  GraphEnv (environments/graph_env.py)                        │
│  - Generic orchestration                                     │
│  - GraphExecutor runs the process graph                      │
│  - Delegates to spec: reset, step, done, info, compat attrs  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  EnvSpec (environments/custom/<type>/spec.py)                │
│  - register_units()                                          │
│  - build_initial_state()                                     │
│  - check_done()                                              │
│  - extend_info()                                             │
│  - get_goal_override()                                       │
│  - get_compat_attr()                                         │
│  - optional: manual_step(), render()                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Reference Implementation

`environments/custom/thermodynamics/` is the reference: temperature-mixing process (hot/cold sources, tank, valves, sensors). Use it as a template when adding a new env type.
