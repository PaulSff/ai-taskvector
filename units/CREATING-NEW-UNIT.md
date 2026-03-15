# Creating a New Unit (Canonical Runtime, Python)

This guide describes how to add a new **canonical** (native) unit in Python: semantics, the units interaction model, and a worked example. For a shorter reference see [README.md](README.md).

---

## 1. Semantics

- **Units** are the building blocks of process graphs. Each unit has an **id**, a **type** (string), and **params** (type-specific config). The graph executor runs units in **topological order** (dependencies first).
- **Unit registry** (`units/registry.py`): maps `type_name` to a **UnitSpec** (ComfyUI-style). The spec defines **input ports**, **output ports**, and either a **step_fn** (Python) or **code_block_driven** (executor runs the graph’s `code_blocks` for that unit).
- **Process graph**: units are nodes; **connections** link an output port of one unit to an input port of another. Data flows over these connections; each port carries a single value (often a dict or primitive).

---

## 2. Units interaction model (canonical)

On the **canonical (native)** runtime, graphs are created in-app or loaded from dict/YAML. The interaction model is:

- **Data flow**: Data is passed from **output ports** to **input ports** via connections. There is no shared global state; only what is sent over connections and what the unit keeps in its **state** (see below).
- **Payloads**: Ports carry **JSON-serialisable** values: dicts (e.g. `{ "action": "search", "query": "...", "max_results": "10" }`), lists, strings, numbers. Observations and agent actions use the same structured payloads.
- **Params**: Each unit’s API and configuration live in **`params`** (the `Unit.params` dict). The executor passes `params` into the unit’s **step_fn** (or into the code_block scope for function/script units). Params are set at edit time (e.g. via `set_params` or when adding the unit) and can be used to tune behaviour without changing the graph structure.
- **Function / script units**: Units of type `"function"` or `"script"` get their logic from the graph’s **`code_blocks`**: one block per unit id, with `id`, `language` (e.g. `"python"`), and `source`. The executor runs that source (see [Function and code_block units](#5-function-and-code_block-units)).

So: **input_port** = data received on that port; **output_port** = data sent from that port; **params** = unit configuration; **code_blocks** = source code for function/script units.

---

## 3. UnitSpec and step_fn

### UnitSpec

```python
from units.registry import UnitSpec, register_unit

UnitSpec(
    type_name="MyUnit",              # Must match Unit.type in the process graph
    input_ports=[("port_a", "Any"), ("port_b", "float")],  # (name, type hint)
    output_ports=[("result", "Any")],
    step_fn=my_step_fn,
    description="Short one-line description for UI and Units Library.",
)
```

- **type_name**: String used in the graph (`Unit.type`).
- **input_ports** / **output_ports**: List of `(name, type)`.
  - Names are used when resolving connections and when building the `inputs` dict for **step_fn**.
  - Types are hints (e.g. `"float"`, `"Any"`); the executor does not enforce them.
- **step_fn**: Callable that runs each step (see below). Required unless **code_block_driven** is True.
- **description**: Optional; used in the Units Library and tooling.

Other optional fields: **controllable**, **role**, **environment_tags**, **runtime_scope**, **code_block_driven**, etc. See `units/registry.py`.

### step_fn signature

```python
def step_fn(
    params: dict,   # Unit.params from the graph
    inputs: dict,   # { port_name: value } from connections (and injected action/initial_inputs when applicable)
    state: dict,    # Unit-local mutable state (persisted between steps)
    dt: float,      # Time step
) -> tuple[dict, dict]:
    """Returns (outputs, new_state)."""
    # outputs: { port_name: value } for each output port
    # new_state: state for the next step (can be the same or updated state)
    return outputs, new_state
```

- **params**: Read-only config for this unit instance.
- **inputs**: Only ports that have an incoming connection (or that are filled by the executor, e.g. agent action) are present. Use `inputs.get("port_name", default)` for optional ports.
- **state**: Unit-local; use for volumes, caches, etc. Return the same or an updated dict.
- **outputs**: Must include a value for every **output port** (keys = port names). Downstream units receive these by port name.

---

## 4. Example: a simple canonical unit

We add a unit **`Echo`** that forwards its input to an output and optionally prefixes it (param).

### 4.1 Create the module

Create `units/canonical/echo/echo.py` (or under an existing package, e.g. `units/canonical/`):

```python
"""Echo unit: forward input to output with optional prefix."""

from typing import Any

from units.registry import UnitSpec, register_unit

ECHO_INPUT_PORTS = [("data", "Any")]
ECHO_OUTPUT_PORTS = [("data", "Any")]


def _echo_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = inputs.get("data")
    prefix = (params.get("prefix") or "").strip()
    if prefix:
        if isinstance(data, str):
            out = prefix + data
        else:
            out = {"prefix": prefix, "data": data}
    else:
        out = data
    return {"data": out}, state


def register_echo() -> None:
    register_unit(UnitSpec(
        type_name="Echo",
        input_ports=ECHO_INPUT_PORTS,
        output_ports=ECHO_OUTPUT_PORTS,
        step_fn=_echo_step,
        description="Forward input to output with optional prefix (param: prefix).",
    ))
```

### 4.2 Register the unit

- If the unit lives under an existing package (e.g. `units/canonical/`): in that package’s `__init__.py`, import `register_echo` and call it from the package’s registration function (e.g. `register_canonical_units()`).
- Ensure that registration runs before the graph is loaded or executed (e.g. when the app or test sets up the env).

### 4.3 Use in a graph

The graph would have a unit like:

```json
{ "id": "my_echo", "type": "Echo", "params": { "prefix": "[Echo] " } }
```

and a connection from some node’s output port to `my_echo`’s `data` input, and from `my_echo`’s `data` output to the next unit.

---

## 5. Function and code_block units

For **custom logic** that is not a fixed step_fn, use a unit of type **`function`** (or a PyFlow-style type that is **code_block_driven**):

1. Add a unit with `type: "function"` and an id.
2. Attach a **code_block** for that unit id (e.g. via the `add_code_block` graph edit), with `id`, `language` (e.g. `"python"`), and `source`.

The executor runs that source in a scope with **`state`**, **`inputs`** (port name → value), **`params`**, and **`node_id`**. The script must produce a single result (e.g. assign to `_result`); that value is written to the unit’s first output port.

- **Canonical (native)**: use **`add_unit`** to add the function unit, then **`add_code_block`** to attach Python (or other) source. Language must match graph origin (e.g. `python` for PyFlow/canonical).
- **code_block_driven** in UnitSpec: set `code_block_driven=True` and omit `step_fn`; the executor will run the graph’s code_block for that unit id instead of calling a step_fn.

See `units/env_agnostic/function/function.py` and `core/normalizer/system_comments.py` (CANONICAL_GRAPH_COMMENT_INFO) for the documented semantics.

---

## 6. Optional error output port

Units that can fail (I/O, parsing, apply) may expose an **`error`** output port (type `str`). When there is no error, emit `None` or `""`. This allows wiring errors to a Debug unit or other handling.

Example: in UnitSpec add `("error", "str")` to `output_ports`, and in step_fn return e.g. `{"data": result, "error": None}` or `{"data": None, "error": "File not found"}`. See `units/canonical/debug/` and [README.md](README.md) for a list of units with an error port.

---

## 7. Registry → Graph → Executor

- **Registry**: UnitSpec defines **input_ports** and **output_ports** for the type. When a unit is added to the graph or the graph is normalised, these ports are copied onto the graph **Unit**.
- **Graph**: Source of truth at run time. Each **Connection** uses `from_port` / `to_port` (index or name) on the graph’s port lists.
- **Executor**: Builds **inputs** from upstream outputs and optional **initial_inputs**; calls **step_fn** (or runs the **code_block** for code_block_driven units); stores **outputs** by port name.

So: define ports and step_fn in the **registry**; the **graph** gets ports from the registry; the **executor** only reads the graph.

---

## 8. Conventions

- **Stateless units**: Return `state` unchanged.
- **Stateful units**: Return updated `new_state` (e.g. tank level, sensor history).
- **Numeric handling**: Use `float()` and handle `list`/`ndarray` for inputs that may be batched or from upstream.
- **Defaults**: Use `params.get("key", default)` and `inputs.get("port", default)` so units work with partial wiring or missing params.

---

## 9. Reference

- **Unit registry**: `units/registry.py` (UnitSpec, register_unit, get_unit_spec).
- **Canonical units**: `units/canonical/` (Aggregate, Prompt, Debug, graph_edit, etc.).
- **Interaction model (canonical)**: `core/normalizer/system_comments.py` — **CANONICAL_GRAPH_COMMENT_INFO**.
- **Executor**: `runtime/executor.py` (topological order, step_fn vs code_block_driven, _build_inputs).
- **Units Library**: `units/canonical/units_library/` (how unit types and descriptions are shown in prompts).
