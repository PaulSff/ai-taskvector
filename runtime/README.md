# Runtime

The runtime runs a **ProcessGraph** in topological order: one forward pass through the graph. Each **process unit** executes in dependency order; inputs come from connections and params. No training loop — just plain graph execution.

---

## Running a workflow

**From the command line:**

```bash
python -m runtime workflow.json
python -m runtime workflow.yaml
python -m runtime path/to/workflow.json --format node_red
```

Outputs are printed as JSON: `{ unit_id: { port_name: value, ... }, ... }`.

**From Python:**

```python
from runtime import run_workflow_file, GraphExecutor
from core.normalizer import load_process_graph_from_file

# Run from file (loads, normalizes, executes once)
outputs = run_workflow_file("workflow.json")

# Or build executor yourself
graph = load_process_graph_from_file("workflow.yaml")
executor = GraphExecutor(graph)
outputs = executor.execute()
```

`execute()` runs the graph once and returns `dict[str, Any]` of unit outputs. If the graph has canonical topology (StepDriver, Join, Switch, StepRewards), that loop is executed as designed: trigger and action are injected, observation is taken from Join, and StepRewards (and other training-loop units) use their **params** for reward formula, max_steps, goal, etc. — i.e. training config is consumed by those units via the graph (params are typically set from training config when the graph is built). For a full RL training loop (many episodes, optimization), use `train.py` with this executor inside the env.

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

Connections to/from **excluded** units (RLAgent, RLOracle, LLMAgent) are not required to have ports; those types may have empty port lists.

### 3. Port indices in range

- For each connection involving a process unit, `from_port` and `to_port` must be valid (integer string or port name) and in range for that unit’s ports.
- **Errors:** out-of-range or invalid `from_port` / `to_port` for the given unit.

Canonical topology (StepDriver, Join, Switch) is **optional**. Graphs without it run as plain dataflow; with it, `step()` / `reset()` can be used for RL (action injection, observation from Join).

---

## Excluded types

Units whose **type** is in **`EXECUTOR_EXCLUDED_TYPES`** are **not** executed and are not required to have ports:

- **RLAgent** (and aliases)
- **RLOracle**
- **LLMAgent** (and aliases)

---

## Data flow: Registry → Graph → Executor

- **Registry** (`units/registry.py`): Defines unit types and port lists (UnitSpec). When units are added to the graph or the graph is normalized, each unit’s `input_ports` and `output_ports` are set **from the registry** onto the graph **Unit**.
- **Graph**: Source of truth for execution. Each **Unit** has `input_ports` and `output_ports` (may be empty for excluded types).
- **Executor**: Reads only the graph. It resolves connection `from_port` / `to_port` to port names using the graph’s port lists. It does not read the registry at execution time.

---

## Execution model

1. **Process units** (registered, not in `EXECUTOR_EXCLUDED_TYPES`) run in **topological order** (dependencies first).
2. For each unit, **inputs** are built from upstream outputs (via connections) and unit **params**. If the graph has canonical topology, action is injected into the Switch and trigger into StepDriver/StepRewards.
3. Each unit runs via its **step_fn** or **code_block** (for code_block_driven units); outputs are stored by port name.
4. **`execute()`**: one forward pass; returns all unit outputs. **`step(dt, action)`** / **`reset()`**: for RL; return `(observation, info)` with `info["outputs"]`.

---

## API summary

| API | Use |
|-----|-----|
| **`run_workflow_file(path, format=None)`** | Load workflow from file, run once, return outputs. |
| **`GraphExecutor(graph).execute()`** | Run graph once; returns `{ unit_id: { port: value, ... } }`. |
| **`GraphExecutor(graph).reset(initial_state=None)`** | Reset state and run one step (RL). |
| **`GraphExecutor(graph).step(dt, action)`** | One step with action (RL). Returns `(observation, info)`. |

---

## Related

- **schemas/process_graph.py** — Unit, Connection, ProcessGraph.
- **units/registry.py** — UnitSpec and port definitions (Registry → Graph).
- **core/normalizer** — `load_process_graph_from_file()` for JSON/YAML and formats (node_red, pyflow, n8n, etc.).
- **docs/PROCESS_GRAPH_TOPOLOGY.md** — Canonical schema and port semantics (optional for plain execution).
