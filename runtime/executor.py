# Graph executor: run process graphs in topological order (plain execution).
#
# Load a workflow JSON/YAML, run the graph once; each unit executes in dependency order.
# Canonical topology (StepDriver, Join, Switch) is optional — used for RL training;
# without it, the graph runs as a plain dataflow (no action/observation).

from __future__ import annotations

import asyncio
import inspect
import logging
import queue
import threading
import types
from collections.abc import Callable, Coroutine, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, cast

from core.schemas.agent_node import (
    EXECUTOR_EXCLUDED_TYPES,
    get_join,
    get_step_driver,
    get_step_rewards,
    get_switch,
    get_switch_action_target_ids,
)
from core.schemas.process_graph import Connection, ProcessGraph, Unit
from services.logging import setup_colored_logging
from units.registry import get_unit_spec

from .graph_validator import validate_graph_for_execution
from .resolve_ports import resolve_port
from .run_code_block import run_code_block_async
from .run_shell_block import run_shell_block_async
from .shared_loop import (
    ensure_shared_loop,
)
from .topological_order import topological_order

THREAD_POOL_MAX_WORKERS = 8

logger = setup_colored_logging(logging.INFO)

@dataclass(frozen=True)
class GraphWakeupEvent:
    unit_id: str
    payload: dict[str, Any] = field(default_factory=dict)  # must match that unit's input port names
    seq: int | None = None

GraphWakeupCallback = Callable[[GraphWakeupEvent], None]

class GraphExecutor:
    """
    Executes a process graph in topological order (one forward pass).
    Use execute() for plain execution; step()/reset() for RL-style control (optional Join/Switch/StepDriver).
    """
    graph: ProcessGraph
    _unit_ids: dict[str, Unit]
    _process_ids: set[str]
    _order: list[str]
    _step_driver_id: str | None
    _join_id: str | None
    _switch_id: str | None
    _step_rewards_id: str | None
    _action_ids: list[str]
    _n_act: int
    _n_obs: int
    _loop: asyncio.AbstractEventLoop
    _loop_thread: threading.Thread | None
    _lock: threading.Lock
    _thread_pool: ThreadPoolExecutor
    _levels: list[list[str]]
    _wakeup_pending_lock: threading.Lock
    _active_stream_callback: Any | None
    _wakeup_start_lock: threading.Lock
    _wakeup_stop_requested: bool
    _state: dict[str, dict[str, Any]]
    _outputs: dict[str, dict[str, Any]]
    _initial_inputs: dict[str, dict[str, Any]]
    _event_inputs: dict[str, dict[str, Any]]
    _last_seq: dict[str, int]
    _code_block_compiled: dict[str, Any]
    _injected_action: list[float]
    _incoming: dict[str, list[tuple[str, str, str]]]
    _wakeup_queue: queue.Queue[GraphWakeupEvent | None]
    _wakeup_task: asyncio.Task[None] | None
    _wakeup_pending: set[str]
    _successors: dict[str, set[str]]


    def __init__(self, graph: ProcessGraph) -> None:
        from units.app_settings_param import resolve_process_graph_param_refs

        graph = cast(ProcessGraph, resolve_process_graph_param_refs(graph))
        validate_graph_for_execution(graph)
        self.graph = graph

        # unit_id -> compiled code object (compile once)
        self._code_block_compiled = {}
        if self.graph.code_blocks:
            for b in self.graph.code_blocks:
                uid = b.id
                if (b.language or "python").lower() in ("shell", "bash"):
                    continue

                source = b.source or ""
                indented = "\n  ".join(source.strip().splitlines())
                wrapped = (
                    f"def _fn(state, inputs):\n"
                    f"  {indented}\n"
                    f"_result = _fn(state, inputs)"
                )
                self._code_block_compiled[uid] = compile(
                    wrapped,
                    filename=f"<code_block:{uid}>",
                    mode="exec",
                )

        self._unit_ids = {u.id: u for u in graph.units}
        self._process_ids = {
            u.id
            for u in graph.units
            if u.type not in EXECUTOR_EXCLUDED_TYPES
            and get_unit_spec(u.type) is not None
        }
        # _order is a topological ordering (list). We'll convert to levels for parallel execution.
        self._order = topological_order(graph, self._process_ids)
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
        self._injected_action = [0.0] * self._n_act
        self._state = {}
        self._outputs = {}
        self._initial_inputs = {}

        # Background asyncio loop and thread (shared across executors)
        self._loop = ensure_shared_loop()
        self._loop_thread = None  # managed by module-level shared loop

        # Lock to protect outputs/state updates if unit code runs concurrently in threads.
        self._lock = threading.Lock()

        # Reused thread pool for sync step_fns and sync stream callbacks
        self._thread_pool = ThreadPoolExecutor(max_workers=THREAD_POOL_MAX_WORKERS)

        # Precompute topological levels (list of lists). Each level can run in parallel.
        self._levels = self._compute_levels(self._order, self.graph.connections)
        # Precompute incoming edges + resolved portnames
        self._incoming = {
            u.id: [] for u in graph.units
        }

        # Wake up graph callback
        self._event_inputs = {}
        self._wakeup_queue = queue.Queue()
        self._last_seq = {}

        self._wakeup_task = None
        self._wakeup_start_lock = threading.Lock()
        self._wakeup_stop_requested = False

        self._wakeup_pending = set()
        self._wakeup_pending_lock = threading.Lock()

        self._successors = {
            uid: set() for uid in self._process_ids
        }
        self._active_stream_callback = None


        # Build incoming and successor edges
        for c in self.graph.connections:
            to_unit = self._unit_ids.get(c.to_id)
            from_unit = self._unit_ids.get(c.from_id)

            if not to_unit or not from_unit:
                continue

            fp, tp = resolve_port(c, from_unit, to_unit)
            self._incoming[c.to_id].append((c.from_id, fp, tp))

            if (
                c.from_id in self._process_ids
                and c.to_id in self._process_ids
            ):
                self._successors[c.from_id].add(c.to_id)


    def _run_compiled_code_block(
        self,
        node_id: str,
        compiled: types.CodeType,
        state: dict[str, Any],
        inputs: dict[str, Any],
        params: dict[str, Any],
    ) -> Any:
        inputs = {k: (0.0 if v is None else v) for k, v in (inputs or {}).items()}
        scope: dict[str, Any] = {
            "state": state,
            "inputs": inputs,
            "node_id": node_id,
            "params": params or {},
        }
        exec(compiled, scope)  # compiled already contains the def + call + _result
        return scope.get("_result", 0.0)


    def _compute_levels(
        self,
        order: list[str],
        connections: Sequence[Connection],
    ) -> list[list[str]]:
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
                for value in deps.values():
                    if n in value:
                        value.remove(n)
            # prune deps of removed nodes
            deps = {k: v for k, v in deps.items() if k in remaining}
        return levels

    def _run_coro(self, coro: Coroutine[Any, Any, Any]) -> tuple[list[float], dict[str, Any]]:
        loop = self._loop
        if not loop or loop.is_closed():
            logger.error("Executor event loop not initialized or closed")
            # best-effort shape: obs vector length = self._n_act (or use 0s of the expected obs size)
            return [0.0] * self._n_act, {"error": "executor_loop_not_initialized_or_closed"}

        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return fut.result()
        except Exception as e:
            logger.exception("Background loop error")
            return [0.0] * self._n_act, {
                "error": type(e).__name__,
                "message": str(e),
            }

    async def _wakeup_consumer_coro(self) -> None:
        loop = self._loop

        while True:
            event = await loop.run_in_executor(
                None,
                self._wakeup_queue.get,
            )

            if event is None:
                self._wakeup_stop_requested = True
                return

            try:
                if event.seq is not None:
                    previous = self._last_seq.get(event.unit_id)
                    if previous is not None and event.seq <= previous:
                        continue
                    self._last_seq[event.unit_id] = event.seq

                if event.payload:
                    self._event_inputs.setdefault(event.unit_id, {}).update(
                        event.payload
                    )

                with self._wakeup_pending_lock:
                    self._wakeup_pending.add(event.unit_id)

                # Let immediately-arriving events coalesce into the same rerun.
                await asyncio.sleep(0)

                with self._wakeup_pending_lock:
                    roots = set(self._wakeup_pending)
                    self._wakeup_pending.clear()

                await self._rerun_from_roots(roots)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Wakeup-triggered graph execution failed for unit %s",
                    event.unit_id,
                )

    # Called by units requesting the downstream graph rerun
    def graph_wakeup_callback(
        self,
        event: GraphWakeupEvent | str,
        payload: dict[str, Any] | None = None,
        seq: int | None = None,
    ) -> None:
        if isinstance(event, str):
            event = GraphWakeupEvent(
                unit_id=event,
                payload=dict(payload or {}),
                seq=seq,
            )
        else:
            event = GraphWakeupEvent(
                unit_id=event.unit_id,
                payload=dict(event.payload or {}),
                seq=event.seq,
            )

        if event.unit_id not in self._unit_ids:
            logger.warning("Ignoring wakeup for unknown unit: %s", event.unit_id)
            return

        self._wakeup_queue.put(event)


    def start_wakeup_consumer(self) -> None:
        with self._wakeup_start_lock:
            if self._wakeup_task is not None and not self._wakeup_task.done():
                return

            self._wakeup_stop_requested = False

            loop = self._loop
            if loop.is_closed():
                logger.error("Cannot start wakeup consumer: event loop is closed")
                return

            def create_task() -> None:
                if self._wakeup_task is None or self._wakeup_task.done():
                    self._wakeup_task = loop.create_task(
                        self._wakeup_consumer_coro()
                    )

            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is loop:
                create_task()
            else:
                _ = loop.call_soon_threadsafe(create_task)


    def stop_wakeup_consumer(self) -> None:
        self._wakeup_queue.put(None)


    def _downstream_including_self(self, roots: set[str]) -> set[str]:
        seen: set[str] = set()
        stack = [
            unit_id
            for unit_id in roots
            if unit_id in self._process_ids
        ]

        while stack:
            unit_id = stack.pop()
            if unit_id in seen:
                continue

            seen.add(unit_id)
            stack.extend(
                successor
                for successor in self._successors.get(unit_id, ())
                if successor not in seen
            )

        return seen


    async def _rerun_from_roots(self, roots: set[str]) -> None:
        if not roots:
            return
        rerun_set = self._downstream_including_self(roots)

        for level in self._levels:
            level_to_run = [uid for uid in level if uid in rerun_set]
            if level_to_run:
                await self._run_level(
                    level_to_run,
                    action=self._injected_action,
                    initial_inputs=self._initial_inputs,
                    stream_callback=self._active_stream_callback,
                )


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
        self._event_inputs = {}
        self._last_seq = {}
        self._initial_inputs = initial_inputs or {}
        self._active_stream_callback = stream_callback

        self.start_wakeup_consumer()

        self._injected_trigger = "step"
        self._injected_action = [0.0] * self._n_act

        _, info = self.step(
            0.0,
            action=self._injected_action,
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
        unit = self._unit_ids.get(unit_id)
        if not unit:
            return {}

        spec = get_unit_spec(unit.type)
        if not spec:
            return {}

        inputs: dict[str, Any] = {}
        init = (initial_inputs or self._initial_inputs or {}).get(unit_id)
        if init:
            inputs.update(init)

        # NEW: overlay latest wakeup-provided inputs for this unit
        ev = self._event_inputs.get(unit_id)
        if ev:
            inputs.update(ev)

        with self._lock:
            for from_id, fp, tp in self._incoming.get(unit_id, []):
                out = self._outputs.get(from_id)
                if not out:
                    continue
                if fp in out:
                    inputs[tp] = out[fp]

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
                    result = await run_shell_block_async(source)
                else:
                    cb_state = self._graph_state_for_code_block()

                    lang = (
                        next(
                            (
                                b.language
                                for b in self.graph.code_blocks
                                if b.id == unit.id
                            ),
                            None,
                        )
                        or "python"
                    ).lower()
                    if lang in ("shell", "bash"):
                        # keep existing behavior
                        result = await run_shell_block_async(source)
                    else:
                        compiled = self._code_block_compiled.get(unit.id)
                        if compiled is None:
                            # fallback (shouldn't happen if compiled in __init__)
                            result = await run_code_block_async(
                                source, unit.id, cb_state, inputs, params
                            )
                        else:
                            result = await asyncio.to_thread(
                                self._run_compiled_code_block,
                                unit.id,
                                compiled,
                                cb_state,
                                inputs,
                                params,
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

        def _sync_step() -> tuple[dict[str, Any], dict[str, Any]]:
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

        if inspect.iscoroutinefunction(stream_callback):
            loop = self._loop
            if loop and not loop.is_closed():
                try:
                    _ = asyncio.run_coroutine_threadsafe(stream_callback(chunk), loop)
                except (RuntimeError, asyncio.CancelledError) as e:
                    logger.debug("Failed to schedule stream_callback coroutine: %s", e)
                except Exception:
                    logger.exception("Unexpected error scheduling stream_callback coroutine")
            return

        # Sync callable: call directly — queue.put is thread-safe and non-blocking
        # (submitting to thread pool would introduce a race where the sentinel None
        # can arrive before pending chunk jobs complete).
        try:
            stream_callback(chunk)
        except (RuntimeError, TypeError) as e:
            logger.debug("stream_callback failed: %s", e)
        except Exception:
            logger.exception("Unexpected error in stream_callback")


    async def _run_level(
        self,
        level: list[str],
        action: list[float] | None,
        initial_inputs: dict[str, dict[str, Any]] | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ):
        """
        Execute all units in a single topological level in parallel.
        Each unit's inputs are built from current self._outputs (protected by lock).
        After a unit finishes, its outputs/state are written under self._lock.
        """
        tasks: list[
            Coroutine[
                Any,
                Any,
                tuple[dict[str, Any], dict[str, Any]],
            ]
        ] = []

        uids_for_tasks: list[str] = []

        for uid in level:
            unit = self._unit_ids.get(uid)
            if not unit:
                continue
            spec = get_unit_spec(unit.type)
            if not spec:
                continue

            if (
                not getattr(spec, "step_fn", None)
                and not getattr(spec, "step_fn_async", None)
                and not getattr(spec, "execute_async", None)
                and not getattr(spec, "code_block_driven", False)
            ):
                continue

            inputs = self._build_inputs(uid, action, initial_inputs)
            state = self._state.get(uid, {}) or {}
            params = dict(self._unit_ids[uid].params or {})

            # Identify units to inject the background loop into (must have _needs_executor: true at params)
            if params.pop("_needs_executor", False):
                params["_background_loop"] = getattr(self, "_loop", None) or getattr(
                    self, "background_loop", None
                )
                params["_executor_loop"] = params.get("_background_loop")

            # Identify units to provide the wakeup callback to (must have `supports_graph_wakeup: true` at params)
            if getattr(spec, "supports_graph_wakeup", False):
                params["_graph_wakeup_callback"] = self.graph_wakeup_callback

            if self._unit_ids[uid].type in {
                "ZmqIn",
            }:
                params["_graph_wakeup_callback"] = self.graph_wakeup_callback

            if (
                stream_callback is not None
                and (
                    params.get("_accepts_stream_callback")
                    or self._unit_ids[uid].type
                    in (
                        "LLMAgent",
                        "RunWorkflow",
                        "Chameleon",
                        "AgentOrchestrator",
                        "TelegramBot",
                    )
                )
            ):
                    params["_stream_callback"] = stream_callback

            uids_for_tasks.append(uid)
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

        results = await asyncio.gather(*tasks, return_exceptions=False)

        with self._lock:
            for idx, uid in enumerate(uids_for_tasks):
                outputs, new_state = results[idx]
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
        state: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:

        """
        Async version of step: runs the entire topological execution on the shared loop.
        Preserves original semantics but runs each topological level in parallel.
        """
        if state is not None:
            self._state = {
                unit_id: dict(unit_state)
                for unit_id, unit_state in state.items()
            }
        self._initial_inputs = initial_inputs or {}
        self._active_stream_callback = stream_callback
        self.start_wakeup_consumer()
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
        state: dict[str, dict[str, Any]] | None = None,
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
        self._event_inputs = {}
        self._last_seq = {}
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
            logger.exception("Executor thread pool shutdown failed")
