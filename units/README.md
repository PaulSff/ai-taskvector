# Units: Developer Guide

Units are the building blocks of process graphs. Each unit type is a registered implementation that the graph executor runs in topological order. **Users only connect units; all logic lives in unit implementations.** This guide explains how to develop new units.

## Overview

- **Unit registry** (`units/registry.py`): Maps `type_name` strings to `UnitSpec` (ComfyUI-style).
- **UnitSpec**: Defines input/output ports and a `step_fn` for NumPy execution.
- **Process graph**: Units are `Unit` instances (id, type, params); connections link outputs to inputs.

## UnitSpec

UnitSpec defines the input and output ports for a unit type. These are the **available options** for connections: `Connection.from_port` must reference an output port, and `Connection.to_port` must reference an input port (by index or name). Discover ports via `get_unit_spec(type_name)`.

```python
UnitSpec(
    type_name="MyUnit",           # Must match Unit.type in the process graph
    input_ports=[("port_a", "float"), ("port_b", "float")],
    output_ports=[("result", "float")],
    step_fn=my_step_fn,
    export_template=None,         # Optional: for Node-RED/PyFlow code_block (future)
)
```

### step_fn signature

```python
def step_fn(
    params: dict,   # Unit.params from the process graph
    inputs: dict,   # {port_name: value} resolved from connections
    state: dict,    # Internal state (mutable, persisted between steps)
    dt: float,      # Time step
) -> tuple[dict, dict]:
    """Returns (outputs, new_state)."""
    # outputs: {port_name: value} for downstream units
    # new_state: updated state for next step
    return outputs, new_state
```

- **params**: Type-specific config (e.g. `capacity`, `cooling_rate` for Tank).
- **inputs**: Only ports with incoming connections (or injected by executor, e.g. agent action).
- **state**: Unit-local; use for volumes, temperatures, etc. that persist across steps.
- **outputs**: Must include all `output_ports`; keys must match port names.

### Error output port (optional)

Units that can fail (I/O, parsing, apply) may expose a dedicated **`error`** output port (type `str`). When no error occurs, the unit emits `None` (or empty string). This makes it easy to wire errors to a **Debug** unit or to conditional logic without parsing the main payload.

**Canonical units with an `error` port:**

| Unit              | Main output(s)     | `error` (str) when …                          |
|-------------------|--------------------|-----------------------------------------------|
| ApplyEdits        | result, status, graph | apply failed (`status.error`)             |
| CreateFileOnRag   | data               | missing payload, missing output_dir, write failed |
| Debug             | data               | log file write failed (OSError)                |
| ProcessAgent      | edits              | parse_error (fenced JSON present but invalid)   |
| RagUpdate         | data               | run_update raised an exception                 |

**Env-agnostic units with an `error` port:**

| Unit     | Main output | `error` (str) when …        |
|----------|-------------|-----------------------------|
| LLMAgent | action      | LLM client raised (e.g. timeout, connection) |

**Web units with an `error` port:**

| Unit          | Main output | `error` (str) when …                                      |
|---------------|-------------|-----------------------------------------------------------|
| browser       | out         | fetch failed (timeout, connection, HTTP error)            |
| beautifulsoup | out         | missing beautifulsoup4; or CSS selector exception         |
| html_to_text  | out         | missing html2text (fallback: pass-through, error set)     |
| minify_html   | out         | missing minify-html package                               |
| web_search    | out         | missing duckduckgo-search/ddgs; or search API exception   |

Other canonical units (Merge, Prompt, RagSearch, FormatRagPrompt, etc.) do not define an `error` port; they either cannot fail or encode failure inside their main output.

## Creating a new unit

### 1. Create a module (e.g. `units/thermodynamic/pump.py`)

```python
"""Pump unit: flow = setpoint * max_flow."""

import numpy as np
from units.registry import UnitSpec, register_unit


def _pump_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    setpoint = inputs.get("setpoint", 0.0)
    if isinstance(setpoint, (list, np.ndarray)):
        setpoint = float(setpoint[0]) if len(setpoint) else 0.0
    setpoint = float(np.clip(setpoint, 0.0, 1.0))
    max_flow = float(params.get("max_flow", 1.0))
    flow = setpoint * max_flow
    return {"flow": flow}, state


def register_pump() -> None:
    register_unit(UnitSpec(
        type_name="Pump",
        input_ports=[("setpoint", "float")],
        output_ports=[("flow", "float")],
        step_fn=_pump_step,
    ))
```

### 2. Register the unit

- If adding to an existing domain (e.g. thermodynamic): call `register_pump()` from `units/thermodynamic/__init__.py` inside `register_thermodynamic_units()`.
- If creating a new domain: add a new package (e.g. `units/chemical/`) with its own `__init__.py` and `register_chemical_units()`.

## Creating a new unit domain

1. Create `units/<domain>/` (e.g. `units/chemical/`).
2. Add one module per unit (e.g. `reactor.py`, `heater.py`).
3. Add `__init__.py` that aggregates registration:

```python
from units.chemical.reactor import register_reactor
from units.chemical.heater import register_heater

def register_chemical_units() -> None:
    register_reactor()
    register_heater()

__all__ = ["register_chemical_units"]
```

4. Call `register_chemical_units()` when building envs that use that domain (e.g. in `GraphEnv` or `env_factory`).

## Ports and connections

- **Registry → Graph → Executor:** UnitSpec in the registry defines `input_ports` and `output_ports` for each unit type. When a unit is **added** to the graph (graph edit) or the graph is **normalized**, those ports are copied onto the graph **Unit** (`Unit.input_ports`, `Unit.output_ports`). The graph executor uses only the **graph** unit's ports to resolve connections; it does not read the registry at execution time. So: Registry (UnitSpec) → Graph (Unit) → Executor.
- **Ports on the graph are mandatory:** Each `Unit` has `input_ports` and `output_ports` (list of PortSpec; default []). Every `Connection` must reference valid ports (by index or name) from the connected units' **graph** port lists.
- **Input ports**: Named; the executor resolves values from connections using the target unit's `input_ports`. Use `inputs.get("port_name", default)` for optional inputs in your step_fn.
- **Output ports**: Named; downstream units receive values by port name (from the source unit's `output_ports` on the graph).
- **Connection ports**: `Connection` has required `from_port` and `to_port` (default `"0"` when omitted). Values are typically port indices (`"0"`, `"1"`) or port names. The executor maps indices to port names using the **graph** Unit's `output_ports`/`input_ports`. See **docs/PROCESS_GRAPH_TOPOLOGY.md** §5.

## Conventions

1. **Stateless units** (Source, Valve): Return `state` unchanged.
2. **Stateful units** (Tank, Sensor with history): Return updated `new_state`.
3. **Numeric handling**: Use `float()` and handle `list`/`ndarray` for inputs that may come from upstream batching.
4. **Defaults**: Use `params.get("key", default)` and `inputs.get("port", default)` so units work without full wiring.

## Reference: thermodynamic units

| Unit   | Inputs                            | Outputs                    |
|--------|-----------------------------------|----------------------------|
| Source | —                                 | temp, max_flow             |
| Valve  | setpoint                          | flow                       |
| Tank   | hot_flow, cold_flow, dump_flow, hot_temp, cold_temp | temp, volume, volume_ratio |
| Sensor | value                             | measurement, raw           |

See `units/thermodynamic/` for implementations.

## Graph executor integration

The `GraphExecutor` (`runtime/executor.py`) runs units in topological order. It excludes `RLAgent` (and other policy nodes); valves receive `setpoint` from the injected action vector. Ensure your unit’s `type_name` matches `Unit.type` in the process graph and that ports align with connection semantics.
