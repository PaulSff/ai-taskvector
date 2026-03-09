"""
PyFlow adapter (in-process, our own executor).

PyFlow is a Python-native node editor (https://github.com/pedroCabrera/PyFlow).
We support the roundtrip: (1) import workflow from PyFlow JSON, (2) train via
this adapter as gym.Env, (3) deploy trained model as an RLAgent node in the flow.

**Node execution does NOT use the PyFlow runtime.** We load the graph JSON,
normalize it to our ProcessGraph (format="pyflow"), then run our own executor:
topological order, code_blocks via exec(), Source from params, pass-through
for other nodes. RLAgent nodes run via their code_block (template-based HTTP
client to inference service). No dependency on the PyFlow library or editor;
no separate process. See docs/WORKFLOW_EDITORS_AND_CODE.md.
"""
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from environments.external.base import BaseExternalWrapper


_ORACLE_ACTION_KEY = "__rl_oracle_action__"
_STEP_COUNT_KEY = "step_count"


def load_pyflow_env(config: dict[str, Any]) -> gym.Env:
    """
    Load PyFlow graph as a Gymnasium env (in-process execution).

    Config:
      flow_path: Path to PyFlow JSON file (required).
      observation_sources: List of node ids whose outputs form the observation vector (required if no Oracle).
      action_targets: List of node ids that receive the action (required if no Oracle; one node = full action vector).
      obs_shape: (n,) or int; optional, inferred if omitted.
      action_shape: (n,) or int; optional, inferred if omitted.
      goal: Optional dict with target_temp (float) for reward = -|obs - target_temp| (ignored if Oracle present).
      reward_node: Optional node id whose output is the reward (ignored if Oracle present).
      done_node: Optional node id whose output is the episode done flag (ignored if Oracle present).

    If the graph has canonical topology (step_driver + step_rewards by role), Oracle mode is used:
    step_driver forwards action from state, step_rewards aggregates obs and computes reward/done. Same
    semantics as Node-RED/n8n export; in-process (no HTTP).
    """
    return PyFlowEnvWrapper(config)


def _connection_from_to(c: Any) -> tuple[Any, Any]:
    """Get (from_id, to_id) from a Connection (Pydantic) or dict."""
    if hasattr(c, "from_id") and hasattr(c, "to_id"):
        return getattr(c, "from_id"), getattr(c, "to_id")
    if isinstance(c, dict):
        return c.get("from") or c.get("from_id"), c.get("to") or c.get("to_id")
    return None, None


def _topological_order(unit_ids: set[str], connections: list[Any]) -> list[str]:
    """Return node ids in topological order (upstream first). Uses Kahn's algorithm."""
    from collections import deque

    # connections have from_id, to_id (or from, to in raw dict)
    in_degree = {n: 0 for n in unit_ids}
    out_edges: dict[str, list[str]] = {n: [] for n in unit_ids}
    for c in connections:
        from_id, to_id = _connection_from_to(c)
        if from_id is None or to_id is None:
            continue
        from_id, to_id = str(from_id), str(to_id)
        if from_id in unit_ids and to_id in unit_ids and from_id != to_id:
            out_edges[from_id].append(to_id)
            in_degree[to_id] = in_degree.get(to_id, 0) + 1
    q = deque(n for n in unit_ids if in_degree[n] == 0)
    order: list[str] = []
    while q:
        n = q.popleft()
        order.append(n)
        for m in out_edges[n]:
            in_degree[m] -= 1
            if in_degree[m] == 0:
                q.append(m)
    # Any remaining nodes (cycles) append at end
    for n in unit_ids:
        if n not in order:
            order.append(n)
    return order


def _inputs_for_node(node_id: str, connections: list[Any], unit_ids: set[str]) -> dict[str, Any]:
    """Return dict of upstream node_id -> value for nodes that feed into node_id."""
    inputs: dict[str, Any] = {}
    for c in connections:
        from_id, to_id = _connection_from_to(c)
        if to_id != node_id or from_id not in unit_ids:
            continue
        inputs[str(from_id)] = None  # caller fills state
    return inputs


def _run_code_block(
    source: str,
    node_id: str,
    state: dict[str, Any],
    inputs: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> Any:
    """Execute code block with state, inputs, params; return result. Safe subset: only state/inputs/params exposed."""
    # Fill inputs from state; coerce None to 0.0 so code never sees None for numeric inputs
    for k in inputs:
        v = state.get(k, 0.0)
        inputs[k] = v if v is not None else 0.0
    scope: dict[str, Any] = {"state": state, "inputs": inputs, "node_id": node_id, "params": params or {}}
    # Wrap as function body and capture return value
    indented = "\n  ".join(source.strip().splitlines())
    wrapped = f"def _fn(state, inputs):\n  {indented}\n_result = _fn(state, inputs)"
    exec(wrapped, scope)
    return scope.get("_result", 0.0)


def _to_float_vec(x: Any) -> np.ndarray:
    """Convert scalar or list to 1d float32 array."""
    if isinstance(x, np.ndarray):
        return np.asarray(x, dtype=np.float32).flatten()
    if isinstance(x, (list, tuple)):
        return np.array([float(v) for v in x], dtype=np.float32)
    return np.array([float(x)], dtype=np.float32)


class PyFlowEnvWrapper(BaseExternalWrapper):
    """
    Wrap PyFlow graph (in-process execution) as gym.Env.

    Loads graph from flow_path, builds topological order, evaluates nodes each step.
    Observation = concatenated outputs of observation_sources; action injected into action_targets.
    """

    def __init__(self, config: dict[str, Any], render_mode: str | None = None):
        super().__init__(config, render_mode)
        self._config = dict(config)
        flow_path = config.get("flow_path")
        if not flow_path:
            raise ValueError("PyFlow adapter requires config['flow_path'] (path to PyFlow JSON)")
        self._flow_path = Path(flow_path)
        self._observation_sources = list(config.get("observation_sources") or [])
        self._action_targets = list(config.get("action_targets") or [])
        self._goal = config.get("goal") or {}
        self._reward_node = config.get("reward_node")
        self._done_node = config.get("done_node")
        self._obs_shape = config.get("obs_shape")
        self._action_shape = config.get("action_shape")

        self._graph = None
        self._order: list[str] = []
        self._code_by_id: dict[str, str] = {}
        self._state: dict[str, Any] = {}
        self._last_reward = 0.0
        self._last_done = False
        self._oracle_mode = False
        self._oracle_step_driver: str | None = None
        self._oracle_collector: str | None = None
        # Set observation/action space before VecEnv wraps this env (it reads spaces at wrap time)
        self._connect()
        self._connected = True

    def _load_graph(self) -> None:
        import json

        from normalizer.normalizer import to_process_graph

        try:
            from units.register_env_agnostic import register_env_agnostic_units
            register_env_agnostic_units()
        except Exception:
            pass
        raw: dict[str, Any]
        with open(self._flow_path, encoding="utf-8") as f:
            text = f.read()
        raw = json.loads(text)
        # Accept canonical format (units, connections) or PyFlow format
        fmt = "dict" if isinstance(raw, dict) and "units" in raw and "connections" in raw else "pyflow"
        self._graph = to_process_graph(raw, format=fmt)
        unit_ids = {u.id for u in self._graph.units}
        self._order = _topological_order(unit_ids, self._graph.connections)
        self._code_by_id = {b.id: b.source for b in self._graph.code_blocks}
        # Default state from params (e.g. Source temp)
        for u in self._graph.units:
            if u.id in self._state:
                continue
            if u.type == "Source" and "temp" in u.params:
                self._state[u.id] = float(u.params["temp"])
            else:
                self._state[u.id] = 0.0
        self._detect_oracle()

    def _detect_oracle(self) -> None:
        """Detect canonical step_driver and step_rewards; enable Oracle mode if both present."""
        from schemas.agent_node import get_step_driver, get_step_rewards

        sd = get_step_driver(self._graph)
        sr = get_step_rewards(self._graph)
        if sd and sr:
            self._oracle_mode = True
            self._oracle_step_driver = sd.id
            self._oracle_collector = sr.id  # observation/reward/done from step_rewards

    def _connect(self) -> None:
        self._load_graph()
        if not self._oracle_mode and (not self._observation_sources or not self._action_targets):
            raise ValueError(
                "PyFlow adapter requires config['observation_sources'] and config['action_targets'] "
                "(or canonical topology with step_driver + step_rewards in the flow)"
            )
        # Infer obs/action dim from first run
        self._state = {u.id: 0.0 for u in self._graph.units}
        for u in self._graph.units:
            if u.type == "Source" and getattr(u, "params", None) and "temp" in u.params:
                self._state[u.id] = float(u.params["temp"])
        if not self._oracle_mode:
            for aid in self._action_targets:
                if aid in self._state:
                    self._state[aid] = 0.0
        self._eval_graph()
        obs = self._observe()
        if self._oracle_mode:
            adapter_cfg = self._config.get("adapter_config") or self._config
            act_spec = adapter_cfg.get("action_spec") or []
            act_dim = len(act_spec) if act_spec else (self._action_shape if isinstance(self._action_shape, int) else 3)
        else:
            act_dim = len(self._action_targets)  # single node = 1-dim action by default
            if isinstance(self._state.get(self._action_targets[0]), (list, np.ndarray)):
                act_dim = np.asarray(self._state[self._action_targets[0]]).size
        obs_dim = obs.size
        if self._obs_shape is not None:
            obs_dim = self._obs_shape if isinstance(self._obs_shape, int) else int(np.prod(self._obs_shape))
        if self._action_shape is not None:
            act_dim = self._action_shape if isinstance(self._action_shape, int) else int(np.prod(self._action_shape))
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(act_dim,), dtype=np.float32
        )

    def _eval_graph(self) -> None:
        """Run one pass: set state for each node in topological order.
        In Oracle mode: action injected via __rl_oracle_action__; step_driver reads it.
        Otherwise: action_targets skipped (already set by _send_action).
        RLAgent nodes are executed inline: load model from params['model_path'], predict(obs), no WS/HTTP.
        """
        unit_ids = {u.id for u in self._graph.units}
        skip_action_targets = self._action_targets if not self._oracle_mode else ()
        for node_id in self._order:
            if node_id in skip_action_targets:
                continue  # already set by _send_action
            unit = self._graph.get_unit(node_id)
            inputs = _inputs_for_node(node_id, self._graph.connections, unit_ids)
            if node_id in self._code_by_id:
                params = dict(unit.params) if unit and unit.params else {}
                result = _run_code_block(
                    self._code_by_id[node_id], node_id, self._state, inputs, params
                )
                # Keep dict/list results (e.g. mixer_tank); coerce None to 0.0 for scalars
                self._state[node_id] = result if result is not None else 0.0
            elif unit and unit.type == "Source":
                self._state[node_id] = float(unit.params.get("temp", 0.0))
            elif inputs:
                # Pass-through: use first input value
                first_id = next(iter(inputs))
                self._state[node_id] = self._state.get(first_id, 0.0)
            else:
                self._state[node_id] = 0.0

    def _observe(self) -> np.ndarray:
        if self._oracle_mode and self._oracle_collector:
            out = self._state.get(self._oracle_collector)
            if isinstance(out, dict) and "observation" in out:
                return _to_float_vec(out["observation"])
        parts = []
        for nid in self._observation_sources:
            v = self._state.get(nid, 0.0)
            parts.append(_to_float_vec(v))
        if not parts:
            return np.zeros(1, dtype=np.float32)
        return np.concatenate(parts).astype(np.float32)

    def _get_obs(self) -> np.ndarray:
        return self._observe()

    def _send_action(self, action: np.ndarray) -> None:
        action = np.asarray(action, dtype=np.float32).flatten()
        if self._oracle_mode:
            self._state[_ORACLE_ACTION_KEY] = action.tolist()
            self._eval_graph()
            out = self._state.get(self._oracle_collector)
            if isinstance(out, dict):
                self._last_reward = float(out.get("reward", 0.0))
                self._last_done = bool(out.get("done", False))
            else:
                self._last_reward = 0.0
                self._last_done = False
            return
        # Inject action into action target(s)
        if len(self._action_targets) == 1:
            self._state[self._action_targets[0]] = action if action.size != 1 else float(action[0])
        else:
            n = len(self._action_targets)
            chunk = max(1, action.size // n)
            for i, aid in enumerate(self._action_targets):
                start = i * chunk
                end = start + chunk if i < n - 1 else action.size
                seg = action[start:end]
                self._state[aid] = float(seg[0]) if seg.size == 1 else seg
        self._eval_graph()
        # Reward from goal or reward node
        obs = self._observe()
        if self._reward_node is not None and self._reward_node in self._state:
            r = self._state[self._reward_node]
            self._last_reward = float(r) if np.isscalar(r) else float(np.asarray(r).flat[0])
        elif self._goal.get("target_temp") is not None:
            target = float(self._goal["target_temp"])
            err = np.abs(obs - target).max() if obs.size else 0.0
            self._last_reward = -float(err)
        else:
            self._last_reward = 0.0
        if self._done_node is not None and self._done_node in self._state:
            d = self._state[self._done_node]
            self._last_done = bool(d) if np.isscalar(d) else bool(np.asarray(d).flat[0])
        else:
            self._last_done = False

    def _reward(self) -> float:
        return self._last_reward

    def _done(self) -> tuple[bool, bool]:
        return self._last_done, False

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if not self._connected:
            self._connect()
            self._connected = True
            return self._get_obs(), {}
        # Re-initialize state and run one eval
        self._state = {u.id: 0.0 for u in self._graph.units}
        for u in self._graph.units:
            if u.type == "Source" and "temp" in u.params:
                self._state[u.id] = float(u.params["temp"])
        if self._oracle_mode:
            self._state.pop(_ORACLE_ACTION_KEY, None)
            self._state.pop(_STEP_COUNT_KEY, None)
        self._eval_graph()
        self._last_reward = 0.0
        self._last_done = False
        return self._get_obs(), {}
