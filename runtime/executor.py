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
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import cast

from core.schemas.agent_node import (
    EXECUTOR_EXCLUDED_TYPES,
    get_join,
    get_step_driver,
    get_step_rewards,
    get_switch,
    get_switch_action_target_ids,
)
from core.schemas.primitives import Data, Output
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
    """Requests execution of a graph unit."""

    unit_id: str

    # Keys must correspond to the input-port names of `unit_id`.
    payload: Data = field(default_factory=dict)

    # Optional monotonic sequence number used to discard stale events.
    seq: int | None = None

    # Optional event signaled after the wakeup has been processed.
    # It is excluded from equality and repr because it is synchronization state.
    completion: threading.Event | None = field(
        default=None,
        compare=False,
        repr=False,
    )


GraphWakeupCallback = Callable[[GraphWakeupEvent], None]
type GraphUpdateCallback = Callable[
    [dict[str, dict[str, object]]],
    None,
]
type GraphStreamCallback = Callable[[str], None]


class GraphExecutor:
    """
    Executes a process graph in topological order using one forward pass.

    Use `execute()` for ordinary execution. Use `step()` and `reset()` for
    optional RL-style control involving Join, Switch, or StepDriver units.
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
    _injected_trigger: str

    _loop: asyncio.AbstractEventLoop
    _loop_thread: threading.Thread | None
    _lock: threading.Lock
    _thread_pool: ThreadPoolExecutor

    _levels: list[list[str]]
    _incoming: dict[str, list[tuple[str, str, str]]]
    _successors: dict[str, set[str]]

    _wakeup_pending_lock: threading.Lock
    _wakeup_start_lock: threading.Lock
    _wakeup_stop_requested: bool

    _wakeup_queue: queue.Queue[GraphWakeupEvent | None]
    _wakeup_task: asyncio.Task[None] | None
    _wakeup_pending: set[str]

    _active_stream_callback: GraphStreamCallback | None
    _update_callback: GraphUpdateCallback | None

    _state: dict[str, dict[str, object]]
    _outputs: dict[str, dict[str, object]]
    _initial_inputs: dict[str, dict[str, object]]
    _event_inputs: dict[str, dict[str, object]]
    _last_seq: dict[str, int]

    _code_block_compiled: dict[str, types.CodeType]
    _injected_action: list[float]

    _keep_alive_stop: threading.Event

    def __init__(self, graph: ProcessGraph) -> None:
        from units.app_settings_param import resolve_process_graph_param_refs

        graph = cast(
            ProcessGraph,
            resolve_process_graph_param_refs(graph),
        )

        validate_graph_for_execution(graph)
        self.graph = graph

        self._code_block_compiled = {}

        if self.graph.code_blocks:
            for block in self.graph.code_blocks:
                unit_id = block.id

                if (block.language or "python").lower() in {"shell", "bash"}:
                    continue

                source = block.source or ""
                indented = "\n  ".join(source.strip().splitlines())

                wrapped = (
                    "def _fn(state, inputs):\n"
                    f"  {indented}\n"
                    "_result = _fn(state, inputs)"
                )

                self._code_block_compiled[unit_id] = compile(
                    wrapped,
                    filename=f"<code_block:{unit_id}>",
                    mode="exec",
                )

        self._unit_ids = {unit.id: unit for unit in graph.units}

        self._process_ids = {
            unit.id
            for unit in graph.units
            if (
                unit.type not in EXECUTOR_EXCLUDED_TYPES
                and get_unit_spec(unit.type) is not None
            )
        }

        self._order = topological_order(
            graph,
            self._process_ids,
        )

        step_driver = get_step_driver(graph)
        join = get_join(graph)
        switch = get_switch(graph)
        step_rewards = get_step_rewards(graph)

        self._step_driver_id = step_driver.id if step_driver else None
        self._join_id = join.id if join else None
        self._switch_id = switch.id if switch else None
        self._step_rewards_id = (
            step_rewards.id if step_rewards else None
        )

        self._action_ids = get_switch_action_target_ids(graph)
        self._n_act = max(len(self._action_ids), 1)
        self._n_obs = max(
            sum(
                1
                for connection in graph.connections
                if connection.to_id == self._join_id
            ),
            1,
        )

        self._injected_trigger = "step"
        self._injected_action = [0.0] * self._n_act

        self._state = {}
        self._outputs = {}
        self._initial_inputs = {}
        self._event_inputs = {}
        self._last_seq = {}

        self._loop = ensure_shared_loop()
        self._loop_thread = None

        self._lock = threading.Lock()
        self._thread_pool = ThreadPoolExecutor(
            max_workers=THREAD_POOL_MAX_WORKERS,
        )

        self._levels = self._compute_levels(
            self._order,
            self.graph.connections,
        )

        self._incoming = {
            unit.id: []
            for unit in graph.units
        }

        self._successors = {
            unit_id: set()
            for unit_id in self._process_ids
        }

        self._wakeup_queue = queue.Queue()
        self._wakeup_task = None
        self._wakeup_pending = set()
        self._wakeup_pending_lock = threading.Lock()
        self._wakeup_start_lock = threading.Lock()
        self._wakeup_stop_requested = False

        self._active_stream_callback = None
        self._update_callback = None
        self._keep_alive_stop = threading.Event()

        for connection in self.graph.connections:
            to_unit = self._unit_ids.get(connection.to_id)
            from_unit = self._unit_ids.get(connection.from_id)

            if to_unit is None or from_unit is None:
                continue

            from_port, to_port = resolve_port(
                connection,
                from_unit,
                to_unit,
            )

            self._incoming[connection.to_id].append(
                (
                    connection.from_id,
                    from_port,
                    to_port,
                )
            )

            if (
                connection.from_id in self._process_ids
                and connection.to_id in self._process_ids
            ):
                self._successors[connection.from_id].add(
                    connection.to_id
                )


    def _run_compiled_code_block(
        self,
        node_id: str,
        compiled: types.CodeType,
        state: Data,
        inputs: Data,
        params: Data,
    ) -> float:
        inputs = {
            k: (0.0 if v is None else v)
            for k, v in (inputs or {}).items()
        }

        scope: Data = {
            "state": state,
            "inputs": inputs,
            "node_id": node_id,
            "params": params or {},
        }

        exec(compiled, scope)

        result = scope.get("_result", 0.0)

        if not isinstance(result, (int, float)):
            raise TypeError(
                f"Compiled code must produce a numeric _result, got {type(result).__name__}"
            )

        return float(result)


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

    def _run_coro(
        self,
        coro: Coroutine[object, object, tuple[list[float], dict[str, object]]],
    ) -> tuple[list[float], dict[str, object]]:
        loop = self._loop

        if loop.is_closed():
            logger.error("Executor event loop is closed")
            return (
                [0.0] * self._n_act,
                {"error": "executor_loop_closed"},
            )

        fut = asyncio.run_coroutine_threadsafe(coro, loop)

        try:
            return fut.result()
        except Exception as exc:
            logger.exception("Background loop error")
            return (
                [0.0] * self._n_act,
                {
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )

    async def _wakeup_consumer_coro(self) -> None:
        loop = self._loop

        while True:
            event = await loop.run_in_executor(
                self._thread_pool,
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

                # Coalesce events arriving immediately after this one.
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
            finally:
                if event.completion is not None:
                    event.completion.set()

    # Called by units requesting the downstream graph rerun
    def graph_wakeup_callback(
        self,
        event: GraphWakeupEvent | str,
        payload: Data | None = None,
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
                completion=event.completion,
            )

        if event.unit_id not in self._unit_ids:
            logger.warning("Ignoring wakeup for unknown unit: %s", event.unit_id)
            if event.completion is not None:
                event.completion.set()
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

    def stop_keep_alive(self) -> None:
        self._keep_alive_stop.set()

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

    def _emit_update(self) -> None:
        callback = self._update_callback
        if callback is None:
            return

        with self._lock:
            outputs = {
                unit_id: dict(values)
                for unit_id, values in self._outputs.items()
            }

        try:
            callback(outputs)
        except Exception:
            # A notification failure should not make graph execution fail.
            logger.exception("Graph update callback failed")


    async def _rerun_from_roots(self, roots: set[str]) -> None:
        if not roots:
            return

        rerun_set = self._downstream_including_self(roots)

        for level in self._levels:
            level_to_run = [
                unit_id
                for unit_id in level
                if unit_id in rerun_set
            ]

            if level_to_run:
                await self._run_level(
                    level_to_run,
                    action=self._injected_action,
                    initial_inputs=self._initial_inputs,
                    stream_callback=self._active_stream_callback,
                )

        self._emit_update()


    def execute(
        self,
        initial_inputs: dict[str, dict[str, object]] | None = None,
        stream_callback: GraphStreamCallback | None = None,
        *,
        keep_alive: bool = False,
        execution_timeout_s: float | None = None,
        update_callback: GraphUpdateCallback | None = None,
    ) -> dict[str, object]:
        """
        Run the graph once.

        If keep_alive is true, remain alive after the initial pass and allow
        wakeup events to rerun the graph. update_callback receives a snapshot
        after the initial execution and after each wakeup-triggered rerun.
        """
        self._state = {}
        self._outputs = {}
        self._event_inputs = {}
        self._last_seq = {}
        self._initial_inputs = initial_inputs or {}
        self._active_stream_callback = stream_callback
        self._update_callback = update_callback
        self._keep_alive_stop.clear()

        self.start_wakeup_consumer()

        self._injected_trigger = "step"
        self._injected_action = [0.0] * self._n_act

        _, info = self.step(
            0.0,
            action=self._injected_action,
            initial_inputs=initial_inputs,
            stream_callback=stream_callback,
        )

        # Notify consumers about the initial execution.
        self._emit_update()

        if not keep_alive:
            outputs = info.get("outputs")

            if isinstance(outputs, dict):
                typed_outputs = cast(
                    dict[str, dict[str, object]],
                    outputs,
                )

                return {
                    unit_id: dict(values)
                    for unit_id, values in typed_outputs.items()
                }

            return {}

        # The shared asyncio loop continues processing wakeups in its own thread,
        # so waiting here does not block timer callbacks.
        _ = self._keep_alive_stop.wait(timeout=execution_timeout_s)

        with self._lock:
            return {
                unit_id: dict(outputs)
                for unit_id, outputs in self._outputs.items()
            }


    def _build_inputs(
        self,
        unit_id: str,
        action: list[float] | None,
        initial_inputs: dict[str, dict[str, object]] | None = None,
    ) -> Data:
        unit = self._unit_ids.get(unit_id)
        if not unit:
            return {}

        spec = get_unit_spec(unit.type)
        if not spec:
            return {}

        inputs: Data = {}
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
        inputs: Data,
        params: Data,
        action: list[float] | None,
        state: Data | None = None,
        stream_callback: GraphStreamCallback | None = None,
    ) -> Output:
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
                exec_fn: Callable[
                    ...,
                    Awaitable[tuple[dict[str, object], dict[str, object]] | None],
                ] | None = getattr(spec, "execute_async", None)

                if exec_fn is not None:
                    res = await exec_fn(state, inputs, params)

                    if res is None:
                        return {}, {}

                    outputs, new_state = res
                    return outputs or {}, new_state or {}

            step_fn_async: Callable[..., Awaitable[object | None]] | None = getattr(
                spec, "step_fn_async", None
            )

            if step_fn_async is not None:
                try:
                    res = await step_fn_async(params, inputs, state, 0.0)
                except TypeError:
                    res = await step_fn_async(params, inputs, state)

                if res is None:
                    return {}, {}

                if isinstance(res, tuple):
                    res_tuple = cast(tuple[object, ...], res)

                    if (
                        len(res_tuple) == 2
                        and isinstance(res_tuple[0], dict)
                        and isinstance(res_tuple[1], dict)
                    ):
                        outputs = cast(dict[str, object], res_tuple[0])
                        new_state = cast(dict[str, object], res_tuple[1])
                        return outputs or {}, new_state or {}

                if isinstance(res, dict):
                    return cast(dict[str, object], res), {}

                out_port = (
                    spec.output_ports[0][0]
                    if getattr(spec, "output_ports", None)
                    else "out"
                )
                return {out_port: res}, {}
        except Exception:
            # Let exceptions propagate to caller; could wrap/log here if desired.
            raise

        # Fallback: run existing sync step_fn in thread pool to avoid blocking loop
        sync_fn = getattr(spec, "step_fn", None)
        if sync_fn is None:
            return {}, {}

        sync_fn_typed = cast(
            Callable[
                [object, object, object, float],
                tuple[dict[str, object], dict[str, object]],
            ],
            sync_fn,
        )

        def _sync_step() -> tuple[dict[str, object], dict[str, object]]:
            return sync_fn_typed(params, inputs, state, 0.0)

        loop = self._loop
        if loop and not loop.is_closed():
            fut = loop.run_in_executor(self._thread_pool, _sync_step)
            outputs, new_state = await fut
        else:
            outputs, new_state = await asyncio.to_thread(_sync_step)

        return (outputs or {}, new_state or {})

    def _graph_state_for_code_block(self) -> dict[str, object]:
        """Build a simple state mapping for code_block execution (same as prior _graph_state closure)."""
        out: dict[str, object] = {}
        with self._lock:
            for nid in self._unit_ids:
                o = self._outputs.get(nid) or {}
                out[nid] = o.get(
                    "out", o.get("value", next(iter(o.values()), 0.0) if o else 0.0)
                )
        return out

    def _call_stream_callback(
        self, chunk: str, stream_callback: GraphStreamCallback | None
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
        initial_inputs: dict[str, dict[str, object]] | None = None,
        stream_callback: GraphStreamCallback| None = None,
    ):
        """
        Execute all units in a single topological level in parallel.
        Each unit's inputs are built from current self._outputs (protected by lock).
        After a unit finishes, its outputs/state are written under self._lock.
        """
        tasks: list[
            Coroutine[
                object,
                object,
                Output,
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

            # Runtime values required by event-driven units.
            params["_unit_id"] = uid
            params["_executor"] = self

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
                "DelayLoop",
                "TelegramBot"
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
        initial_inputs: dict[str, dict[str, object]] | None = None,
        stream_callback: GraphStreamCallback | None = None,
        state: dict[str, dict[str, object]] | None = None,
    ) -> tuple[list[float], dict[str, object]]:

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
        raw: object = join_out.get("observation", [])

        if isinstance(raw, (list, tuple)):
            values = cast(list[object] | tuple[object, ...], raw)
            obs = [
                float(x)
                for x in values
                if isinstance(x, (int, float))
            ]
        elif isinstance(raw, (int, float)):
            obs = [float(raw)]
        else:
            obs = []

        if not obs and self._step_rewards_id:
            step_rewards_out = self._outputs.get(self._step_rewards_id, {})
            raw = step_rewards_out.get("observation", [])

            if isinstance(raw, (list, tuple)):
                values = cast(list[object] | tuple[object, ...], raw)
                obs = [
                    float(x)
                    for x in values
                    if isinstance(x, (int, float))
                ]
            elif isinstance(raw, (int, float)):
                obs = [float(raw)]
            else:
                obs = []

        info: dict[str, object] = {"outputs": dict(self._outputs)}

        if self._step_rewards_id:
            out = self._outputs.get(self._step_rewards_id, {})

            reward = out.get("reward")
            if isinstance(reward, (int, float, str)):
                info["reward"] = float(reward)

            done = out.get("done")
            if isinstance(done, bool):
                info["done"] = done

        return obs, info


    def step(
        self,
        dt: float,
        action: list[float] | None = None,
        initial_inputs: dict[str, dict[str, object]] | None = None,
        stream_callback: GraphStreamCallback | None = None,
        state: dict[str, dict[str, object]] | None = None,
    ) -> tuple[list[float], dict[str, object]]:
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
        initial_state: dict[str, dict[str, object]] | None = None,
    ) -> tuple[list[float], dict[str, object]]:
        """Reset all unit states and run one step with valves closed (idle)."""
        self._state = dict(initial_state or {})
        self._outputs = {}
        self._event_inputs = {}
        self._last_seq = {}
        self._injected_trigger = "reset"
        self._injected_action = [0.0] * self._n_act

        return self.step(0.1, action=self._injected_action)

    def _cleanup_unit(self, unit: Unit) -> None:
        spec = get_unit_spec(unit.type)
        if spec is None or spec.cleanup_fn is None:
            return

        params = dict(unit.params or {})
        params["_unit_id"] = unit.id
        params["_executor"] = self

        with self._lock:
            state = dict(self._state.get(unit.id, {}))

        try:
            spec.cleanup_fn(params, state)
        except Exception:
            logger.exception(
                "Cleanup failed for unit %s (%s)",
                unit.id,
                unit.type,
            )

    def shutdown(self, timeout: float = 2.0) -> None:
        """
        Request a graceful stop through the WorkflowTrigger unit, run unit
        cleanup functions, then release per-executor resources.
        """
        stop_unit_id: str | None = None

        for unit in self.graph.units:
            if unit.type == "WorkflowTrigger" and unit.id == "control":
                stop_unit_id = unit.id
                break

        if stop_unit_id is not None:
            completion = threading.Event()

            self.start_wakeup_consumer()

            self._wakeup_queue.put(
                GraphWakeupEvent(
                    unit_id=stop_unit_id,
                    payload={
                        "payload": {
                            "action": "stop",
                        },
                    },
                    completion=completion,
                )
            )

            if not completion.wait(timeout=timeout):
                logger.warning(
                    "Timed out waiting for stop wakeup execution for unit %s",
                    stop_unit_id,
                )

        # Stop accepting further wakeup events.
        self.stop_wakeup_consumer()

        # Run cleanup functions before releasing the thread pool.
        cleanup_futures: list[Future[None]] = []

        for unit in self.graph.units:
            spec = get_unit_spec(unit.type)
            if spec is None or spec.cleanup_fn is None:
                continue

            cleanup_futures.append(
                self._thread_pool.submit(self._cleanup_unit, unit)
            )

        for future in cleanup_futures:
            try:
                future.result(timeout=timeout)
            except TimeoutError:
                logger.warning("Timed out waiting for unit cleanup")

        # Release per-executor resources.
        try:
            self._thread_pool.shutdown(wait=True)
        except Exception:
            logger.exception("Executor thread pool shutdown failed")
