"""
Graph executor: topological execution with input resolution (ComfyUI-style).

Excludes RLAgent from execution; valves receive setpoint from injected action,
sensors feed observation vector.
"""
from __future__ import annotations

from typing import Any

from schemas.agent_node import RL_AGENT_NODE_TYPES, get_agent_action_output_ids, get_agent_observation_input_ids
from schemas.process_graph import Connection, ProcessGraph, Unit

from units.registry import get_unit_spec


def _resolve_port(
    conn: Connection,
    from_unit: Unit,
    to_unit: Unit,
    from_port: str | None,
    to_port: str | None,
) -> tuple[str, str]:
    """Resolve from_port/to_port; use connection fields or heuristics."""
    fp = conn.from_port or from_port
    tp = conn.to_port or to_port

    fid = from_unit.id.lower()
    tid = to_unit.id.lower()

    # Valve -> Tank: infer to_port from valve id
    if to_unit.type == "Tank" and from_unit.type == "Valve":
        if not tp:
            if "hot" in fid:
                tp = "hot_flow"
            elif "cold" in fid:
                tp = "cold_flow"
            elif "dump" in fid:
                tp = "dump_flow"
        fp = fp or "flow"

    # Source -> Tank: infer to_port from source id
    if to_unit.type == "Tank" and from_unit.type == "Source":
        if not tp:
            if "hot" in fid:
                tp = "hot_temp"
            elif "cold" in fid:
                tp = "cold_temp"
        fp = fp or "temp"

    # Source -> Sensor: source outputs temp
    if to_unit.type == "Sensor" and from_unit.type == "Source":
        fp = fp or "temp"
        tp = tp or "value"

    # Tank -> Sensor: tank outputs temp or volume_ratio
    if to_unit.type == "Sensor" and from_unit.type == "Tank":
        measure = to_unit.params.get("measure", "temperature")
        if measure == "volume":
            fp = fp or "volume_ratio"
        else:
            fp = fp or "temp"
        tp = tp or "value"

    return (fp or "out", tp or "in")


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
    Executes a process graph in topological order.

    Process units: all except RLAgent (and other policy nodes).
    Valves receive setpoint from action vector (injected at step).
    Observation = sensor outputs (measurement) in observation_input_ids order.
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

        # Valves: setpoint from action
        if unit.type == "Valve" and unit_id in self._action_ids and action is not None:
            idx = self._action_ids.index(unit_id)
            if idx < len(action):
                inputs["setpoint"] = float(action[idx])

        for c in self.graph.connections:
            if c.to_id != unit_id:
                continue
            if c.from_id not in self._outputs:
                continue
            from_unit = self._unit_ids.get(c.from_id)
            to_unit = self._unit_ids.get(c.to_id)
            if not from_unit or not to_unit:
                continue
            fp, tp = _resolve_port(c, from_unit, to_unit, c.from_port, c.to_port)
            out = self._outputs[c.from_id]
            if fp in out:
                inputs[tp] = out[fp]

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
            out = self._outputs.get(sid, {})
            m = out.get("measurement", out.get("raw", 0.0))
            obs.append(float(m))
        if not obs:
            obs = [0.0]

        info: dict[str, Any] = {}
        tank_id = next((u.id for u in self.graph.units if u.type == "Tank"), None)
        if tank_id and tank_id in self._outputs:
            t = self._outputs[tank_id]
            info["temperature"] = t.get("temp", 0.0)
            info["volume"] = t.get("volume", 0.0)
            info["volume_ratio"] = t.get("volume_ratio", 0.0)
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
