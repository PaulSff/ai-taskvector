# Runtime

The runtime runs a **ProcessGraph** in topological order: one forward pass through the graph. Each **process unit** executes in dependency order; inputs come from connections, params, and optional **initial_inputs** (e.g. for Inject units). No training loop — plain graph execution.

---

## Running a workflow

**From the command line (all parameters in the run command; no hardcoding):**

```bash
# Run with no injected inputs
python -m runtime workflow.json

# Run with initial_inputs (JSON string)
python -m runtime workflow.json --format dict --initial-inputs '{"inject_user_message":{"data":"hi"},"inject_graph":{"data":{"units":[],"connections":[]}}}'

# Run with initial_inputs and unit param overrides from files
python -m runtime workflow.json --initial-inputs @inputs.json --unit-params @unit_params.json

# Write outputs to a file
python -m runtime workflow.json --initial-inputs @inputs.json --output out.json
```

| Option | Description |
|--------|-------------|
| `workflow` | Path to workflow JSON or YAML (positional). |
| `--initial-inputs` | JSON `{ unit_id: { port_name: value } }` for units with no upstream (e.g. Inject). Inline JSON or `@path/to/file.json`. |
| `--unit-params` | JSON `{ unit_id: { param_name: value } }` to merge into each unit’s params. Inline or `@path`. |
| `--format` | `dict` \| `yaml` \| `node_red` \| `pyflow` \| `n8n`. Inferred from suffix if omitted. |
| `--output` | Write outputs JSON to this file (default: print to stdout). |

Outputs are JSON: `{ unit_id: { port_name: value, ... }, ... }`.

**From Python:**

```python
from runtime import run_workflow, run_workflow_file, GraphExecutor
from core.normalizer import load_process_graph_from_file

# Generic run: supply everything via arguments (no hardcoded unit ids)
outputs = run_workflow(
    "workflow.json",
    initial_inputs={
        "inject_user_message": {"data": "hi"},
        "inject_graph": {"data": {"units": [], "connections": []}},
    },
    unit_param_overrides={"llm_agent": {"model_name": "llama3.2"}},
    format="dict",
)

# Simple run with no inputs (backward-compatible)
outputs = run_workflow_file("workflow.json")

# Or build executor yourself
graph = load_process_graph_from_file("workflow.yaml")
executor = GraphExecutor(graph)
outputs = executor.execute(initial_inputs={"inject_1": {"data": "value"}})
```

`run_workflow()` registers env-agnostic units, loads the graph, applies `unit_param_overrides` by unit id, runs with `initial_inputs`, and returns unit outputs. Use it when the workflow has Inject (or similar) units that need data at start.

---

## Requirements (validation)

The executor validates the graph in **`__init__`**. If any requirement is violated, it raises **`ValueError`**.

### 1. Connections mandatory

- If the graph has at least one **process unit** (type in registry, not in `EXECUTOR_EXCLUDED_TYPES`), **`graph.connections`** must be non-empty.
- **Error:** `"Process graph has process units but no connections. Connections are mandatory for execution."`

### 2. Ports on process units used in connections

- Every connection **from** a process unit: that unit must have **`output_ports`** on the graph.
- Every connection **to** a process unit: that unit must have **`input_ports`** on the graph.
- **Errors:**  
  - `"Connection from unit '<id>' has no output_ports; ..."`  
  - `"Connection to unit '<id>' has no input_ports; ..."`

Connections to/from **excluded** units (RLAgent, RLOracle, etc.) are not required to have ports; those types may have empty port lists.

### 3. Port indices in range

- For each connection involving a process unit, `from_port` and `to_port` must be valid (integer string or port name) and in range for that unit’s ports.
- **Errors:** out-of-range or invalid `from_port` / `to_port` for the given unit.

Canonical topology (StepDriver, Join, Switch) is **optional**. Graphs without it run as plain dataflow; with it, `step()` / `reset()` can be used for RL (action injection, observation from Join).

---

## Excluded types

Units whose **type** is in **`EXECUTOR_EXCLUDED_TYPES`** (see `core/schemas/agent_node.py`) are **not** executed and are not required to have ports. Other unit types (e.g. LLMAgent, Inject, Merge, ApplyEdits) are executed when present in the graph.

---

## Data flow: Registry → Graph → Executor

- **Registry** (`units/registry.py`): Defines unit types and port lists (UnitSpec). When the graph is normalized, each unit’s `input_ports` and `output_ports` are set from the registry onto the graph **Unit**.
- **Graph**: Source of truth for execution. Each **Unit** has `input_ports` and `output_ports` (may be empty for excluded types).
- **Executor**: Reads only the graph. It resolves connection `from_port` / `to_port` to port names using the graph’s port lists. **initial_inputs** are merged into inputs for units with no upstream (e.g. Inject).

---

## Execution model

1. **Process units** (registered, not in `EXECUTOR_EXCLUDED_TYPES`) run in **topological order** (dependencies first).
2. For each unit, **inputs** are built from upstream outputs (via connections), unit **params**, and **initial_inputs** for that unit id (if any).
3. Each unit runs via its **step_fn** or **code_block** (for code_block_driven units); outputs are stored by port name.
4. **`execute(initial_inputs=None)`**: one forward pass; returns all unit outputs. **`step(dt, action)`** / **`reset()`**: for RL; return `(observation, info)` with `info["outputs"]`.

---

## API summary

| API | Use |
|-----|-----|
| **`run_workflow(path, initial_inputs=None, unit_param_overrides=None, format=None)`** | Load workflow, optionally override unit params, run with initial_inputs, return outputs. No hardcoded unit ids. |
| **`run_workflow_file(path, format=None)`** | Load workflow, run once with no inputs, return outputs. Backward-compatible wrapper. |
| **`GraphExecutor(graph).execute(initial_inputs=None)`** | Run graph once; returns `{ unit_id: { port: value, ... } }`. |
| **`GraphExecutor(graph).reset(initial_state=None)`** | Reset state and run one step (RL). |
| **`GraphExecutor(graph).step(dt, action)`** | One step with action (RL). Returns `(observation, info)`. |

---

## Related

- **core/schemas/process_graph.py** — Unit, Connection, ProcessGraph.
- **units/registry.py** — UnitSpec and port definitions (Registry → Graph).
- **core/normalizer** — `load_process_graph_from_file()` for JSON/YAML and formats (node_red, pyflow, n8n, etc.).
- **assistants/runner.py** — Builds initial_inputs for the assistant workflow and calls `run_workflow()`.
