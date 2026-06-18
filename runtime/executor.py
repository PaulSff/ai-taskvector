# Graph executor: run process graphs in topological order (plain execution).
#
# Load a workflow JSON/YAML, run the graph once; each unit executes in dependency order.
# Canonical topology (StepDriver, Join, Switch) is optional — used for RL training;
# without it, the graph runs as a plain dataflow (no action/observation).

from __future__ import annotations

import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Coroutine, cast

from core.schemas.agent_node import (
    EXECUTOR_EXCLUDED_TYPES,
    get_join,
    get_step_driver,
    get_step_rewards,
    get_switch,
    get_switch_action_target_ids,
)
from core.schemas.process_graph import ProcessGraph, Unit
from units.registry import get_unit_spec

from .graph_validator import _validate_graph_for_execution
from .resolve_ports import _resolve_port
from .run_code_block import _run_code_block_async
from .run_shell_block import _run_shell_block_async
from .shared_loop import (
    _ensure_shared_loop,
)
from .topological_order import _topological_order


class GraphExecutor:
    """
    Executes a process graph in topological order (one forward pass).
    Use execute() for plain execution; step()/reset() for RL-style control (optional Join/Switch/StepDriver).
    """

    graph: ProcessGraph

    def __init__(self, graph: ProcessGraph) -> None:
        from units.canonical.app_settings_param import resolve_process_graph_param_refs

        graph = cast(ProcessGraph, resolve_process_graph_param_refs(graph))
        _validate_graph_for_execution(graph)
        self.graph = graph
        self._unit_ids = {u.id: u for u in graph.units}
        self._process_ids = {
            u.id
            for u in graph.units
            if u.type not in EXECUTOR_EXCLUDED_TYPES
            and get_unit_spec(u.type) is not None
        }
        # _order is a topological ordering (list). We'll convert to levels for parallel execution.
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

        # Background asyncio loop and thread (shared across executors)
        self._loop = _ensure_shared_loop()
        self._loop_thread = None  # managed by module-level shared loop

        # Lock to protect outputs/state updates if unit code runs concurrently in threads.
        self._lock = threading.Lock()

        # Reused thread pool for sync step_fns and sync stream callbacks
        self._thread_pool = ThreadPoolExecutor(max_workers=8)

        # Precompute topological levels (list of lists). Each level can run in parallel.
        self._levels = self._compute_levels(self._order, self.graph.connections)

    def _compute_levels(self, order: list[str], connections) -> list[list[str]]:
        # Build dependency map: for each node, which nodes it depends on (incoming from process nodes only)
        deps: dict[str, set[str]] = {nid: set() for nid in order}
        proc_ids = self._process_ids
        for c in connections:
            if (
                c.to_id in deps
                and c.from_id in deps
                and c.from_id in proc_ids
                and c.to_id in proc_ids
            ):
                deps[c.to_id].add(c.from_id)
        # Kahn-like level construction respecting original order
        levels: list[list[str]] = []
        remaining = set(order)
        while remaining:
            ready = [n for n in order if n in remaining and not deps.get(n)]
            if not ready:
                # If cyclic or only excluded nodes remain, just place remaining as single level to avoid infinite loop.
                ready = [n for n in order if n in remaining]
            levels.append(ready)
            for n in ready:
                remaining.remove(n)
                # remove n as a dependency
                for k in deps:
                    if n in deps[k]:
                        deps[k].remove(n)
            # prune deps of removed nodes
            deps = {k: v for k, v in deps.items() if k in remaining}
        return levels

    def _run_coro(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Schedule coro on the background loop and wait for result (blocks)."""
        loop = self._loop
        if not loop or loop.is_closed():
            raise RuntimeError("Executor event loop not initialized or closed")
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return fut.result()
        except Exception as e:
            raise RuntimeError("Background loop error") from e

    def execute(
        self,
        initial_inputs: dict[str, dict[str, Any]] | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Run the graph once (one forward pass in topological order).
        Returns outputs: { unit_id: { port_name: value, ... }, ... }.
        initial_inputs: optional { unit_id: { port_name: value } } for units with no upstream (e.g. Inject).
        stream_callback: optional; passed to LLMAgent, RunWorkflow, and Chameleon; LLM token chunks use this channel.
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
        # Collect inputs from connections (protect reads with lock)
        with self._lock:
            for c in self.graph.connections:
                if c.to_id != unit_id:
                    continue
                if c.from_id not in self._outputs:
                    continue
                from_unit = self._unit_ids.get(c.from_id)
                if not from_unit:
                    continue
                fp, tp = _resolve_port(c, from_unit, unit)
                out = self._outputs.get(c.from_id, {})
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
                    inputs[p.name] = dict(self._outputs)
                    break
        if unit_id == self._switch_id and unit.input_ports:
            inputs[unit.input_ports[0].name] = self._injected_action

        return inputs

    async def _execute_unit_coro(
        self,
        unit: Unit,
        inputs: dict[str, Any],
        params: dict[str, Any],
        action: list[float] | None,
        state: dict[str, Any] | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Coroutine that executes a single unit, supporting:
        - code_block_driven units (shell or python) via async helpers
        - unit specs that implement execute_async
        - sync unit specs executed in a thread via thread pool
        Returns (outputs, new_state).
        """
        spec = get_unit_spec(unit.type)
        # Short-circuit if no spec or no step_fn/code_block_driven
        if not spec or (
            not getattr(spec, "step_fn", None)
            and not getattr(spec, "code_block_driven", False)
        ):
            return {}, {}

        # code_block_driven units handled here
        if getattr(spec, "code_block_driven", False):
            # locate code block source and language from graph (same logic used in step())
            source = None
            lang = "python"
            if self.graph.code_blocks:
                for b in self.graph.code_blocks:
                    if b.id == unit.id:
                        source = b.source
                        lang = (b.language or "python").lower()
                        break
            if source:
                if unit.type == "exec" or lang in ("shell", "bash"):
                    result = await _run_shell_block_async(source)
                else:
                    cb_state = self._graph_state_for_code_block()
                    result = await _run_code_block_async(
                        source, unit.id, cb_state, inputs, params
                    )
                out_port = (
                    (spec.output_ports[0][0])
                    if getattr(spec, "output_ports", None)
                    else "out"
                )
                return ({out_port: result}, {})

        # If spec provides an async execute (convention: execute_async or step_fn_async), prefer it.
        state = self._state.get(unit.id, {}) or {}
        try:
            if getattr(spec, "execute_async", None):
                exec_fn = getattr(spec, "execute_async", None)
                if exec_fn is not None:
                    res = await exec_fn(state, inputs, params)
                    if res is None:
                        return {}, {}
                    if isinstance(res, tuple) and len(res) == 2:
                        outputs, new_state = res
                        return (outputs or {}, new_state or {})
                    if isinstance(res, dict):
                        return (res, {})
                    out_port = (
                        spec.output_ports[0][0]
                        if getattr(spec, "output_ports", None)
                        else "out"
                    )
                    return ({out_port: res}, {})
            step_fn_async = getattr(spec, "step_fn_async", None)
            if step_fn_async is not None:
                try:
                    # primary signature with progress
                    res = await step_fn_async(params, inputs, state, 0.0)
                except TypeError:
                    # fallback: some implementations use (params, inputs, state)
                    res = await step_fn_async(params, inputs, state)
                if res is None:
                    return {}, {}

                if isinstance(res, tuple) and len(res) == 2:
                    outputs, new_state = res
                    return (outputs or {}, new_state or {})
                if isinstance(res, dict):
                    return (res, {})
                out_port = (
                    (spec.output_ports[0][0])
                    if getattr(spec, "output_ports", None)
                    else "out"
                )
                return ({out_port: res}, {})
        except Exception:
            # Let exceptions propagate to caller; could wrap/log here if desired.
            raise

        # Fallback: run existing sync step_fn in thread pool to avoid blocking loop
        sync_fn = getattr(spec, "step_fn", None)
        if sync_fn is None:
            return {}, {}

        def _sync_step():
            return sync_fn(params, inputs, state, 0.0)

        loop = self._loop
        if loop and not loop.is_closed():
            fut = loop.run_in_executor(self._thread_pool, _sync_step)
            outputs, new_state = await fut
        else:
            outputs, new_state = await asyncio.to_thread(_sync_step)

        return (outputs or {}, new_state or {})

    def _graph_state_for_code_block(self) -> dict[str, Any]:
        """Build a simple state mapping for code_block execution (same as prior _graph_state closure)."""
        out: dict[str, Any] = {}
        with self._lock:
            for nid in self._unit_ids:
                o = self._outputs.get(nid) or {}
                out[nid] = o.get(
                    "out", o.get("value", next(iter(o.values()), 0.0) if o else 0.0)
                )
        return out

    def _call_stream_callback(
        self, chunk: str, stream_callback: Callable[[str], None] | None
    ) -> None:
        """Call stream_callback which may be sync or async. Run it without blocking executor."""
        if not stream_callback:
            return

        try:
            if inspect.iscoroutinefunction(stream_callback):
                loop = self._loop
                if loop and not loop.is_closed():
                    try:
                        asyncio.run_coroutine_threadsafe(stream_callback(chunk), loop)
                    except Exception:
                        pass
                return
            # Sync callable: call directly — queue.put is thread-safe and non-blocking
            # (submitting to thread pool would introduce a race where the sentinel None
            # can arrive before pending chunk jobs complete).
            try:
                stream_callback(chunk)
            except Exception:
                pass
        except Exception:
            pass

    async def _run_level(
        self,
        level: list[str],
        action: list[float] | None,
        initial_inputs,
        stream_callback,
    ):
        """
        Execute all units in a single topological level in parallel.
        Each unit's inputs are built from current self._outputs (protected by lock).
        After a unit finishes, its outputs/state are written under self._lock.
        """
        tasks = []
        for uid in level:
            unit = self._unit_ids.get(uid)
            if not unit:
                continue
            spec = get_unit_spec(unit.type)
            if not spec:
                continue

            # code_block_driven units are handled inside _execute_unit_coro,
            # but for efficiency build inputs/params here.
            if getattr(spec, "code_block_driven", False):
                # We'll still call _execute_unit_coro which handles code blocks.
                pass

            # Skip nodes without executable behavior
            if (
                not getattr(spec, "step_fn", None)
                and not getattr(spec, "step_fn_async", None)
                and not getattr(spec, "execute_async", None)
                and not getattr(spec, "code_block_driven", False)
            ):
                continue

            # Build per-unit inputs/params/state snapshot before scheduling to reduce lock hold time
            inputs = self._build_inputs(uid, action, initial_inputs)
            state = self._state.get(uid, {}) or {}
            params = dict((self._unit_ids[uid].params or {}))
            if params.pop("_needs_executor", False):
                # Inject the shared event loop object the units expect.
                # Prefer explicit background loop key so units find an asyncio.AbstractEventLoop.
                params["_background_loop"] = getattr(self, "_loop", None) or getattr(
                    self, "background_loop", None
                )
                # Also set _executor_loop for compatibility with some units.
                params["_executor_loop"] = params.get("_background_loop")

            if stream_callback is not None:
                if params.get("_accepts_stream_callback") or self._unit_ids[
                    uid
                ].type in (
                    "LLMAgent",
                    "RunWorkflow",
                    "Chameleon",
                    "AgentOrchestrator",
                ):
                    params["_stream_callback"] = stream_callback

            # Schedule execution coroutine
            tasks.append(
                self._execute_unit_coro(
                    self._unit_ids[uid],
                    inputs,
                    params,
                    action,
                    state=state,
                    stream_callback=stream_callback,
                )
            )

        if not tasks:
            return

        # Await all tasks in this level concurrently
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Apply outputs/state under lock
        with self._lock:
            for idx, uid in enumerate([u for u in level if u in self._unit_ids]):
                try:
                    outputs, new_state = results[idx]
                except Exception:
                    outputs, new_state = {}, {}
                if outputs:
                    self._outputs[uid] = outputs
                if new_state:
                    self._state[uid] = new_state

    async def _step_async(
        self,
        dt: float,
        action: list[float] | None = None,
        initial_inputs: dict[str, dict[str, Any]] | None = None,
        stream_callback: Callable[[str], None] | None = None,
        state: dict[str, Any] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:
        """
        Async version of step: runs the entire topological execution on the shared loop.
        Preserves original semantics but runs each topological level in parallel.
        """
        self._initial_inputs = initial_inputs or {}
        self._injected_trigger = "step"
        self._injected_action = (
            list(action) if action is not None else [0.0] * self._n_act
        )

        code_by_id: dict[str, str] = {}
        lang_by_id: dict[str, str] = {}
        if self.graph.code_blocks:
            for b in self.graph.code_blocks:
                code_by_id[b.id] = b.source
                lang_by_id[b.id] = b.language or "python"

        # Iterate levels and run each level concurrently
        for level in self._levels:
            # Special-case: we still need to honor the original handling for code_block_driven
            # which sometimes used _run_coro to invoke helpers. Here we run all logic on the loop.
            await self._run_level(level, action, initial_inputs, stream_callback)

            # After level completes, certain code_block_driven nodes might have updated outputs
            # which will be used by next levels via _build_inputs.

        # Observation from Join (or from StepRewards when present, same vector)
        join_out = self._outputs.get(self._join_id, {}) if self._join_id else {}
        raw = join_out.get("observation", [])
        obs = (
            [float(x) for x in raw] if isinstance(raw, (list, tuple)) else [float(raw)]
        )
        if not obs and self._step_rewards_id:
            raw = self._outputs.get(self._step_rewards_id, {}).get("observation", [])
            obs = (
                [float(x) for x in raw]
                if isinstance(raw, (list, tuple))
                else [float(raw)]
            )

        info: dict[str, Any] = {"outputs": dict(self._outputs)}
        if self._step_rewards_id:
            out = self._outputs.get(self._step_rewards_id, {})
            if "reward" in out:
                info["reward"] = float(out["reward"])
            if "done" in out:
                info["done"] = bool(out["done"])
        return obs, info

    def step(
        self,
        dt: float,
        action: list[float] | None = None,
        initial_inputs: dict[str, dict[str, Any]] | None = None,
        stream_callback: Callable[[str], None] | None = None,
        state: dict[str, Any] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:
        """
        Execute one step. Returns (observation, info).

        action: normalized [-1,1] or [0,1] depending on spec; mapped to valve setpoints.
        initial_inputs: optional { unit_id: { port_name: value } } for edit flows (e.g. Inject).
        stream_callback: optional; passed to LLMAgent, RunWorkflow, and Chameleon.
        Canonical: action injected into Switch input; observation from Join output.
        """
        # Run the entire step on the shared loop as a single coroutine to avoid per-unit blocking.
        return self._run_coro(
            self._step_async(
                dt,
                action=action,
                initial_inputs=initial_inputs,
                stream_callback=stream_callback,
                state=state,
            )
        )

    def reset(
        self,
        initial_state: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:
        """Reset all unit states and run one step with valves closed (idle)."""
        self._state = dict(initial_state or {})
        self._outputs = {}
        self._injected_trigger = "reset"
        self._injected_action = [0.0] * self._n_act
        return self.step(0.1, action=self._injected_action)

    def shutdown(self, timeout: float = 2.0) -> None:
        """Shut down per-executor resources. The shared loop is NOT stopped here —
        it is a process-level singleton and may be used by other concurrent executors
        (e.g. nested workflow runs, Telegram poller). Stopping it prematurely would
        interrupt any workflow still running on it."""
        try:
            self._thread_pool.shutdown(wait=False)
        except Exception:
            pass
