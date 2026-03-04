"""
Graph executor: topological execution with input resolution (ComfyUI-style).

Type-agnostic: runs whatever graph and units are provided. Excludes RLAgent (and
other policy node types) from execution; units wired as action targets receive
injected action; units wired as observation sources feed the observation vector.
"""
from __future__ import annotations

from typing import Any

from schemas.agent_node import (
    EXECUTOR_EXCLUDED_TYPES,
    get_agent_action_output_ids,
    get_agent_observation_input_ids,
)
from schemas.process_graph import Connection, ProcessGraph, Unit

from units.registry import get_unit_spec


def _resolve_port(conn: Connection, from_unit: Unit, to_unit: Unit) -> tuple[str, str]:
    """Resolve from_port/to_port to port names using graph Unit ports (Registry → Graph → Executor)."""
    fp = conn.from_port or "0"
    tp = conn.to_port or "0"
    if from_unit.output_ports:
        try:
            idx = int(fp)
            if 0 <= idx < len(from_unit.output_ports):
                fp = from_unit.output_ports[idx].name
        except (ValueError, TypeError):
            if fp in [p.name for p in from_unit.output_ports]:
                pass
            else:
                fp = from_unit.output_ports[0].name
    if to_unit.input_ports:
        try:
            idx = int(tp)
            if 0 <= idx < len(to_unit.input_ports):
                tp = to_unit.input_ports[idx].name
        except (ValueError, TypeError):
            if tp in [p.name for p in to_unit.input_ports]:
                pass
            else:
                tp = to_unit.input_ports[0].name
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


def _validate_graph_for_execution(graph: ProcessGraph) -> None:
    """Raise ValueError if the graph is invalid for execution (missing connections or ports)."""
    unit_ids = {u.id: u for u in graph.units}
    process_ids = {
        u.id for u in graph.units
        if u.type not in EXECUTOR_EXCLUDED_TYPES and get_unit_spec(u.type) is not None
    }
    if process_ids and not graph.connections:
        raise ValueError(
            "Process graph has process units but no connections. Connections are mandatory for execution."
        )
    for c in graph.connections:
        if c.from_id not in unit_ids or c.to_id not in unit_ids:
            continue
        from_unit = unit_ids[c.from_id]
        to_unit = unit_ids[c.to_id]
        # Only process units (executed) must have ports; agent/oracle can have empty ports
        if c.from_id in process_ids and not from_unit.output_ports:
            raise ValueError(
                f"Connection from unit '{c.from_id}' has no output_ports; "
                "every process unit used as a connection source must have output_ports on the graph."
            )
        if c.to_id in process_ids and not to_unit.input_ports:
            raise ValueError(
                f"Connection to unit '{c.to_id}' has no input_ports; "
                "every process unit used as a connection target must have input_ports on the graph."
            )
        # Validate port indices for process units
        if c.from_id in process_ids and from_unit.output_ports:
            try:
                fp = int(c.from_port or "0")
            except (ValueError, TypeError):
                raise ValueError(
                    f"Connection from_port must be a valid index for unit '{c.from_id}', got '{c.from_port}'."
                ) from None
            if fp < 0 or fp >= len(from_unit.output_ports):
                raise ValueError(
                    f"Connection from_port '{c.from_port}' out of range for unit '{c.from_id}' "
                    f"(has {len(from_unit.output_ports)} output_ports)."
                )
        if c.to_id in process_ids and to_unit.input_ports:
            try:
                tp = int(c.to_port or "0")
            except (ValueError, TypeError):
                raise ValueError(
                    f"Connection to_port must be a valid index for unit '{c.to_id}', got '{c.to_port}'."
                ) from None
            if tp < 0 or tp >= len(to_unit.input_ports):
                raise ValueError(
                    f"Connection to_port '{c.to_port}' out of range for unit '{c.to_id}' "
                    f"(has {len(to_unit.input_ports)} input_ports)."
                )
    obs_ids = get_agent_observation_input_ids(graph)
    for sid in obs_ids:
        u = unit_ids.get(sid)
        if u and not u.output_ports:
            raise ValueError(
                f"Observation source unit '{sid}' has no output_ports; "
                "observation sources must have at least one output port on the graph."
            )
    action_ids = get_agent_action_output_ids(graph)
    for aid in action_ids:
        u = unit_ids.get(aid)
        if u and not u.input_ports:
            raise ValueError(
                f"Action target unit '{aid}' has no input_ports; "
                "action targets must have at least one input port on the graph."
            )


class GraphExecutor:
    """
    Executes a process graph in topological order. Type-agnostic.

    - Process units: all except RLAgent (and other policy node types).
    - Action targets: units wired from agent receive action at first input port.
    - Observation: first output port of units wired into agent, in sorted order.
    - info["outputs"]: all unit outputs {unit_id: {port: value}}.

    Raises ValueError in __init__ if the graph has no connections (when process units exist),
    or any connected unit or observation/action unit is missing required ports.
    """

    def __init__(self, graph: ProcessGraph) -> None:
        _validate_graph_for_execution(graph)
        self.graph = graph
        self._unit_ids = {u.id: u for u in graph.units}
        self._process_ids = {
            u.id for u in graph.units
            if u.type not in EXECUTOR_EXCLUDED_TYPES and get_unit_spec(u.type) is not None
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
            from_unit = self._unit_ids.get(c.from_id)
            if not from_unit:
                continue
            fp, tp = _resolve_port(c, from_unit, unit)
            out = self._outputs[c.from_id]
            if fp in out:
                inputs[tp] = out[fp]

        # Action injection: units in action_ids get action at first input port (from graph)
        if unit_id in self._action_ids and action is not None and unit.input_ports:
            idx = self._action_ids.index(unit_id)
            if idx < len(action):
                inputs[unit.input_ports[0].name] = float(action[idx])

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
            out = self._outputs.get(sid, {})
            if unit and unit.output_ports:
                port = unit.output_ports[0].name
                obs.append(float(out.get(port, 0.0)))

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
