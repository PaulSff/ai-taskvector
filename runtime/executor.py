# Graph executor: run process graphs in topological order (plain execution).
#
# Load a workflow JSON/YAML, run the graph once; each unit executes in dependency order.
# Canonical topology (StepDriver, Join, Switch) is optional — used for RL training;
# without it, the graph runs as a plain dataflow (no action/observation).

from __future__ import annotations

import asyncio
import inspect
import subprocess
import threading
import time
from typing import Any, Callable, Coroutine, Optional, cast

from core.schemas.agent_node import (
    EXECUTOR_EXCLUDED_TYPES,
    get_join,
    get_step_driver,
    get_step_rewards,
    get_switch,
    get_switch_action_target_ids,
)
from core.schemas.process_graph import Connection, ProcessGraph, Unit
from units.registry import get_unit_spec


def _run_shell_block(source: str, timeout: float = 30.0) -> Any:
    """Run a unit's code_block as a bash script; return stdout/stderr as result (sync fallback)."""
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


async def _run_shell_block_async(source: str, timeout: float = 30.0) -> Any:
    """Async variant using asyncio subprocess APIs."""
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        source,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        await proc.wait()
        return ""
    out = (stdout.decode() if stdout else "") or (stderr.decode() if stderr else "")
    return out.strip()


def _run_code_block(
    source: str,
    node_id: str,
    state: dict[str, Any],
    inputs: dict[str, Any],
    params: dict[str, Any],
) -> Any:
    """Run a unit's code_block with state/inputs/params; return single value (PyFlow-adapter contract)."""
    # Normalize inputs: replace None with 0.0 without mutating caller dict
    inputs = {k: (0.0 if v is None else v) for k, v in (inputs or {}).items()}
    scope: dict[str, Any] = {
        "state": state,
        "inputs": inputs,
        "node_id": node_id,
        "params": params or {},
    }
    indented = "\n  ".join(source.strip().splitlines())
    wrapped = f"def _fn(state, inputs):\n  {indented}\n_result = _fn(state, inputs)"
    # Intentionally using scope as globals so node_id/params accessible; keep builtins available
    exec(wrapped, scope)
    return scope.get("_result", 0.0)


async def _run_code_block_async(
    source: str,
    node_id: str,
    state: dict[str, Any],
    inputs: dict[str, Any],
    params: dict[str, Any],
) -> Any:
    """Async wrapper that executes the existing sync _run_code_block in a thread."""
    return await asyncio.to_thread(
        _run_code_block, source, node_id, state, inputs, params
    )


def _resolve_port(conn: Connection, from_unit: Unit, to_unit: Unit) -> tuple[str, str]:
    """Resolve from_port/to_port to port names using graph Unit ports (Registry → Graph → Executor)."""
    fp = conn.from_port or "0"
    tp = conn.to_port or "0"
    if from_unit.output_ports:
        names = [p.name for p in from_unit.output_ports]
        try:
            idx = int(fp)
            if 0 <= idx < len(names):
                fp = names[idx]
        except (ValueError, TypeError):
            if fp in names:
                pass
            else:
                fp = names[0]
    if to_unit.input_ports:
        names = [p.name for p in to_unit.input_ports]
        try:
            idx = int(tp)
            if 0 <= idx < len(names):
                tp = names[idx]
        except (ValueError, TypeError):
            if tp in names:
                pass
            else:
                tp = names[0]
    return (fp, tp)


def _topological_order(graph: ProcessGraph, process_unit_ids: set[str]) -> list[str]:
    """Return unit ids in execution order (dependencies first). Raises on cycle."""
    preds: dict[str, list[str]] = {uid: [] for uid in process_unit_ids}
    for c in graph.connections:
        if (
            c.from_id in process_unit_ids
            and c.to_id in process_unit_ids
            and c.from_id != c.to_id
        ):
            if c.to_id not in preds:
                preds[c.to_id] = []
            preds[c.to_id].append(c.from_id)

    order: list[str] = []
    remaining = set(process_unit_ids)
    while remaining:
        ready = [u for u in remaining if all(p in order for p in preds.get(u, []))]
        if not ready:
            raise ValueError("Cycle detected in graph or unresolved dependencies")
        order.extend(sorted(ready))
        remaining -= set(ready)
    return order


def _validate_graph_for_execution(graph: ProcessGraph) -> None:
    """Raise ValueError if the graph is invalid for execution (invalid connections or ports)."""
    unit_ids = {u.id: u for u in graph.units}
    process_ids = {
        u.id
        for u in graph.units
        if u.type not in EXECUTOR_EXCLUDED_TYPES and get_unit_spec(u.type) is not None
    }
    for c in graph.connections:
        # If connection references units not in graph, treat as valid
        if c.from_id not in unit_ids or c.to_id not in unit_ids:
            continue
        from_unit = unit_ids[c.from_id]
        to_unit = unit_ids[c.to_id]
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


_shared_loop: Optional[asyncio.AbstractEventLoop] = None
_shared_loop_thread: Optional[threading.Thread] = None
_shared_loop_lock = threading.Lock()


def _start_loop(loop: asyncio.AbstractEventLoop) -> None:
    # This runs in the loop thread only.
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_shared_loop() -> asyncio.AbstractEventLoop:
    global _shared_loop, _shared_loop_thread
    with _shared_loop_lock:
        if _shared_loop is not None and _shared_loop.is_running():
            return _shared_loop
        if _shared_loop is None:
            _shared_loop = asyncio.new_event_loop()
        # If thread exists and is alive but loop not running, don't recreate; ensure single start
        if _shared_loop_thread is None or not _shared_loop_thread.is_alive():
            _shared_loop_thread = threading.Thread(
                target=_start_loop, args=(_shared_loop,), daemon=True
            )
            _shared_loop_thread.start()
            # wait for loop to become running
            for _ in range(50):
                if _shared_loop.is_running():
                    break
                time.sleep(0.02)
        return _shared_loop


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

    def _run_coro(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Schedule coro on the background loop and wait for result (blocks)."""
        if not self._loop or self._loop.is_closed():
            raise RuntimeError("Executor event loop not initialized or closed")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
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
        - sync unit specs executed in a thread via asyncio.to_thread
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
        # stream callback handling: pass through if given and unit expects stream (done by caller via params)
        try:
            if getattr(spec, "execute_async", None):
                # execute_async(state, inputs, params) -> (outputs, new_state) or dict/single value
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

        # Fallback: run existing sync step_fn in a thread to avoid blocking loop
        sync_fn = getattr(spec, "step_fn", None)
        if sync_fn is None:
            return {}, {}

        def _sync_step():
            return sync_fn(params, inputs, state, 0.0)

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
        # If user provided an async coroutine function, schedule it on the background loop.
        try:
            if inspect.iscoroutinefunction(stream_callback):
                if not self._loop or self._loop.is_closed():
                    return
                # schedule and don't wait — streaming callbacks are best-effort
                try:
                    asyncio.run_coroutine_threadsafe(stream_callback(chunk), self._loop)
                except Exception:
                    pass
                return
            # Sync callable: run in a separate thread so we don't block the main thread that called step()
            threading.Thread(target=stream_callback, args=(chunk,), daemon=True).start()
        except Exception:
            pass

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
                        # run async shell helper via background loop, block until done
                        result = self._run_coro(_run_shell_block_async(source))
                    else:
                        cb_state = self._graph_state_for_code_block()
                        inputs = self._build_inputs(uid, action)
                        params = dict(unit.params or {})
                        # runtime injection: if workflow explicitly requests executor, provide it
                        if params.pop("_needs_executor", False):
                            params["_executor"] = self
                        result = self._run_coro(
                            _run_code_block_async(source, uid, cb_state, inputs, params)
                        )
                    out_port = (
                        (spec.output_ports[0][0])
                        if getattr(spec, "output_ports", None)
                        else "out"
                    )
                    with self._lock:
                        self._outputs[uid] = {out_port: result}
                    continue

            if (
                not getattr(spec, "step_fn", None)
                and not getattr(spec, "step_fn_async", None)
                and not getattr(spec, "execute_async", None)
            ):
                continue

            inputs = self._build_inputs(uid, action)
            state = self._state.get(uid, {}) or {}
            params = dict(unit.params or {})

            # runtime injection: if workflow explicitly requests executor, provide it
            if params.pop("_needs_executor", False):
                params["_executor"] = self

            # pass stream callback into params for LLMAgent-like units (same behavior as before)
            if stream_callback is not None and unit.type in (
                "LLMAgent",
                "RunWorkflow",
                "Chameleon",
                "AgentOrchestrator",
            ):
                params["_stream_callback"] = stream_callback

            # Execute unit: run coroutine on background loop and block until done
            outputs, new_state = self._run_coro(
                self._execute_unit_coro(
                    unit,
                    inputs,
                    params,
                    action,
                    stream_callback=stream_callback,
                    state=state,
                )
            )

            with self._lock:
                self._outputs[uid] = outputs or {}
                self._state[uid] = new_state or {}

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


def shutdown_shared_loop(timeout: float = 2.0) -> None:
    global _shared_loop, _shared_loop_thread
    loop = _shared_loop
    th = _shared_loop_thread
    if not loop:
        return

    # ask loop to stop
    try:
        loop.call_soon_threadsafe(loop.stop)
    except Exception:
        pass

    # schedule close of selector socket and loop from loop thread
    def _close_from_loop():
        try:
            ssock = getattr(loop, "_ssock", None)
            if ssock is not None:
                try:
                    ssock.close()
                except Exception:
                    pass
            try:
                loop.close()
            except Exception:
                pass
        except Exception:
            pass

    try:
        loop.call_soon_threadsafe(_close_from_loop)
    except Exception:
        # fallback: attempt to close here (best-effort)
        try:
            ssock = getattr(loop, "_ssock", None)
            if ssock is not None:
                try:
                    ssock.close()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass

    # wait for thread to exit
    try:
        if th is not None and th.is_alive():
            th.join(timeout)
    except Exception:
        pass

    _shared_loop = None
    _shared_loop_thread = None
