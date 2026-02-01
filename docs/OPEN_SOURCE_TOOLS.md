# Open Source Tools: Process Visualization & Simulators

Short reference for **process visualization** and **simulators** before implementing GUI or a graph-driven visualizer. Aligns with VISION.md (§5, §6) and the "What's left" section in IMPLEMENTATION_PLAN.md.

---

## Visualization vs simulation (dynamics): both matter

Training an AI agent (e.g. RL) requires **dynamic simulation**, not only visualization:

- **Simulation / dynamics** = how the process **evolves over time**: state transitions, physics (ODEs, mass balance, mixing, cooling, etc.). The agent interacts with this via `reset()` and `step(action)`; observations and rewards come from the simulated dynamics. **Required for training.**
- **Visualization** = how we **display** the process (flowsheet, graphs, live plots, 3D view). For humans; **optional** for training (you can train headless with `render_mode=None`).

So: the **simulator** (dynamics) is what the agent "lives in"; the **visualizer** is what we use to inspect or debug. Both are relevant: dynamics for learning, visualization for understanding and tuning.

**Inline vs external simulator — same interface from our system.** We can use either:

- **Inline (custom) simulator** — e.g. `TemperatureControlEnv`: dynamics implemented in our repo, wrapped as a Gymnasium env.
- **External simulator** — e.g. IDAES: dynamics run by an external library; we wrap it (or a thin adapter) as a Gymnasium env so the agent still sees `reset()` / `step(action)`.

From the **system’s point of view** (constructor, RL agent, training pipeline), **both are external**: we only **send actions** (valve positions, setpoints, etc.) into the simulator and **receive feedback** (observations, rewards) from it. We do not implement the physics; we interface with whatever runs the dynamics. So the simulator (inline or external) is the black box that runs the process; our system is the client that pushes on controls and gets feedback.

---

## Principle: Visualization is environment-type dependent

**Process visualization strongly depends on the environment type.** There is no single “best” visualizer for all types: thermodynamic flows need a flowsheet/PFD-style viewer; robotics needs a robot/scene viewer; generic control might need only a topology graph. The constructor should **choose the visualizer per environment type** (and optionally fall back to a generic topology view when no type-specific viewer is available).

---

## 1. Visualization by environment type

| Environment type | Best-fit visualizer | Rationale |
|------------------|----------------------|-----------|
| **thermodynamic** | **IDAES Flowsheet Visualizer (IFV)** | Flowsheets, streams, units (Source, Valve, Tank, Sensor), stream table, export SVG. Native to process/thermo. Requires IDAES flowsheet model or a bridge from our canonical ProcessGraph. |
| **chemical** | **IDAES Flowsheet Visualizer (IFV)** | Same as thermodynamic: reactors, separation, streams; IDAES is the reference stack for chemical PSE. |
| **generic_control** | **NetworkX + Matplotlib** or **Graphviz** | No domain-specific flowsheet; a generic graph (units = nodes, connections = edges) is enough. Topology-only or with simple state overlay. |
| **robotics** (future) | **Sim viewer** (MuJoCo, Isaac Gym, etc.) | Process “graph” is robot + task config; visualization is the 3D sim view, not a flowsheet. |
| **machine_vision** (future) | **Pipeline/canvas** or **generic graph** | Cameras, models, tasks; either a custom pipeline UI or a generic graph view. |

**Fallback:** For any type, we can offer a **generic topology view** (e.g. NetworkX/Graphviz from our canonical ProcessGraph) so that every environment has at least a graph-only visualization when a type-specific viewer is not yet integrated.

---

## 2. Gymnasium envs: built-in visualizers (robotics, games, etc.)

Gymnasium environments for **robotics**, **games**, and **classic control** typically **do** ship with visualizers: they implement the **standard Gymnasium render API** and plug in the appropriate backend.

**Standard API**

- **`render_mode`** (set at env creation): `None` (no render), `"human"` (window), `"rgb_array"` (pixels), `"ansi"` (text).
- **`metadata["render_modes"]`** and **`metadata["render_fps"]`** declare what the env supports.
- **`render()`** returns a frame (e.g. RGB array) or `None` depending on mode; for `"human"`, rendering often happens inside `step()` and `render()` may return `None`.

**How common env types implement it**

| Env type | Backend | What the user sees |
|----------|---------|--------------------|
| **MuJoCo** (Ant, Hopper, Humanoid, etc.) | MuJoCo OpenGL renderer | 3D scene in a window; optional depth/segmentation. |
| **Gymnasium-Robotics** (Fetch, Hand, etc.) | MuJoCo (same as above) | Robot + scene; `render_mode="human"` or `"rgb_array"`. |
| **Atari** | Game emulator | Game screen (pixels). |
| **Classic control** (CartPole, Pendulum, etc.) | Pygame (or similar) | 2D animation in a window. |
| **Box2D** (Lunar Lander, Car Racing) | Box2D + rendering | 2D physics view. |

So **visualization is part of the env**: each env implements `render()` using its sim/game backend (MuJoCo, Pygame, emulator, etc.). There is no separate “Gymnasium visualizer app”; the env *is* the visualizer for its domain.

**Implication for us**

- **Our thermodynamic env** already follows this: `TemperatureControlEnv` has `metadata = {"render_modes": ["human"], "render_fps": 4}` and a `render()` (e.g. text or the test_model-style schematic). So we already have a **built-in visualizer** for the current thermo env; it’s just not graph-driven yet.
- **If we add robotics (or other Gymnasium envs):** Those envs will bring their **own** visualizer (MuJoCo window, etc.). We don’t need to build a separate robotics viewer; we use `render_mode="human"` or `"rgb_array"` on the env. Our “process visualization” for robotics would be **that** (the sim view), plus optionally a generic topology view of the robot/task config.
- **Process graph vs. env render:** The **process graph** (units, connections) is the *design* view (e.g. IDAES IFV for thermo, NetworkX for generic). The **env render** is the *runtime* view (what the agent sees: 3D sim, game screen, or our tank schematic). Both can coexist: design view for editing/inspection, env render for training/testing.

---

## 3. Process / flowsheet visualization tools (reference)

| Tool | Best for env type | Stack | Notes |
|------|--------------------|--------|--------|
| **IDAES Flowsheet Visualizer (IFV)** | thermodynamic, chemical | Python (IDAES), Jupyter or script | `m.fs.visualize("My Flowsheet", save_as="my_flowsheet.json")`; view/rearrange diagram, stream table, export SVG; read-only. Requires IDAES flowsheet (or bridge from our ProcessGraph). |
| **React Flow** | Editor (any type) | JavaScript/React, npm | Generic node-based **editor**; map ProcessGraph ↔ React Flow; good for custom web process editing. Not a domain-specific renderer. |
| **Node-RED** | Editor (any type) | Node.js, browser UI | We have Node-RED → canonical adapter. Use for **editing**; custom nodes per unit type; not a schematic renderer. |
| **Chemical-PFD (FOSSEE)** | thermodynamic, chemical | Python, GPL-3.0 | PFD design in Python; check if it can consume our graph. Alternative to IDAES for pure visualization. |
| **NetworkX + Matplotlib** | generic_control, fallback | Python (nx, plt) | Generic graph: ProcessGraph → DiGraph → draw. Topology only; no process icons. |
| **Graphviz (DOT)** | generic_control, fallback | DOT, Python `graphviz` | Static topology: ProcessGraph → DOT → PNG/SVG. |

---

## 4. Process simulators (physics / dynamics)

| Tool | Type | Stack | Fit for us |
|------|------|--------|------------|
| **IDAES (IDAES-PSE)** | Process systems engineering | Python, DOE/Sandia/etc. | **Reference** in VISION: unit models, flowsheets, thermodynamics. Heavier; use as “unit library” and optionally for dynamics. Our env factory could later wrap IDAES-built flowsheets. |
| **PC-Gym** | RL benchmarks for process control | Python, Gym API, Imperial College | **Templates**: CSTR, distillation, etc. `pip install pcgym`. Good for comparing RL vs NMPC and for cloning env ideas. **Does not ship with a Gym-style live visualizer** (no `render_mode="human"` / `render()` window); visualization is **post-processing** (example notebooks, policy evaluation plots). |
| **SMPL** | Industrial manufacturing / process control RL | Python, Gym, arxiv 2206.08851 | **Templates**: Beer fermentation, CSTR, penicillin, MAb, etc. Gym-compatible; useful as reference or for benchmarking. |
| **DWSIM** | Chemical process simulator | .NET, GUI, automation API | **Not recommended** here: .NET + COM/DLL; VISION had moved away. Rich thermodynamics and PFD; Python automation exists but adds stack complexity. |
| **Our TemperatureControlEnv** | In-house thermodynamic demo | Python, Gymnasium | **Current**: mixing tank, valves, sensor; we already have env factory + config-driven training. No separate “simulator” product; it *is* the simulator for our use case. |

**Summary**

- **Today:** Our own env (temperature mixing) + env factory; no external simulator required.  
- **Later:** IDAES for richer thermodynamics/units if we need it; PC-Gym / SMPL for templates and benchmarking, not as the main “process visualization” tool.

---

## 5. Suggested order before implementation

1. **Per-type visualizer strategy**  
   - **Thermodynamic / chemical:** Integrate **IDAES Flowsheet Visualizer (IFV)** when we have (or bridge to) an IDAES flowsheet; until then, use a **generic topology** view (NetworkX/Graphviz) or our current test_model-style viewer.  
   - **Generic control:** Use **NetworkX + Matplotlib** or **Graphviz** for graph-only visualization from our canonical ProcessGraph.  
   - **Future types (robotics, vision):** Use the appropriate sim/viewer (MuJoCo, pipeline UI, etc.); keep a **fallback** generic graph view for any type.

2. **Generic fallback (fast win)**  
   - Implement a **generic topology visualizer**: ProcessGraph (any env type) → NetworkX/Graphviz → static diagram or small window. Ensures every env has at least a graph view.

3. **Live process view (per type)**  
   - **Thermodynamic:** Extend test_model-style viewer (layout from ProcessGraph, state from env); later, drive IDAES IFV from live state if we use IDAES.  
   - **Generic control:** Overlay state on the generic graph view if needed.

4. **GUI (editor + training panel)**  
   - **Process editor:** Node-RED or React Flow; **visualization** in the GUI should **dispatch by environment type** (e.g. “thermodynamic” → IFV or our thermo viewer; “generic_control” → generic graph).

---

## 6. Links (as of writing)

- **Gymnasium:** https://gymnasium.farama.org (Env API, render modes: human, rgb_array, ansi)  
- **Gymnasium-Robotics:** https://robotics.farama.org (Fetch, Hand, etc.; MuJoCo render)  
- **MuJoCo (Gymnasium):** https://gymnasium.farama.org/environments/mujoco/  
- IDAES: https://idaes.org , https://github.com/IDAES/idaes-pse  
- IDAES Flowsheet Visualizer: https://idaes-pse.readthedocs.io/en/1.9.0/user_guide/vis/index.html  
- PC-Gym: https://maximilianb2.github.io/pc-gym/ , https://github.com/MaximilianB2/pc-gym  
- SMPL: https://smpl-env.readthedocs.io/ , https://github.com/Mohan-Zhang-u/smpl  
- React Flow: https://reactflow.dev  
- Node-RED: https://nodered.org  
- Chemical-PFD (FOSSEE): https://github.com/FOSSEE/Chemical-PFD  
- NetworkX drawing: https://networkx.org/documentation/stable/reference/drawing.html  
- Graphviz (Python): https://graphviz.readthedocs.io/
