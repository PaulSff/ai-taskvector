# Vision: Constructor + AI Assistants for Process RL (No-Code/Low-Code)

This document captures the target architecture: a **constructor app** where users (and AI assistants) **select environments, compose processes from units, and configure training** via GUI and conversation—minimizing hand-written code.

---

## 1. Core Idea

- **Constructor**: User/AI picks an **environment type** (e.g. thermodynamic: pipelines, valves, tanks, pressure, thermometers) and **builds a process** by selecting and connecting **pre-built units**—no writing environment code.
- **AI assistants**: Help with (1) environment/process design and (2) training setup (goals, rewards, testing)—**not** with writing raw Python/env code.
- **GUI**: Like "Visual Studio for process/RL"—pick environment, draw process, set training goals and rewards, run and inspect training.

---

## 2. Why Constructor Over Pure Code

| Approach | Pros | Cons |
|----------|------|------|
| **Code (current)** | Full flexibility, version control, fits experts | Steep for non-coders; every change = edit code; hard to reuse "temperature + tank + valves" as a building block |
| **Constructor (target)** | Reuse units, validate connections, same UX for many processes; AI suggests "add a tank here" instead of writing `temperature_env.py` | Need a unit library and a runtime that turns a **process graph** into a Gym env |

**Conclusion**: Keep code **under the hood**. Expose **environment types**, **unit library**, **connections**, and **training config** (goals, rewards, algorithm) as **data + GUI**. The system then **generates or selects** the right env and training pipeline.

---

## 3. Two AI Roles (Recommended)

Separating roles keeps each assistant focused and avoids "one AI doing everything."

| Role | Responsibility | Avoids |
|------|-----------------|--------|
| **Environment / Process Assistant** | Suggests or applies: environment type (e.g. thermodynamic), which units to add (tank, valve, pipe, sensor), how to connect them, bounds (pressure, temp). Operates on **process graph** and **env config**, not on Python source. | Writing `temperature_env.py` or editing `step()` |
| **Training Assistant** | Helps with: goals (e.g. "keep pressure in 2–5 bar"), reward design (presets + sliders or structured choices), algorithm (PPO/SAC), hyperparameters, running training, testing policy, and **adjusting rewards** to reach the desired behavior. | Writing `train.py` or raw reward code |

Formal approach for each assistant: see **ENVIRONMENT_PROCESS_ASSISTANT.md** and **TRAINING_ASSISTANT.md** (start with prompt-only + structured output; fine-tune later if needed).

Optional: a single "orchestrator" that routes the user to the right assistant ("I want to add a valve" → Process; "reward is too sparse" → Training).

---

## 4. Data Model (What the Constructor and AI Manipulate)

Everything the user and AI do should map to **declarative structures**, not code strings.

### 4.1 Environment type (preset or template)

- **Thermodynamic (pipelines, valves, tanks, pressure, thermometers, barometers)**
- **Chemical (reactors, separation, streams)** — e.g. IDAES/RL-Energy style
- **Generic control (CSTR, first-order, etc.)** — e.g. PC-Gym style

Each type has a **unit library** and **connection rules** (what can connect to what).

### 4.2 Process = graph of units + connections

Example (conceptual):

```yaml
environment_type: thermodynamic
units:
  - id: hot_source
    type: Source
    params: { temp: 60, max_flow: 1.0 }
  - id: cold_source
    type: Source
    params: { temp: 10, max_flow: 1.0 }
  - id: mixer_tank
    type: Tank
    params: { capacity: 1.0, cooling_rate: 0.01 }
  - id: hot_valve
    type: Valve
    controllable: true
  - id: cold_valve
    type: Valve
    controllable: true
  - id: dump_valve
    type: Valve
    controllable: true
  - id: thermometer
    type: Sensor
    measure: temperature
connections:
  - from: hot_source
    to: hot_valve
  - from: hot_valve
    to: mixer_tank
  - from: cold_source
    to: cold_valve
  - from: cold_valve
    to: mixer_tank
  - from: mixer_tank
    to: dump_valve
  - from: mixer_tank
    to: thermometer
```

**Valve position range and setpoints** are properties of the Valve units (in `params`), not of the env: e.g. `position_range: [0, 1]`, `setpoint`, or `max_flow` per valve. The runtime (env factory + simulator) reads these from the graph to build the action space and bounds.

The **runtime** (your framework + standard libs) turns this into:
- state vector (from sensors and tank state),
- action vector (from controllable valves; bounds from valve units’ `params`),
- physics (mixing, cooling, mass balance),

and wraps it in a **Gymnasium `Env`**. No user-written env code.

### 4.3 Training config (goals, rewards, algorithm)

```yaml
goal:
  type: setpoint
  target_temp: 37.0
  target_volume_ratio: [0.80, 0.85]
rewards:
  preset: temperature_and_volume   # or custom
  weights: { temp_error: -1.0, volume_in_range: 10.0, dumping: -0.1 }
algorithm: PPO
hyperparameters:
  learning_rate: 3e-4
  n_steps: 2048
  batch_size: 64
```

Training assistant suggests changes to **goal** and **rewards** (and maybe hyperparameters), not to Python.

### 4.4 Canonical schema and centralized normalizer

**Do you need a centralized data normalizer?** Yes, once you have **multiple input formats**; optional if you only have one.

| Situation | Need normalizer? |
|-----------|------------------|
| **Single format** — only your own process graph YAML and training config YAML | No. Use that format as canonical; env factory and training script read it directly. |
| **Multiple formats** — Node-RED flow JSON, your YAML graph, IDAES/PC-Gym templates, or different tools with different key names | **Yes.** Centralize mapping in one place so env factory and training pipeline only ever see **one canonical schema**. |

**What it does:**

- **Canonical schema**: Define **one** process graph schema (units, connections, env_type) and **one** training config schema (goal, rewards, algorithm, hyperparameters), e.g. with Pydantic or JSON Schema. All consumers (env factory, training script, assistants) use this.
- **Normalizer (adapter layer)**: Accepts input in various formats (Node-RED flow JSON, external YAML, IDAES/PC-Gym style) and **maps to canonical**. Single entry point, e.g. `normalizer.to_process_graph(raw, format="node_red" | "yaml" | "template")` and `normalizer.to_training_config(raw, format=...)`. Env factory and training script **only** consume canonical output.
- **Benefits**: One place to maintain mapping logic; no branching on format inside env factory or training; validation at the normalizer (invalid data caught before env factory); easy to add new sources (new adapter, same canonical).

**When to add:** Start without it if you have a single format. Introduce the normalizer (or adapter layer) when you add a second source (e.g. Node-RED export, or templates from another tool) so mapping logic stays in one place instead of scattering.

### 4.5 Control loop: our system and the simulator

A clear picture of where **our system** (constructor, trained model, training pipeline) sits relative to the **simulator** (dynamics). We send actions; we receive feedback. The simulator can be **inline** (e.g. `TemperatureControlEnv` in our repo) or **external** (e.g. IDAES); from our system’s point of view both are the same: a black box that runs the process.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  OUR SYSTEM                                                              │
│  ┌──────────────────┐                                                    │
│  │  Trained Model   │  (RL policy: observation → action)                 │
│  │  (e.g. PPO)      │                                                    │
│  └────────┬─────────┘                                                    │
│           │ actions (valve positions, setpoints, etc.)                   │
│           ▼                                                               │
└───────────┼─────────────────────────────────────────────────────────────┘
            │
            │   ─────────────────────────────────────────────────────────►
            │                    SIMULATOR
            │                    (inline: TemperatureControlEnv
            │                     or external: e.g. IDAES)
            │                    Runs dynamics: state, physics, reward
            │   ◄─────────────────────────────────────────────────────────
            │
            │ feedback (observation, reward, terminated, truncated)
            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  OUR SYSTEM                                                              │
│  receives feedback → passes to model (next observation, reward)         │
│  → model outputs next action → … loop                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

**In one line:** Trained model → sends **actions** → Simulator → **feedback** (obs, reward) → (via our system) back to model → … loop.

---

## 5. Standard Libs and Frameworks

| Layer | Purpose | Suggested options |
|-------|---------|--------------------|
| **Process / thermodynamics** | Unit models, flowsheets, physics | **IDAES** (DOE; units, properties, flowsheets). Use as "unit library" and optionally for dynamic sim; your runtime builds Gym state/action from IDAES or from a lighter internal model. |
| **RL env API** | Same as today | **Gymnasium** (observation/action spaces, `reset`/`step`). Your **env factory** builds a Gym env from the process graph + env type. |
| **Pre-built process envs** | Benchmarks, standard examples | **PC-Gym** (CSTR, distillation, etc.), **ChemGymRL** (lab benches). Use as **templates** users can clone and then modify in the constructor. |
| **Training** | Algorithms, logging, eval | **Stable-Baselines3** (PPO, SAC, etc.). Training script is **config-driven** (YAML/JSON from GUI + training config). |
| **GUI** | Constructor + training UI | **Recommended: Node-RED** for process graph editor + connection layer (see §5.1). **Alternative**: React Flow / Rete.js if you prefer a custom web-only editor. **Training UI**: forms (Streamlit/Gradio or React + schema). **Desktop**: embed Node-RED in Electron/Tauri or run locally. |
| **Persistence** | Save/load process and training config | **JSON/YAML** for process graph and training config; Node-RED flows are JSON (export/import). Version with Git if desired. |

**RL-Energy** is a good reference: they use **IDAES** for process and **RL** for design/operation. Your twist is **constructor + GUI + two AI roles** so that building the process and tuning training are **selection and configuration**, not coding.

### 5.1 Recommendation: Node-RED for editor + connection layer

**Use Node-RED for both the process graph editor and the connection layer** instead of developing your own editor.

| Use Node-RED for | Benefit |
|------------------|--------|
| **Process graph editor** | Ready-to-use: palette, canvas, drag-and-drop nodes, connections, JSON flows. No need to build React Flow / Rete.js from scratch. Runs locally (e.g. localhost:1880); can be embedded in a desktop app (Electron/Tauri WebView). |
| **Connection layer** | Same tool for (1) drawing the process and (2) later connecting to real hardware (sensors, valves, PLCs). Node-RED already has MQTT, HTTP, OPC-UA, etc.; used in industrial/IoT. One stack for "design process" and "talk to plant." |

**What you still write (minimal):**

- **Custom nodes** for your unit types: Source, Valve, Tank, Sensor (thermometer, barometer), etc. Each node stores **config only** (type, params); no message logic needed for constructor use.
- **Mapping**: Node-RED flow JSON → your **process graph** schema (units + connections). One-time glue in your Python backend; env factory consumes process graph, not raw Node-RED JSON.
- **Training UI** (goal, rewards, algorithm) can stay separate: forms in Streamlit/Gradio or a second tab; or a custom Node-RED dashboard / HTTP endpoint that serves training config.

**Tradeoff:** Node-RED is message-flow oriented; your process graph is physical (mass/energy). Custom nodes represent "process units" with config; connections mean "physical connection" in your backend. The editor and connection layer are reused; semantics are defined by your mapping and env factory.

---

## 6. GUI Sketch

- **Left**: Environment type selector (e.g. "Thermodynamic – pipelines, valves, tanks, pressure, thermometers").
- **Center**: **Canvas** with nodes (units) and edges (connections). Drag units from a palette; connect inlets/outlets; double-click to set parameters (bounds, setpoints).
- **Right (or tab)**: **Training** — goal (setpoints, ranges), reward preset + sliders/weights, algorithm (PPO/SAC), "Run training" / "Test policy," and later "Adjust rewards" with suggestions from the Training Assistant.
- **Chat panel**: "Add a tank after the mixer," "Make the reward penalize dumping more," "Suggest a reward preset for pressure control" — routed to Process or Training assistant.

No code editor in the main flow; optional "Export config" or "View generated config" for power users.

---

## 7. Migration Path from Current Repo

1. **Keep** `TemperatureControlEnv` and `train.py` as the **reference implementation** and as one **template** the constructor can emulate.
2. **Extract** from `temperature_env.py` an abstract **unit set**: sources (hot/cold), valves (3), tank (1), sensor (thermometer), and a small **physics kernel** (mixing, cooling, mass balance). Map these to the **data model** (units + connections) so that the current env is **one valid process graph**.
3. **Implement** an **env factory**: input = process graph + env type + training goal; output = Gymnasium env (same interface as today). First milestone: same graph as current temperature env → same behavior.
4. **Add** 1–2 standard envs from **PC-Gym** (or IDAES) as **templates** in your app (clone + edit in constructor).
5. **Introduce** training **config file** (YAML/JSON) for goals, rewards, algorithm; make `train.py` read it. Training assistant only edits this config.
6. **Build** minimal GUI: process graph editor (even if only dropdown + list of connections at first), form for training config, "Run training" and "Test" buttons.
7. **Wire** Process Assistant to "add/connect units" and Training Assistant to "change goal/rewards/hyperparameters" via config and graph edits, not code.

---

## 8. Summary

- **Constructor**: User/AI **select environment type** and **compose process from units** (pipelines, valves, tanks, pressure, thermometers, etc.); **no env coding**.
- **Two AI roles**: (1) **Process** — pick env, add/connect units, set bounds; (2) **Training** — goals, rewards, run/test, tune rewards; both work on **data/config**, not code.
- **GUI**: Process canvas + training panel + optional chat; "Visual Studio for process/RL."
- **Stack**: **IDAES** (or similar) for units/physics, **Gymnasium** for env API, **SB3** for training, **config-driven** env factory and training script, **web or desktop** GUI with graph editor.
- **Path**: Refactor current temperature env into **graph + env factory**, add config-driven training, then add GUI and AI assistants that operate on graph and config.

This keeps the successful experiment as a concrete template while moving toward a no-code/low-code app where the AI **selects and composes** environments and **improves training** via goals and rewards, not by writing code.

---

## 9. Reuse vs Build (Don't Reinvent the Bicycle)

To avoid coding everything yourself, **reuse** as much as possible and **write** only the minimal glue.

### Reuse (no need to implement)

| What | Use this | You do |
|------|----------|--------|
| **Process / thermodynamics** | **IDAES** (units, properties, flowsheets), **PC-Gym** (CSTR, distillation, etc.), **ChemGymRL** (lab benches) | Pick env type and template; wire config into your constructor. |
| **RL environment API** | **Gymnasium** (spaces, `reset`/`step`) | Consume it; your env factory *outputs* a Gymnasium env. |
| **RL algorithms** | **Stable-Baselines3** (PPO, SAC, etc.), callbacks, logging | Call `model.learn()`; drive hyperparameters from config. |
| **Reward composition** | Pattern from **qontinui-gym** (RewardBuilder + presets) or similar | Define reward *components* and *presets* in config; one small reward aggregator that reads config. |
| **Process graph editor + connection layer** | **Node-RED** (recommended) | Ready-to-use editor (palette, canvas, JSON flows); runs locally, embeddable in desktop app; same tool for future hardware/IoT connection. Custom nodes for Source, Valve, Tank, Sensor; map flow JSON → process graph in backend. **Alternative**: React Flow / Rete.js if you prefer a custom web-only editor. |
| **Forms / training UI** | **React Hook Form** + JSON Schema, or **Streamlit**/Gradio for a quick prototype | Forms for unit params, goal, rewards, algorithm; produce training config. |
| **Config format** | **YAML** / **JSON** + **Pydantic** or **JSON Schema** | Define schemas once; validate and load in backend. |
| **Pre-built env templates** | Your current `temperature_env`, **PC-Gym** envs, **RL-Energy** examples | Ship as "starter processes" users clone and then modify in the constructor. |

### Write (minimal glue only)

| What | Why you need it | Size |
|------|------------------|------|
| **Env factory** | Turns *process graph + env type* → Gymnasium env (state/action from units, physics from IDAES or your kernel). | One module: load graph, instantiate units, wire connections, expose `reset`/`step`. |
| **Training config loader** | Reads YAML/JSON (goal, rewards, algorithm, hyperparameters) and calls SB3 + your env factory. | One script or small pipeline; same as today's `train.py` but config-driven. |
| **Graph ↔ backend API** | Node-RED exports flow JSON (or POST on "deploy"); backend maps flow → process graph, runs env factory + training. | Thin API: accept Node-RED flow JSON, map to process graph schema, run training. File-based (export flow file) or Node-RED HTTP node → your backend. |
| **Centralized normalizer** (optional until multiple formats) | Maps various input formats (Node-RED flow, YAML graph, IDAES/PC-Gym templates, etc.) → **canonical** process graph and training config. Env factory and training script only consume canonical. | One module (or adapter layer): `to_process_graph(raw, format)`, `to_training_config(raw, format)`; validate with Pydantic/JSON Schema. Add when you have a second input source. |
| **AI assistant integration** | Process Assistant edits graph/config; Training Assistant edits training config; optional orchestrator. | Prompts + API that apply edits to graph/config (no code generation). |

### What you do *not* write

- **Physics engines** — use IDAES or your existing temperature physics.
- **RL algorithms** — use SB3.
- **Graph rendering / node editor** — use **Node-RED** (recommended) or React Flow / Rete.js.
- **Generic form components** — use a form library + schema.
- **Reward math from scratch** — use composable components + presets (pattern from qontinui-gym).

**Bottom line:** You avoid reinventing the bicycle by **reusing** env libs (IDAES, PC-Gym, your env), Gymnasium, SB3, **Node-RED** for editor + connection layer, and form libs. You **only** write: env factory, config-driven training pipeline, **Node-RED flow JSON → process graph** mapping, custom Node-RED nodes for your unit types, and AI assistant glue that edits config.

---

## 10. Model-operator (speaking + control)

Sometimes you need a **model-operator**: an AI that (1) **operates the process** it was trained for (control policy) and (2) **speaks** (multilingual, explanation, dialogue with users). This is distinct from the Process Assistant and Training Assistant (which help *design* the process and *train* the agent).

### 10.1 Recommended strategy: two models that interact

**Use two models that interact**, rather than one model that does both:

| Model | Role | Input | Output |
|-------|------|-------|--------|
| **RL operator** ("the operator") | Low-level control: observation → action (valves, setpoints, etc.). Trained with PPO/SAC on the process env. | Observation (temp, flow, volume, pressure, etc.); optionally **goal** (e.g. target temp) if goal-conditioned. | Action (valve adjustments, etc.). No language. |
| **LLM** (e.g. Ollama, or a fork/fine-tuned model) | Speaking: dialogue, explanation, multilingual. Interprets user intent and sets **goals/commands** for the operator. | User message + **current process state** (and optionally alarms, history). | Natural language response; optionally **goal/command** (e.g. "set temperature to 37°C") passed to the RL operator or to a setpoint interface. |

**Interaction:** User talks to the LLM. The LLM (1) responds in natural language (any language), (2) when the user asks for control or the LLM decides to act, it outputs a **goal or high-level command** (e.g. target temperature, "reduce flow"). A small **operator middleware** passes that goal to the RL policy (if goal-conditioned) or to a setpoint layer; the RL policy continues to run the closed loop (observation → action). So: **LLM = front-end (speech, explanation, multilingual); RL = back-end (low-level control)**. They interact via a clear interface: state → LLM (for dialogue); state (+ goal) → RL → action.

**Why two models (preferred):**

- **RL is the right tool for control**: sample-efficient, low latency, reliable for continuous control. LLMs are not trained for high-frequency, precise control loops.
- **LLMs are the right tool for language**: multilingual, explanation, dialogue. Training one model to do both control and language is harder and less reliable for safety-critical control.
- **Separation of concerns**: You can swap or upgrade the LLM (Ollama, cloud, fine-tuned fork) without retraining the control policy. The RL operator stays small and deterministic for control; the LLM handles all variability in language and user intent.
- **Goal-conditioned RL**: If the RL policy is goal-conditioned (goal = target temp, pressure, etc.), the LLM only needs to **set the goal** from natural language ("keep temperature at 37" → goal = 37). The RL policy does the rest. No need for the LLM to output raw actions.

### 10.2 What you write (operator middleware)

| Piece | What it does |
|-------|------------------|
| **Operator middleware** | (1) Feeds **current state** (and optional history) to the LLM for dialogue. (2) Receives **goal/command** from the LLM (structured output or parsed intent). (3) Passes goal to the RL policy (if goal-conditioned) or to a setpoint/override layer. (4) Runs the RL policy in a loop: observation → action → process. So: one process connects "user ↔ LLM" and "LLM ↔ RL operator." |
| **Structured output or intent parsing** | LLM output must include an optional **goal/command** (e.g. JSON: `{"goal": {"temperature": 37}}` or intent "set_temp_37"). Middleware parses this and updates the goal for the RL policy. |

### 10.3 Alternative: one model (not recommended)

A **single LLM** fine-tuned or prompted to output both (1) natural language and (2) control actions (e.g. action vector or discrete commands) is possible but **not recommended** for closed-loop control: LLMs are less sample-efficient than RL for control, harder to make safe and deterministic, and add latency/cost to the control loop. Keeping **RL for control** and **LLM for language + goal setting** is the preferred strategy.

### 10.4 Reuse for the model-operator

| What | Use this |
|------|----------|
| **Speaking / dialogue** | **Ollama** (local LLM, multilingual), or a fine-tuned fork, or a cloud LLM. |
| **Control** | Your **trained RL policy** (SB3 PPO/SAC, etc.) — the "operator" trained on the process env. |
| **Goal-conditioned policy** | Train the RL operator with a **goal** in the observation (e.g. target_temp); the LLM only sets that goal. |

**Summary:** Prefer **two models**: LLM (Ollama or fork) for speaking and setting goals/commands; RL operator for process control. They interact via **operator middleware** (state → LLM, goal/command from LLM → RL). One model doing both is possible but not recommended for reliable, low-latency control.

### 10.5 Current repo: reference implementation

This repo **already uses** the two-model pattern for the temperature use case:

- **Ollama** (local LLM) for natural-language dialogue: `chat_with_local_ai.py` — user talks to the assistant (set target temp, run test, status, etc.); Ollama handles multilingual, explanation, intent.
- **RL operator**: PPO model (trained on `TemperatureControlEnv`) for low-level control; when the user says "run a test" or similar, the chat runs the env and the RL policy (`model.predict`) in a loop.

So: **Ollama + temperature control RL operator** is the current model-operator setup. The "operator middleware" is the logic in `chat_with_local_ai.py` that (1) feeds state/context to Ollama, (2) parses user intent (target temp, run test, status), and (3) invokes the RL policy and env when running a control test. This is the reference implementation for §10.

---

## 11. Generalization to Other Domains (robotics, machine vision, etc.)

The same **concept** applies to any other environment type: robotics, machine vision, games, etc. You don't change the architecture; you **pick a new environment type** and **provide the right building blocks + train the operator** (and optionally adapt the assistants).

### 11.1 What stays the same

- **Constructor** — User/AI picks env type and composes from units (or building blocks); no env coding.
- **Two assistants** — Process Assistant (design), Training Assistant (goals, rewards); they operate on **config/graph**, not code.
- **Model-operator** — LLM for speaking + RL operator for control; operator middleware connects them.
- **Stack** — Gymnasium env API, SB3 (or other RL lib), config-driven training, GUI (e.g. Node-RED or custom).

### 11.2 What changes per domain

| Domain | Environment type | "Units" / building blocks | Env factory | RL operator |
|--------|-------------------|---------------------------|-------------|-------------|
| **Process / thermodynamic** (current) | Thermodynamic, chemical | Source, Valve, Tank, Sensor, pipe connections | Process graph → Gym env (mixing, cooling, mass balance) | Train PPO/SAC on that env (e.g. temperature control). |
| **Robotics** | Robot + task (e.g. pick-place, assembly) | Robot config (joints, gripper), task template, sim (MuJoCo, Isaac Gym) | Robot + task config → Gym env (sim) | Train PPO/SAC (or similar) on that robotics env. |
| **Machine vision** | Vision pipeline or vision-based control | Cameras, models (detection/segmentation), preprocessing, control task | Pipeline + task config → Gym env (e.g. observation = image + state, action = control) | Train RL (or imitation) on that vision env. |
| **Games / other** | Game or custom sim | Level/task config, game engine or sim | Config → Gym env | Train agent on that env. |

So for each new domain you:

1. **Pick (or add) an environment type** — e.g. "Robotics," "Machine vision," with a **unit library** and **connection rules** for that domain (e.g. robot + task, camera + model + task).
2. **Implement (or reuse) an env factory** — Input = graph/config for that domain; output = Gymnasium env. You can reuse standard sims (MuJoCo, Isaac Gym, Atari, etc.) and wrap them; the "constructor" just configures which robot, which task, which camera, etc.
3. **Train the RL operator** — For that new env type you **train a new RL policy** (PPO, SAC, etc.) on the env produced by the env factory. The operator that "does the job" (control valves, move robot, drive from vision) is always **trained** on the specific env.
4. **Adapt the assistants (optional)** — Process Assistant and Training Assistant can stay **prompt-based** (e.g. "you are helping design a robotics task") or be **fine-tuned** on the new domain so they suggest the right units and rewards (e.g. "add a gripper," "reward for successful pick"). They don't need to be "trained" in the RL sense—they're LLMs (or rules) that edit config; you only need them to know the vocabulary of the new domain.

### 11.3 Summary: "Pick new env type and train the assistants?"

Your understanding is **right in spirit**, with one nuance:

- **Pick new environment type** — Yes. You add (or select) an env type (robotics, vision, etc.) with its unit library and env factory.
- **Train the assistants** — Partially. The **Process and Training assistants** usually only need **adaptation** (better prompts or fine-tuning) so they know the new domain (robotics, vision). They don't "run" the env; they edit config. The part you **must** train is the **RL operator** for the new environment—that's the agent that performs the task (control, manipulation, vision-based control). So: **pick new env type → provide env factory + unit library → train the RL operator on that env → optionally adapt the assistants (prompts/fine-tune) for the new domain.**

**Bottom line:** The concept is **domain-agnostic**. For robotics, machine vision, or any other env type: same constructor + assistants + model-operator architecture; you only need the right **env type**, **building blocks**, **env factory**, and a **trained RL operator** for that env, plus optional adaptation of the Process/Training assistants for the new domain.
