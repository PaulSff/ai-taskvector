# PyFlowBase-alike nodes (no PyFlow install)

You **do not need to install PyFlow or PyFlowBase**. This folder defines node *semantics* (constant, branch, reroute, etc.) in our format. When you add a unit with one of these types, the system attaches the right code and runs it in our executor or PyFlow adapter.

---

## 1. Ensure units are registered

Canonical and PyFlow units are registered when the app loads canonical units (e.g. GUI, training, or any code that calls `register_canonical_units()`). If you use the Workflow Designer or load a graph that uses these types, registration is already done.

To register manually (e.g. in a script):

```python
from units.canonical import register_canonical_units
register_canonical_units()  # registers function + pyflow catalog types
```

---

## 2. Add a PyFlow-type unit (assistant or edit)

**Option A – Workflow Designer assistant**

In chat, ask to add a unit with a catalog type, e.g.:

- *"Add a constant node with id `c1` and value 42."*
- *"Add a reroute node between sensor and the next node."*
- *"Add a branch node."*

The assistant will emit something like:

```json
{"action": "add_unit", "unit": {"id": "c1", "type": "constant", "controllable": false, "params": {"value": 42}}}
```

On apply, the graph gets the unit **and** the template `code_block` for `constant` is attached automatically. No extra step.

**Option B – Graph edit JSON (no assistant)**

Use the same shape. When `add_unit` is applied with `type` in the PyFlow catalog (`constant`, `branch`, `reroute`, `makeArray`, `makeList`, `dictKeys`), the backend injects the matching code_block for that unit id.

---

## 3. Available PyFlow catalog types

| Type        | Purpose                          | Typical params / inputs      |
|------------|-----------------------------------|------------------------------|
| `constant` | Output a fixed value              | `params.value` (default 0)   |
| `branch`   | condition ? true : false          | inputs: condition, true, false |
| `reroute`  | Pass-through                      | input port `in`              |
| `makeArray`| Collect inputs into a list        | multiple upstream nodes      |
| `makeList` | Same as makeArray                 | multiple upstream nodes      |
| `dictKeys` | Output list of dict keys          | input: dict                  |

Port names and behavior match the catalog in `units/pyflow/__init__.py`. You can add more types there by copying the same pattern (input_ports, output_ports, code_template).

---

## 4. Custom code: canonical `function` unit

For arbitrary logic (any language in the code_block), use the canonical type **`function`**:

1. Add a unit with `type: "function"` and an id.
2. Attach a code_block for that unit id (e.g. via `add_code_block` or in the graph’s `code_blocks`).

The executor and PyFlow adapter run that code_block (state/inputs/params → result). The code_block’s `language` can be anything; execution support depends on the runtime (today: Python in executor and PyFlow adapter).

---

## 5. Run the graph

- **Native (canonical) executor**: Use a graph that has the right topology (e.g. StepDriver, Join, Switch) and include your PyFlow-type units. They run via their code_block in topological order.
- **PyFlow adapter**: Use a graph (from JSON or our format) and run it with the PyFlow adapter as a gym.Env; same code_blocks run there with `state` / `inputs` / `params`.

---

## 6. If you *did* install PyFlowBase

You still don’t need it for **this** project. This catalog is standalone. If you have PyFlow installed elsewhere (e.g. for the PyFlow editor), you can:

- Export a flow from the PyFlow editor to JSON.
- Import that JSON here (format `pyflow`); we normalize it to units + connections + code_blocks.
- Edit and run the graph in our stack; when you export back to PyFlow format, we emit nodes with the same types and code.

No need to run or depend on the PyFlow app or PyFlowBase package in this repo.

---

## 7. Populating the catalog from PyFlowBase (optional)

If you **do** install the PyFlowBase package, you can **list its nodes into `units/pyflow`** so the catalog is filled from the package instead of (or in addition to) hand-written entries.

**How it works**

1. Install PyFlow (e.g. `pip install PyFlow` or from [GitHub](https://github.com/pedroCabrera/PyFlow)); that brings in PyFlowBase.
2. Run the generator script (see below). It introspects `PyFlow.Packages.PyFlowBase.Nodes`, reads node classes, their pin names (input/output), and optionally the `compute()` source.
3. The script writes catalog entries into `units/pyflow/` in our format: type name, `input_ports`, `output_ports`, and a `code_template` (either derived from `compute()` and adapted to our `state`/`inputs`/`params` API, or a placeholder you fill later).
4. The rest of the system is unchanged: `PYFLOW_NODE_CATALOG` in `__init__.py` can be extended or overwritten by the generated data, and `add_unit` with those types still gets the code_block from the catalog.

**Generator script**

Run when PyFlow is installed:

```bash
python scripts/generate_pyflow_catalog.py
```

The script (see `scripts/generate_pyflow_catalog.py`) discovers node modules under `PyFlow.Packages.PyFlowBase.Nodes`, extracts pin layout and optionally `compute()` source, and outputs entries you can paste into `units/pyflow/__init__.py` or merge into `PYFLOW_NODE_CATALOG`. So: **install PyFlowBase → run the script → nodes are listed into `units/pyflow`** (catalog or per-node files). No PyFlow dependency at runtime; the generator is one-off or rare.
