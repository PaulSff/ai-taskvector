"""
Graph executor: run process graphs in topological order (plain execution).

Load a workflow JSON/YAML, run the graph once; each unit executes in dependency order.
Canonical topology (StepDriver, Join, Switch) is optional — used for RL training;
without it, the graph runs as a plain dataflow (no action/observation).
"""
from __future__ import annotations

import subprocess
from typing import Any, Callable

from core.schemas.agent_node import (
    EXECUTOR_EXCLUDED_TYPES,
    get_join,
    get_step_driver,
    get_step_rewards,
    get_switch,
    get_switch_action_target_ids,
    has_canonical_topology,
)
from core.schemas.process_graph import Connection, ProcessGraph, Unit

from units.registry import get_unit_spec


def _run_shell_block(source: str, timeout: float = 30.0) -> Any:
    """Run a unit's code_block as a bash script; return stdout as result."""
    try:
        out = subprocess.run(
            ["bash", "-c", source],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (out.stdout or "").strip() or (out.stderr or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return ""


def _run_code_block(
    source: str,
    node_id: str,
    state: dict[str, Any],
    inputs: dict[str, Any],
    params: dict[str, Any],
) -> Any:
    """Run a unit's code_block with state/inputs/params; return single value (PyFlow-adapter contract)."""
    for k in inputs:
        v = inputs.get(k)
        if v is None:
            inputs = {**inputs, k: 0.0}
    scope: dict[str, Any] = {"state": state, "inputs": inputs, "node_id": node_id, "params": params or {}}
    indented = "\n  ".join(source.strip().splitlines())
    wrapped = f"def _fn(state, inputs):\n  {indented}\n_result = _fn(state, inputs)"
    exec(wrapped, scope)
    return scope.get("_result", 0.0)


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
    """Raise ValueError if the graph is invalid for execution (invalid connections or ports)."""
    unit_ids = {u.id: u for u in graph.units}
    process_ids = {
        u.id for u in graph.units
        if u.type not in EXECUTOR_EXCLUDED_TYPES and get_unit_spec(u.type) is not None
    }
    # Connections are optional: single-unit workflows (e.g. rag_update) have no connections.
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
            fp_raw = c.from_port or "0"
            try:
                fp = int(fp_raw)
            except (ValueError, TypeError):
                names = [p.name for p in from_unit.output_ports]
                if fp_raw in names:
                    fp = names.index(fp_raw)
                else:
                    raise ValueError(
                        f"Connection from_port must be a valid index or port name for unit '{c.from_id}', got '{c.from_port}'."
                    ) from None
            if fp < 0 or fp >= len(from_unit.output_ports):
                raise ValueError(
                    f"Connection from_port '{c.from_port}' out of range for unit '{c.from_id}' "
                    f"(has {len(from_unit.output_ports)} output_ports)."
                )
        if c.to_id in process_ids and to_unit.input_ports:
            tp_raw = c.to_port or "0"
            try:
                tp = int(tp_raw)
            except (ValueError, TypeError):
                names = [p.name for p in to_unit.input_ports]
                if tp_raw in names:
                    tp = names.index(tp_raw)
                else:
                    raise ValueError(
                        f"Connection to_port must be a valid index or port name for unit '{c.to_id}', got '{c.to_port}'."
                    ) from None
            if tp < 0 or tp >= len(to_unit.input_ports):
                raise ValueError(
                    f"Connection to_port '{c.to_port}' out of range for unit '{c.to_id}' "
                    f"(has {len(to_unit.input_ports)} input_ports)."
                )
    # Canonical topology (StepDriver, Join, Switch) is optional; plain graphs run without action/observation.


class GraphExecutor:
    """
    Executes a process graph in topological order (one forward pass).
    Use execute() for plain execution; step()/reset() for RL-style control (optional Join/Switch/StepDriver).
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
        sd = get_step_driver(graph)
        j = get_join(graph)
        sw = get_switch(graph)
        sr = get_step_rewards(graph)
        self._step_driver_id = sd.id if sd else None
        self._join_id = j.id if j else None
        self._switch_id = sw.id if sw else None
        self._step_rewards_id = sr.id if sr else None
        self._action_ids = get_switch_action_target_ids(graph)
        self._n_act = max(len(self._action_ids), 1)
        self._n_obs = max(
            sum(1 for c in graph.connections if c.to_id == self._join_id),
            1,
        )
        self._injected_trigger: str = "step"
        self._injected_action: list[float] = [0.0] * self._n_act
        self._state: dict[str, dict[str, Any]] = {}
        self._outputs: dict[str, dict[str, Any]] = {}
        self._initial_inputs: dict[str, dict[str, Any]] = {}

    def execute(
        self,
        initial_inputs: dict[str, dict[str, Any]] | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Run the graph once (one forward pass in topological order).
        Returns outputs: { unit_id: { port_name: value, ... }, ... }.
        initial_inputs: optional { unit_id: { port_name: value } } for units with no upstream (e.g. Inject).
        stream_callback: optional; when an LLMAgent unit runs, each streamed token chunk is passed here.
        """
        self._state = {}
        self._outputs = {}
        self._injected_trigger = "step"
        self._injected_action = [0.0] * self._n_act
        _, info = self.step(
            0.0,
            action=[0.0] * self._n_act,
            initial_inputs=initial_inputs,
            stream_callback=stream_callback,
        )
        return info.get("outputs", {})

    def _build_inputs(
        self,
        unit_id: str,
        action: list[float] | None,
        initial_inputs: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Resolve inputs from connections, injected action, and optional initial_inputs (e.g. for edit flows)."""
        unit = self._unit_ids.get(unit_id)
        if not unit:
            return {}

        spec = get_unit_spec(unit.type)
        if not spec:
            return {}

        inputs: dict[str, Any] = {}
        # Merge initial_inputs for this unit (e.g. Inject gets graph from backend)
        init = (initial_inputs or self._initial_inputs or {}).get(unit_id)
        if init:
            inputs.update(init)
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

        # Inject trigger into StepDriver and StepRewards, action vector into Switch
        if unit_id == self._step_driver_id and unit.input_ports:
            inputs[unit.input_ports[0].name] = self._injected_trigger
        if unit_id == self._step_rewards_id and unit.input_ports:
            for p in unit.input_ports:
                if p.name == "trigger":
                    inputs[p.name] = self._injected_trigger
                    break
                if p.name == "outputs":
                    # Full graph outputs so rewards DSL (formula/rules) can use get(outputs, 'unit.port')
                    inputs[p.name] = dict(self._outputs)
                    break
        if unit_id == self._switch_id and unit.input_ports:
            inputs[unit.input_ports[0].name] = self._injected_action

        return inputs

    def step(
        self,
        dt: float,
        action: list[float] | None = None,
        initial_inputs: dict[str, dict[str, Any]] | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:
        """
        Execute one step. Returns (observation, info).

        action: normalized [-1,1] or [0,1] depending on spec; mapped to valve setpoints.
        initial_inputs: optional { unit_id: { port_name: value } } for edit flows (e.g. Inject).
        stream_callback: optional; passed to LLMAgent units so they can stream tokens.
        Canonical: action injected into Switch input; observation from Join output.
        """
        self._initial_inputs = initial_inputs or {}
        self._injected_trigger = "step"
        self._injected_action = list(action) if action is not None else [0.0] * self._n_act

        # Build state view for code_block units: node_id -> single value (from outputs)
        def _graph_state() -> dict[str, Any]:
            out: dict[str, Any] = {}
            for nid in self._unit_ids:
                o = self._outputs.get(nid) or {}
                out[nid] = o.get("out", o.get("value", next(iter(o.values()), 0.0) if o else 0.0))
            return out

        code_by_id: dict[str, str] = {}
        lang_by_id: dict[str, str] = {}
        if self.graph.code_blocks:
            for b in self.graph.code_blocks:
                bid = b.id if hasattr(b, "id") else (b.get("id") if isinstance(b, dict) else None)
                if bid:
                    code_by_id[bid] = b.source if hasattr(b, "source") else (b.get("source") if isinstance(b, dict) else "")
                    lang_by_id[bid] = (b.language if hasattr(b, "language") else (b.get("language") or "python") if isinstance(b, dict) else "python")

        for idx, uid in enumerate(self._order):
            unit = self._unit_ids.get(uid)
            if not unit:
                continue
            spec = get_unit_spec(unit.type)
            if not spec:
                continue

            # code_block_driven: run graph code_block (Python in-process or shell via subprocess)
            if getattr(spec, "code_block_driven", False):
                source = code_by_id.get(uid)
                if source:
                    lang = (lang_by_id.get(uid) or "python").lower()
                    if unit.type == "exec" or lang in ("shell", "bash"):
                        result = _run_shell_block(source)
                    else:
                        cb_state = _graph_state()
                        inputs = self._build_inputs(uid, action)
                        params = dict(unit.params or {})
                        result = _run_code_block(source, uid, cb_state, inputs, params)
                    out_port = (spec.output_ports[0][0]) if spec.output_ports else "out"
                    self._outputs[uid] = {out_port: result}
                    continue

            if not spec.step_fn:
                continue

            inputs = self._build_inputs(uid, action)
            state = self._state.get(uid, {})
            params = dict(unit.params or {})
            if stream_callback is not None and unit.type in ("LLMAgent", "RunWorkflow"):
                params["_stream_callback"] = stream_callback
            outputs, new_state = spec.step_fn(params, inputs, state, dt)
            self._outputs[uid] = outputs
            self._state[uid] = new_state

        # Observation from Join (or from StepRewards when present, same vector)
        raw = self._outputs.get(self._join_id, {}).get("observation", [])
        obs = [float(x) for x in raw] if isinstance(raw, (list, tuple)) else [float(raw)]
        if not obs and self._step_rewards_id:
            raw = self._outputs.get(self._step_rewards_id, {}).get("observation", [])
            obs = [float(x) for x in raw] if isinstance(raw, (list, tuple)) else [float(raw)]

        info: dict[str, Any] = {"outputs": dict(self._outputs)}
        if self._step_rewards_id:
            out = self._outputs.get(self._step_rewards_id, {})
            if "reward" in out:
                info["reward"] = float(out["reward"])
            if "done" in out:
                info["done"] = bool(out["done"])
        return obs, info

    def reset(
        self,
        initial_state: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:
        """Reset all unit states and run one step with valves closed (idle).
        initial_state: optional {unit_id: {"volume": ..., "temp": ...}} for Tank etc.
        Canonical: inject trigger=reset and action=idle; StepDriver emits start to simulators, one step runs, obs from Join.
        """
        self._state = dict(initial_state or {})
        self._outputs = {}
        self._injected_trigger = "reset"
        self._injected_action = [0.0] * self._n_act
        return self.step(0.1, action=self._injected_action)
