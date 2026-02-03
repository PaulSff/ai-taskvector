"""
IDAES simulator adapter.

Wraps an IDAES flowsheet (Pyomo model) as a Gymnasium env for the roundtrip:
(1) import flowsheet topology (template-like JSON or introspect from model),
(2) train via this adapter (step = set action vars, solve, read obs, reward),
(3) use trained model in control/optimization. See docs/WORKFLOW_EDITORS_AND_CODE.md.

IDAES is optional: pip install idaes-pse (and a solver, e.g. ipopt). If not installed,
loading this adapter raises ImportError with install instructions.
"""
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from environments.external.base import BaseExternalWrapper

# Optional: IDAES and Pyomo (heavy deps)
try:
    from pyomo.environ import SolverFactory, value
    from pyomo.core.base import Block
except ImportError as e:
    SolverFactory = None  # type: ignore[misc, assignment]
    value = None  # type: ignore[assignment]
    Block = None  # type: ignore[misc, assignment]
    _pyomo_import_error = e

try:
    from idaes.core.util.model_serializer import to_json as idaes_to_json, from_json as idaes_from_json
except ImportError:
    idaes_to_json = None  # type: ignore[misc, assignment]
    idaes_from_json = None  # type: ignore[misc, assignment]


def _check_idaes() -> None:
    if SolverFactory is None:
        raise ImportError(
            "IDAES adapter requires Pyomo: pip install pyomo"
        ) from getattr(
            __import__("sys").modules[__name__], "_pyomo_import_error", None
        )


def _load_model_from_config(config: dict[str, Any]) -> Any:
    """Build or load IDAES/Pyomo model from config. Returns the model (ConcreteModel)."""
    import importlib.util

    model_path = config.get("model_path")
    model_module = config.get("model_module")
    model_attr = config.get("model_attr", "model")

    if model_path:
        path = Path(model_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise FileNotFoundError(f"IDAES model_path not found: {path}")
        spec = importlib.util.spec_from_file_location("idaes_flowsheet_module", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load module from model_path: {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Prefer callable that returns model (e.g. create_flowsheet), then attribute
        if callable(getattr(mod, "create_flowsheet", None)):
            return getattr(mod, "create_flowsheet")()
        if callable(getattr(mod, "get_model", None)):
            return getattr(mod, "get_model")()
        if hasattr(mod, model_attr):
            return getattr(mod, model_attr)
        if hasattr(mod, "model"):
            return getattr(mod, "model")
        if hasattr(mod, "m"):
            return getattr(mod, "m")
        raise ValueError(
            f"model_path module must expose 'model', 'm', or create_flowsheet()/get_model(); got {dir(mod)}"
        )

    if model_module:
        mod_name, _, attr = model_module.partition(":")
        attr = attr or model_attr
        mod = __import__(mod_name, fromlist=[attr])
        obj = getattr(mod, attr)
        return obj() if callable(obj) else obj

    raise ValueError("IDAES config must include 'model_path' or 'model_module'")


def _resolve_component(model: Any, path: str) -> Any:
    """Resolve a path like 'fs.mixer.outlet.temperature[0]' on the Pyomo model."""
    return model.find_component(path)


def _get_var_value(component: Any) -> float:
    """Get scalar or first index value from a Pyomo Var/Param."""
    if component is None:
        return 0.0
    try:
        v = value(component)
        return float(v) if v is not None else 0.0
    except TypeError:
        # Indexed: take first index
        for idx in component:
            return float(value(component[idx]))
    return 0.0


def _set_var_value(component: Any, val: float) -> None:
    """Set value (and fix) on a Pyomo Var."""
    if component is None:
        return
    try:
        component.set_value(val)
        component.fix()
    except (AttributeError, TypeError):
        for idx in component:
            component[idx].set_value(val)
            component[idx].fix()
            break


def flowsheet_to_canonical_dict(model: Any, flowsheet_name: str = "fs") -> dict[str, Any]:
    """
    Introspect an IDAES/Pyomo flowsheet and return a canonical process-graph dict (units, connections).

    Use this to export a live model to our ProcessGraph format (e.g. for GUI or normalizer).
    Requires the model to have a FlowsheetBlock (e.g. model.fs) with unit blocks and Arcs.

    Args:
        model: Pyomo ConcreteModel with a flowsheet block (e.g. model.fs).
        flowsheet_name: Name of the flowsheet block (default "fs").

    Returns:
        Dict with environment_type, units, connections for ProcessGraph.
    """
    _check_idaes()
    fs = getattr(model, flowsheet_name, None)
    if fs is None:
        raise ValueError(f"Model has no block '{flowsheet_name}'")
    units: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    for block in fs.component_objects(Block, active=True):
        name = block.getname(fully_qualified=False)
        if name.startswith("_"):
            continue
        try:
            # Skip Arcs and other non-unit blocks if identifiable
            if "arc" in name.lower() or "port" in name.lower():
                continue
        except Exception:
            pass
        bid = str(name)
        unit_ids.add(bid)
        units.append({
            "id": bid,
            "type": type(block).__name__,
            "controllable": False,
            "params": {},
        })
    connections: list[dict[str, str]] = []
    try:
        from pyomo.network import Arc
        for arc in fs.component_objects(Arc, active=True):
            for idx in arc:
                a = arc[idx]
                src_port = getattr(a, "source", None)
                dst_port = getattr(a, "destination", getattr(a, "dest", None))
                src = getattr(src_port, "parent_block", None) if src_port is not None else None
                dst = getattr(dst_port, "parent_block", None) if dst_port is not None else None
                if src is not None and dst is not None:
                    sname = src.getname(fully_qualified=False) if hasattr(src, "getname") else str(id(src))
                    dname = dst.getname(fully_qualified=False) if hasattr(dst, "getname") else str(id(dst))
                    if sname in unit_ids and dname in unit_ids and sname != dname:
                        connections.append({"from": sname, "to": dname})
    except ImportError:
        pass
    return {
        "environment_type": "chemical",
        "units": units,
        "connections": connections,
    }


def load_idaes_env(config: dict[str, Any]) -> gym.Env:
    """
    Load an IDAES flowsheet as a Gymnasium env.

    Config:
      model_path: Path to Python file that builds the model (must expose model, m, or create_flowsheet()).
      model_module: Alternative: dotted module path (e.g. "my_package.flowsheet:get_model").
      model_attr: Attribute or callable name (default "model").
      state_path: Optional path to JSON from idaes.core.util.model_serializer.to_json; load state after build.
      observation_vars: List of var paths (e.g. ["fs.mixer.outlet.temperature[0]"]) for observation vector.
      action_vars: List of var paths to set each step (control inputs).
      obs_shape: Optional (n,) or int; inferred from observation_vars length if omitted.
      action_shape: Optional (n,) or int; inferred from action_vars length if omitted.
      reward_config: Optional dict, e.g. {"type": "setpoint", "target_temp": 100} or {"observation_index": 0, "target": 100}.
      solver: Solver name (default "ipopt").
      solver_options: Optional dict of solver options.
    """
    _check_idaes()
    return IDAESEnvWrapper(config)


class IDAESEnvWrapper(BaseExternalWrapper):
    """
    Wrap an IDAES flowsheet (Pyomo model) as gym.Env.

    Each step: set action_vars from action vector, solve model, read observation_vars, compute reward.
    Reset: optionally reload state from state_path or re-run model builder (re-init).
    """

    def __init__(self, config: dict[str, Any], render_mode: str | None = None):
        super().__init__(config, render_mode)
        self._model: Any = None
        self._observation_vars = list(config.get("observation_vars") or [])
        self._action_vars = list(config.get("action_vars") or [])
        if not self._observation_vars or not self._action_vars:
            raise ValueError(
                "IDAES adapter requires config['observation_vars'] and config['action_vars'] "
                "(list of model var paths, e.g. ['fs.unit1.outlet.temperature[0]'])"
            )
        self._state_path = config.get("state_path")
        self._reward_config = dict(config.get("reward_config") or {})
        self._solver_name = str(config.get("solver", "ipopt"))
        self._solver_options = dict(config.get("solver_options") or {})
        self._obs_shape = config.get("obs_shape")
        self._action_shape = config.get("action_shape")
        self._last_reward = 0.0

    def _connect(self) -> None:
        self._model = _load_model_from_config(self.config)
        if self._state_path and idaes_from_json is not None:
            idaes_from_json(self._model, fname=str(self._state_path))
        # Infer spaces from first observation
        obs = self._get_obs()
        act_dim = len(self._action_vars)
        obs_dim = obs.size
        if self._obs_shape is not None:
            obs_dim = (
                self._obs_shape
                if isinstance(self._obs_shape, int)
                else int(np.prod(self._obs_shape))
            )
        if self._action_shape is not None:
            act_dim = (
                self._action_shape
                if isinstance(self._action_shape, int)
                else int(np.prod(self._action_shape))
            )
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(act_dim,), dtype=np.float32
        )

    def _get_obs(self) -> np.ndarray:
        parts: list[float] = []
        for path in self._observation_vars:
            comp = _resolve_component(self._model, path)
            parts.append(_get_var_value(comp))
        return np.array(parts, dtype=np.float32)

    def _send_action(self, action: np.ndarray) -> None:
        action = np.asarray(action, dtype=np.float32).flatten()
        for i, path in enumerate(self._action_vars):
            if i >= action.size:
                break
            comp = _resolve_component(self._model, path)
            _set_var_value(comp, float(action[i]))
        solver = SolverFactory(self._solver_name)
        if self._solver_options:
            for k, v in self._solver_options.items():
                solver.options[k] = v
        solver.solve(self._model)
        # Reward from config
        obs = self._get_obs()
        rtype = self._reward_config.get("type", "setpoint")
        if rtype == "setpoint":
            idx = int(self._reward_config.get("observation_index", 0))
            target = float(self._reward_config.get("target", self._reward_config.get("target_temp", 0.0)))
            self._last_reward = -float(np.abs(obs[idx] - target))
        else:
            self._last_reward = 0.0

    def _reward(self) -> float:
        return self._last_reward

    def _done(self) -> tuple[bool, bool]:
        return False, False

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if not self._connected:
            self._connect()
            self._connected = True
            return self._get_obs(), {}
        # Re-load state for fresh episode (if state_path given); else keep current model
        if self._state_path and idaes_from_json is not None:
            idaes_from_json(self._model, fname=str(self._state_path))
        self._last_reward = 0.0
        return self._get_obs(), {}
