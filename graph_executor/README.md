# Graph executor

The graph executor runs a **ProcessGraph** in topological order: it executes **process units** (Source, Valve, Tank, Sensor, etc.), skips policy nodes (RLAgent, RLOracle, LLMAgent), injects the action vector into **action targets**, and builds the **observation** vector from **observation sources**. It uses only the **graph** for ports and connections (**Registry → Graph → Executor**).

---

## Requirements (validation)

The executor validates the graph in **`__init__`**. If any requirement is violated, it raises **`ValueError`** with a clear message. There are no silent fallbacks.

### 1. Connections mandatory

- If the graph has at least one **process unit** (a unit whose type is in the registry and not in `EXECUTOR_EXCLUDED_TYPES`), then **`graph.connections` must be non-empty**.
- **Error:** `"Process graph has process units but no connections. Connections are mandatory for execution."`

### 2. Ports on process units used in connections

- Every connection whose **source** is a process unit: that unit must have **`output_ports`** (non-empty list on the graph).
- Every connection whose **target** is a process unit: that unit must have **`input_ports`** (non-empty list on the graph).
- **Errors:**  
  - `"Connection from unit '<id>' has no output_ports; every process unit used as a connection source must have output_ports on the graph."`  
  - `"Connection to unit '<id>' has no input_ports; every process unit used as a connection target must have input_ports on the graph."`

Connections to/from **excluded** units (RLAgent, RLOracle, LLMAgent) are not required to have ports on those units; excluded types may have empty port lists.

### 3. Port indices in range

- For each connection involving a **process** unit, `from_port` and `to_port` must be **integer strings** (e.g. `"0"`, `"1"`) and **in range** for that unit’s `output_ports` / `input_ports` length.
- **Errors:**  
  - `"Connection from_port '<value>' out of range for unit '<id>' (has N output_ports)."`  
  - `"Connection to_port '<value>' out of range for unit '<id>' (has N input_ports)."`  
  - `"Connection from_port must be a valid index for unit '<id>', got '<value>'."` (non-integer)

### 4. Observation sources must have output_ports

- Every unit that is an **observation source** (wired **into** the agent, i.e. in `get_agent_observation_input_ids(graph)`) must have at least one **`output_ports`** entry on the graph.
- **Error:** `"Observation source unit '<id>' has no output_ports; observation sources must have at least one output port on the graph."`

### 5. Action targets must have input_ports

- Every unit that is an **action target** (wired **from** the agent, i.e. in `get_agent_action_output_ids(graph)`) must have at least one **`input_ports`** entry on the graph.
- **Error:** `"Action target unit '<id>' has no input_ports; action targets must have at least one input port on the graph."`

---

## Excluded types (no execution, no port requirement)

Units whose **type** is in **`EXECUTOR_EXCLUDED_TYPES`** are **not** executed and are **not** required to have ports for validation. Excluded types are:

- **RLAgent** (and aliases)
- **RLOracle**
- **LLMAgent** (and aliases)

They may have empty `input_ports` and `output_ports` on the graph. Only **process units** (registered, non-excluded) and the roles **observation source** / **action target** are validated for ports.

---

## Data flow: Registry → Graph → Executor

- **Registry** (`units/registry.py`): Defines unit types and their port lists (UnitSpec). When units are **added** to the graph (e.g. via `apply_graph_edit`) or the graph is **normalized**, each unit’s `input_ports` and `output_ports` are set **from the registry** onto the graph **Unit**.
- **Graph**: The single source of truth for execution. Each **Unit** has mandatory `input_ports` and `output_ports` (lists of PortSpec; may be empty for excluded types).
- **Executor**: Reads **only the graph**. It resolves connection `from_port` / `to_port` (indices or names) to port **names** using `Unit.output_ports` and `Unit.input_ports`. It does **not** read the registry at execution time.

So: ports are mandatory on the graph for process units and for observation/action roles; the executor assumes the graph is already valid and throws at construction time if not.

---

## Execution model

1. **Process units** are those with a type in the registry and not in `EXECUTOR_EXCLUDED_TYPES`. They are run in **topological order** (dependencies first), using **connections** between process units only for ordering and data flow.
2. For each process unit, **inputs** are built from:
   - Values from **upstream** units (via connections), using the graph unit’s **input_ports** / **output_ports** to map port indices to port names.
   - **Action injection**: if the unit is an action target, its first input port receives the corresponding component of the `action` vector.
3. Each unit’s **step_fn** (from the registry) is called with `(params, inputs, state, dt)`; its **outputs** are stored by port name.
4. **Observation**: the observation vector is built from the **first output port** of each **observation source** unit (units that feed into the agent), in a stable order.

**API:**

- **`step(dt, action)`** — One simulation step. Returns `(observation: list[float], info: dict)` with `info["outputs"]` = all unit outputs by id and port.
- **`reset(initial_state=None)`** — Reset unit states (and optionally set initial state for tanks etc.), then one step with zero action. Returns same shape as `step`.

---

## Related

- **schemas/process_graph.py** — Unit, Connection, ProcessGraph; Unit has mandatory `input_ports` / `output_ports`.
- **units/registry.py** — UnitSpec and port definitions (Registry → Graph).
- **docs/PROCESS_GRAPH_TOPOLOGY.md** — Canonical schema and port semantics.
- **graph_executor/executor.py** — Implementation and `_validate_graph_for_execution`.
