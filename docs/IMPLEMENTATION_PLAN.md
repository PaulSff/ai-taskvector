# Implementation Plan

This document outlines the implementation plan for the constructor + AI assistants vision. **Data normalizer is core**: all inputs (Node-RED, YAML, templates, assistants) flow through the normalizer to **canonical** process graph and training config so the rest of the stack stays consistent.

---

## Vision vs implementation (assessment)

Mapping **VISION.md** to current status: where we are and what’s left.

| VISION (§) | Goal | Status |
|------------|------|--------|
| **§1–2 Core idea** | Constructor: env type + units + connections, no env code. AI assistants for design + training. GUI “Visual Studio for process/RL.” | **Backend done**; minimal GUI in place (load/paste/upload, React Flow view, training + assistant). No full canvas editor (drag-from-palette, connect in-app). |
| **§3 Two AI roles** | **Workflow Designer** (graph: units, connections, bounds); **RL Coach** (goals, rewards, algorithm). Both operate on **data/config**, not code. | **Done**: `assistants/` (graph_edits, config_edits, **prompts.py** with system prompts for Workflow Designer and RL Coach), CLI `apply_graph` / `apply_config`. Backend applies edits → normalizer → canonical; LLM integration uses prompts from `assistants.prompts`. |
| **§4 Data model** | Process graph (units + connections), training config (goal, rewards, algorithm), **canonical schema**, **normalizer**, control loop (model ↔ simulator). | **Done**: `schemas/` (ProcessGraph, TrainingConfig), `normalizer/` (YAML, Node-RED, template → canonical). Env factory + train/test consume canonical only. |
| **§5 Stack** | Gymnasium, SB3, config-driven env factory + training, Node-RED (editor), IDAES/PC-Gym (optional). | **Done**: Gymnasium, SB3, config-driven train/test; normalizer accepts Node-RED, template, PyFlow, Ryven, IDAES, n8n. External adapters: Node-RED, EdgeLinkd, PyFlow, Ryven, IDAES; n8n import + deploy. |
| **§6 GUI sketch** | Left: env type; center: process canvas; right: training panel; chat. | **Done**: Flet GUI — load graph (Node-RED, YAML, PyFlow, n8n, paste), canvas with layered layout, training tab + Run/Test, RAG, settings; right panel **AI chat** (Workflow Designer / RL Coach). No env-type selector. |
| **§7 Migration path** | (1) Keep temp env + runtime/train.py ✅ (2) Extract unit set → data model ✅ (3) Env factory ✅ (4) Add PC-Gym templates ⏳ (5) Training config file ✅ (6) Minimal GUI ⏳ (7) Wire assistants ✅ | **Steps 1–3, 5, 6 (partial), 7 done.** Step 4: adapter pattern only; no concrete PC-Gym templates. Step 6: minimal GUI with flow view + training + assistant. |
| **§10 Model-operator** | LLM (speech, goals) + RL operator (control); middleware connects them. | **Done**: Flet GUI chat (Workflow Designer / RL Coach) + Training tab Run/Test — Ollama + PPO; user sets target, runs test; RL policy via `scripts/test_model.py` or GUI. |
| **§11 Generalization** | Same architecture for other env types; add env type + factory + train operator. | **Done**: `environments/` (EnvSource: GYMNASIUM, EXTERNAL, CUSTOM), `get_env()`; adapters for Node-RED, PyFlow, Ryven, IDAES, n8n (import + deploy). One full CUSTOM (thermodynamic); EXTERNAL via adapters. |

**Summary**

- **Implemented:** Canonical schemas, normalizer (YAML, Node-RED, template, PyFlow, Ryven, IDAES, n8n; code_blocks), env factory (thermodynamic), config-driven training and test, assistants (apply edits + text-to-reward → canonical), model-operator (chat + RL), environments package (CUSTOM/GYMNASIUM/EXTERNAL) with external adapters (Node-RED, EdgeLinkd, PyFlow, Ryven, IDAES; n8n import/deploy), agent folder layout, water-tank simulator (viz), scripts under `scripts/`, **Flet GUI** (load graph from all formats, canvas with layered layout, training config, Run/Test, RAG, AI chat). See **docs/PROGRESS_ASSESSMENT.md** for full assessment.
- **Not implemented / partial:** **env-type selector** in GUI; **graph-driven live view** (topology in canvas done; live step view still env-specific in thermodynamics.water_tank_simulator); **other env types** (chemical, generic_control, or second thermodynamic topology); concrete PC-Gym templates.

---

## Principles

1. **Canonical schema first** — One process graph schema and one training config schema (Pydantic). All consumers (env factory, training script, assistants) use canonical only.
2. **Normalizer everywhere** — Every external format (YAML, Node-RED flow, assistant edits, templates) is mapped to canonical via the normalizer. No format branching inside env factory or training.
3. **Incremental** — Each phase delivers something runnable; we keep existing `graph_env` and `runtime/train.py` working while adding the new path.

---

## Phase 1: Canonical schemas + data normalizer ✅ (current)

**Goal:** Define canonical schemas and a normalizer so all data flows through one format. Use it everywhere for consistency.

| Task | Description | Status |
|------|-------------|--------|
| 1.1 | Define **canonical process graph** schema (Pydantic): `environment_type`, `units` (id, type, params, controllable), `connections` (from, to). | Done |
| 1.2 | Define **canonical training config** schema (Pydantic): `goal` (type, target_temp, target_volume_ratio), `rewards` (preset, weights), `algorithm`, `hyperparameters`. | Done |
| 1.3 | Implement **normalizer** module: `to_process_graph(raw, format="yaml" \| "dict")`, `to_training_config(raw, format="yaml" \| "dict")`. Validate and return canonical models. | Done |
| 1.4 | Add **YAML/dict adapter** (our primary format). Load from file or dict; normalize to canonical. | Done |
| 1.5 | Example configs in canonical format: `config/examples/temperature_process.yaml`, `config/examples/training_config.yaml`. | Done |
| 1.6 | Minimal test or script: load YAML → normalizer → canonical; assert schema. | Done |

**Deliverable:** `schemas/`, `normalizer/`, `config/examples/`, `scripts/test_normalizer.py`. Run from repo root (with venv): `python scripts/test_normalizer.py`

---

## Phase 2: Env factory (canonical graph → Gymnasium env) ✅ (done)

**Goal:** Env factory consumes **canonical** process graph only; builds Gymnasium env. First support: temperature (thermodynamic) env matching current `GraphEnv`.

| Task | Description | Status |
|------|-------------|--------|
| 2.1 | Implement **env factory**: `build_env(process_graph: ProcessGraph, goal: GoalConfig) -> gym.Env`. | Done |
| 2.2 | For `environment_type: thermodynamic` and graph matching current temperature setup (sources, valves, tank, sensor), instantiate `GraphEnv` with params derived from canonical graph + goal. | Done |
| 2.3 | Add validation in factory: require needed units/connections for chosen env type. | Done |

**Deliverable:** `env_factory/` (`factory.py`, `__init__.py`), `scripts/test_env_factory.py`. Run from repo root: `python scripts/test_env_factory.py`

**Current limitation:** We have **only one process with dynamic simulation**: the thermodynamic temperature-mixing process (2 sources, 1 tank, 3 valves, sensor). The env factory supports only `environment_type: thermodynamic` and maps to a single `GraphEnv`; it reads params from the graph but the dynamics are fixed (one tank, three valves). **No simulation** for other env types (chemical, generic_control) or for different topologies (e.g. two tanks, four valves). Adding a new process requires implementing a new env class and wiring it in the factory.

---

## Phase 3: Config-driven training (canonical config → train) ✅ (done)

**Goal:** Training script reads **canonical** training config (from file or API); creates env via env factory from canonical process graph; runs SB3. No hardcoded env params in `runtime/train.py`.

| Task | Description | Status |
|------|-------------|--------|
| 3.1 | Add **config-driven entry point**: e.g. `runtime/train.py --config config/training_config.yaml` (and optional `--process-config config/process.yaml`). Load via normalizer; build env via factory; run SB3 from canonical hyperparameters. | Done |
| 3.2 | Config-only: legacy hardcoded path removed; `--config` required. | Done |
| 3.3 | Persist used config (canonical) alongside checkpoints for reproducibility. | Done |

**Deliverable:** `runtime/train.py` supports `--config` + optional `--process-config`. Saves `models/training_config_used.yaml` and `models/process_config_used.yaml`. Run: `cd /Users/jm/ai-control-agent && source venv/bin/activate && python runtime/train.py --config config/examples/training_config.yaml --timesteps 5000` (short run to verify).

---

## Phase 4: Assistants (edits → normalizer → canonical) ✅ (done)

**Goal:** **Workflow Designer** and **RL Coach** output structured edits; backend applies edits and runs edits through normalizer to get updated canonical graph/config. System prompts are in the repo so LLM integration can use them directly.

| Task | Description | Status |
|------|-------------|--------|
| 4.1 | **Workflow Designer** (process graph): system prompt in `assistants/prompts.py` (`WORKFLOW_DESIGNER_SYSTEM`); structured output = graph edit JSON. Backend applies via `process_assistant_apply` → **normalizer.to_process_graph** → canonical. | Done |
| 4.2 | **RL Coach** (training config): system prompt in `assistants/prompts.py` (`RL_COACH_SYSTEM`); for reward shaping the Coach outputs `reward_from_text` and backend calls **text-to-reward** then merges; for goal/algorithm/hyperparameters outputs direct config edit. `training_assistant_apply` → normalizer → canonical. | Done |
| 4.3 | Optional: API endpoints or CLI that accept assistant output and return normalized canonical (for GUI or scripts). | Done |

**Deliverable:** `assistants/` (graph_edits, config_edits, **prompts.py**, process_assistant, training_assistant), CLI `python -m assistants apply_graph|apply_config`, `scripts/test_assistants.py`. Text-to-reward prompt remains in `assistants/text_to_reward.py`. Assistant integration always goes through normalizer; canonical only downstream.

---

## Phase 5: Additional adapters (Node-RED, templates)

**Goal:** Add more input formats to the normalizer so new UIs or templates feed the same pipeline.

| Task | Description | Status |
|------|-------------|--------|
| 5.1 | **Node-RED adapter**: map Node-RED flow JSON → canonical process graph. Add `format="node_red"` to `to_process_graph`. | Done |
| 5.2 | **Template adapter**: load PC-Gym / IDAES-style template (if we have a schema for them); map to canonical. | Done |

**Deliverable:** Normalizer supports `format="node_red"` and `format="template"`. Node-RED: flow nodes (type in Source/Valve/Tank/Sensor, wires) → units/connections. Template: dict with `blocks`/`links` or `units`/`connections` → canonical; example `config/examples/temperature_process_template.json`. `load_process_graph_from_file(path)` infers format from `.json` (node_red). Env factory and training unchanged.

---

## What’s left (from VISION.md)

Phases 1–5 cover **data + backend**: canonical schemas, normalizer, env factory, config-driven training, assistants (apply edits), and Node-RED/template adapters. The following are **not yet implemented** and are optional next steps.

### GUI (§6, §7 step 6) — in progress

| Item | VISION | Status |
|------|--------|--------|
| **Process graph** | Load from Node-RED flow JSON or YAML; validate → canonical. | **Done**: Flet GUI — load/paste/upload Node-RED / YAML / PyFlow / Ryven / n8n JSON; normalizer → canonical; canvas shows units and connections with layered layout. |
| **Process graph editor** | Canvas with units + connections; drag from palette; double-click params. Recommended: **Node-RED** (we have the adapter; no custom nodes or running Node-RED setup yet). Alternative: React Flow / Rete.js. | **Partial (import + view + edit)**: Flet canvas — load/paste/upload; edit nodes and links on canvas. Format doc in `gui/node-red/README.md`, example in `gui/node-red/example_flow.json`. |
| **Training panel** | Goal (setpoints/ranges), reward preset + sliders/weights, algorithm (PPO/SAC), “Run training” / “Test policy.” Forms. | **Done**: Flet Training tab — load/edit goal, model_dir, timesteps; run `runtime/train.py` (via run_rl_training workflow) and `scripts/test_model.py`. |
| **Assistant panel** | Apply **Workflow Designer** or **RL Coach** edits (JSON) → normalized result. Prompts in `assistants/prompts.py`. | **Done**: Flet chat applies graph or config edits via workflows. |
| **Chat panel** | "Add a tank," "Penalize dumping more" — routed to Workflow Designer or RL Coach. | **Done**: Flet GUI chat (Workflow Designer / RL Coach). CLI: `python -m assistants apply_*`. |

**Minimal next step:** Optional: embed or link Node-RED for the process canvas (see below).

**Embed vs link Node-RED (for the process canvas):**

| Option | Meaning |
|--------|--------|
| **Link** | Node-RED runs as a **separate** app (e.g. `npx node-red` or Docker). Users design the flow there, **export** the flow JSON (or copy), then **import** that JSON into our GUI (Upload Node-RED JSON or Paste JSON). The "link" is the **data flow**: Node-RED export → our normalizer → canonical process graph. No Node-RED UI inside our app. **Current state:** we already support this (GUI accepts Node-RED flow JSON). |
| **Embed** | Node-RED's **editor UI** runs **inside** our app (e.g. in an iframe, or Node-RED packaged in Electron/Tauri). Users edit the flow in the same window as the training panel; we'd need to get the flow JSON from the embedded instance (Node-RED HTTP API or postMessage). More integrated UX; more work (hosting Node-RED, CORS, auth, syncing flow back into our backend). |

So: **linking** = use Node-RED elsewhere, bring the exported JSON into the constructor; **embedding** = run the Node-RED canvas inside the constructor UI.

**Trained agent as a Node-RED node:** An agent trained in our platform can be deployed as a **custom Node-RED node**. At runtime the model sits in the flow: **observations in** (from Sensor/Setpoint nodes), **actions out** (to Valve/actuator nodes). See **docs/DEPLOYMENT_NODERED.md** for the projected design-time vs runtime flow and where the trained model is wired.

**PyFlow / Ryven (Python-native editors), full workflow + code:** See **docs/WORKFLOW_EDITORS_AND_CODE.md**. PyFlow and Ryven are Python alternatives to Node-RED; same roundtrip (import full workflow → train via adapter → model as node). Canonical format extended with optional **code_blocks** (language-agnostic: id, language, source) for full workflow import including functions.

**Reward rules (rule engine, text-to-reward):** See **docs/REWARD_RULES.md**. We had no rule engine; **RewardsConfig** now has optional **rules** (condition → reward_delta) for Rule-engine. Options: Rule-engine (structured rules), Clipspy (expert system), text-to-reward (LLM → reward function).

### Process visualization (during testing/training)

**Visualization is environment-type dependent.** Thermodynamic/chemical envs are best served by a flowsheet-style viewer (e.g. IDAES Flowsheet Visualizer); generic_control by a topology graph; robotics/vision by their sim viewers. See **docs/OPEN_SOURCE_TOOLS.md** for a per-type strategy and tool options.

| Item | Current | Gap |
|------|--------|-----|
| **Topology view** | **Done in GUI**: Flow tab shows canonical process graph as **React Flow** (units + connections, layered layout). | — |
| **Live process view** | `environments/custom/thermodynamics/water_tank_simulator.py` has a **hardcoded** tank schematic (hot/cold valves, tank, dump, thermometer) and updates it step-by-step. Works only for the current temperature layout. | Not **graph-driven**: different process graphs (e.g. extra valve, second tank) are not visualized. Live view remains env-specific; no shared “process visualizer” that consumes `ProcessGraph` + optional live state. |

**Minimal next step:** (1) **Per-type choice**: thermodynamic/chemical → IDAES IFV (or bridge from ProcessGraph) when available; generic_control → NetworkX/Graphviz; fallback = generic topology for any type. (2) **Generic fallback**: script or small app that reads a process graph (YAML/JSON), builds a graph (units = nodes, connections = edges), and renders it. (3) **Live view**: extend or refactor so topology is driven by ProcessGraph and state is overlaid; for thermodynamic, keep or extend test_model-style viewer; for other types, use the appropriate viewer per OPEN_SOURCE_TOOLS.md.

### Summary

- **Done:** Data model, normalizer (all formats + code_blocks), env factory, config-driven training, assistants backend + CLI, Node-RED/template/PyFlow/Ryven/IDAES/n8n adapters and deploy, model-operator (chat + RL), Flet GUI (load graph from all formats, canvas topology, training + Run/Test + AI chat). Process visualization: **topology** in Flow tab (graph-driven). See **docs/PROGRESS_ASSESSMENT.md** for full assessment.
- **Left:** **GUI** — env-type selector; **process visualization** — graph-driven **live** view (topology done; live step view remains env-specific, e.g. thermodynamics.water_tank_simulator). Optional for “run from config + CLI”; they become important when you want a no-code “constructor” and visual feedback.

---

## Directory layout (after Phase 1–2)

```
ai-control-agent/
  config/
    examples/
      temperature_process.yaml    # canonical process graph example
      training_config.yaml       # canonical training config example
  schemas/
    __init__.py
    process_graph.py             # ProcessGraph, Unit, Connection, etc.
    training_config.py           # TrainingConfig, GoalConfig, RewardsConfig, etc.
  normalizer/
    __init__.py
    normalizer.py                # to_process_graph, to_training_config
  env_factory/
    __init__.py
    factory.py                   # build_env(process_graph, goal) -> gym.Env ✅
  environments/graph_env.py  # generic; thermodynamics/spec.py for thermodynamic
  runtime/train.py               # add --config path; use normalizer + factory
  scripts/                       # dev/test scripts (run from repo root)
    test_assistants.py
    test_env_factory.py
    test_environments.py
    test_normalizer.py
  ...
```

---

## Summary

- **Phase 1:** Canonical schemas + normalizer (use everywhere for consistency). ✅ Start here.
- **Phase 2:** Env factory from canonical process graph (temperature first).
- **Phase 3:** Config-driven training (canonical config → train).
- **Phase 4:** Assistants output edits → normalizer → canonical.
- **Phase 5:** More adapters (Node-RED, templates).

Data normalizer is **necessary** and used everywhere so the rest of the stack sees a single, consistent format.
