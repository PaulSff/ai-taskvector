"""
Graph executor: topological execution with input resolution (ComfyUI-style).

Type-agnostic: runs whatever graph and units are provided. Excludes RLAgent (and
other policy node types) from execution; units wired as action targets receive
injected action; units wired as observation sources feed the observation vector.
"""
from __future__ import annotations

from typing import Any

from schemas.agent_node import RL_AGENT_NODE_TYPES, get_agent_action_output_ids, get_agent_observation_input_ids
from schemas.process_graph import Connection, ProcessGraph, Unit

from units.registry import get_unit_spec


def _resolve_port(
    conn: Connection,
    from_spec: Any,
    to_spec: Any,
) -> tuple[str, str]:
    """Resolve from_port/to_port to port names. Connection stores indices ('0','1') or names; map to spec when available."""
    fp = conn.from_port or "0"
    tp = conn.to_port or "0"
    if from_spec and from_spec.output_ports:
        try:
            idx = int(fp)
            if 0 <= idx < len(from_spec.output_ports):
                fp = from_spec.output_ports[idx][0]
        except (ValueError, TypeError):
            if fp in [p[0] for p in from_spec.output_ports]:
                pass
            else:
                fp = from_spec.output_ports[0][0]
    if to_spec and to_spec.input_ports:
        try:
            idx = int(tp)
            if 0 <= idx < len(to_spec.input_ports):
                tp = to_spec.input_ports[idx][0]
        except (ValueError, TypeError):
            if tp in [p[0] for p in to_spec.input_ports]:
                pass
            else:
                tp = to_spec.input_ports[0][0]
    return (fp, tp)


def _topological_order(graph: ProcessGraph, process_unit_ids: set[str]) -> list[str]:
    """Return unit ids in execution order (dependencies first)."""
    preds: dict[str, list[str]] = {uid: [] for uid in process_unit_ids}
    for c in graph.connections:
        if c.from_id in process_unit_ids and c.to_id in process_unit_ids and c.from_id != c.to_id:
            if c.to_id not in preds:
                preds[c.to_id] = []
            preds[c.to_id].append(c.from_id)

    order: list[str] = []
    remaining = set(process_unit_ids)
    while remaining:
        ready = [u for u in remaining if all(p in order for p in preds[u])]
        if not ready:
            break
        order.extend(sorted(ready))
        remaining -= set(ready)
    return order


class GraphExecutor:
    """
    Executes a process graph in topological order. Type-agnostic.

    - Process units: all except RLAgent (and other policy node types).
    - Action targets: units wired from agent receive action at first input port.
    - Observation: first output port of units wired into agent, in sorted order.
    - info["outputs"]: all unit outputs {unit_id: {port: value}}.
    """

    def __init__(self, graph: ProcessGraph) -> None:
        self.graph = graph
        self._unit_ids = {u.id: u for u in graph.units}
        self._process_ids = {
            u.id for u in graph.units
            if u.type not in RL_AGENT_NODE_TYPES and get_unit_spec(u.type) is not None
        }
        self._order = _topological_order(graph, self._process_ids)
        self._obs_ids = get_agent_observation_input_ids(graph)
        self._action_ids = get_agent_action_output_ids(graph)
        self._state: dict[str, dict[str, Any]] = {}
        self._outputs: dict[str, dict[str, Any]] = {}

    def _build_inputs(self, unit_id: str, action: list[float] | None) -> dict[str, Any]:
        """Resolve inputs from connections and injected action."""
        unit = self._unit_ids.get(unit_id)
        if not unit:
            return {}

        spec = get_unit_spec(unit.type)
        if not spec:
            return {}

        inputs: dict[str, Any] = {}

        for c in self.graph.connections:
            if c.to_id != unit_id:
                continue
            if c.from_id not in self._outputs:
                continue
            from_spec = get_unit_spec(self._unit_ids[c.from_id].type) if c.from_id in self._unit_ids else None
            to_spec = spec
            fp, tp = _resolve_port(c, from_spec, to_spec)
            out = self._outputs[c.from_id]
            if fp in out:
                inputs[tp] = out[fp]

        # Action injection last (takes precedence): units in action_ids get action at first input port
        if unit_id in self._action_ids and action is not None and spec.input_ports:
            idx = self._action_ids.index(unit_id)
            if idx < len(action):
                port_name = spec.input_ports[0][0]
                inputs[port_name] = float(action[idx])

        return inputs

    def step(self, dt: float, action: list[float] | None = None) -> tuple[list[float], dict[str, Any]]:
        """
        Execute one step. Returns (observation, info).

        action: normalized [-1,1] or [0,1] depending on spec; mapped to valve setpoints.
        """
        for uid in self._order:
            unit = self._unit_ids.get(uid)
            if not unit:
                continue
            spec = get_unit_spec(unit.type)
            if not spec or not spec.step_fn:
                continue

            inputs = self._build_inputs(uid, action)
            state = self._state.get(uid, {})
            params = dict(unit.params or {})
            outputs, new_state = spec.step_fn(params, inputs, state, dt)
            self._outputs[uid] = outputs
            self._state[uid] = new_state

        obs = []
        for sid in self._obs_ids:
            unit = self._unit_ids.get(sid)
            spec = get_unit_spec(unit.type) if unit else None
            out = self._outputs.get(sid, {})
            if spec and spec.output_ports:
                port = spec.output_ports[0][0]
                val = out.get(port, 0.0)
            else:
                val = 0.0
            obs.append(float(val))
        if not obs:
            obs = [0.0]

        info: dict[str, Any] = {"outputs": dict(self._outputs)}
        return obs, info

    def reset(
        self,
        initial_state: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:
        """Reset all unit states and run one step with valves closed.
        initial_state: optional {unit_id: {"volume": ..., "temp": ...}} for Tank etc.
        """
        self._state = dict(initial_state or {})
        self._outputs = {}
        return self.step(0.1, action=[0.0] * max(len(self._action_ids), 1))
