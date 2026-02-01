# Implementation Plan

This document outlines the implementation plan for the constructor + AI assistants vision. **Data normalizer is core**: all inputs (Node-RED, YAML, templates, assistants) flow through the normalizer to **canonical** process graph and training config so the rest of the stack stays consistent.

---

## Principles

1. **Canonical schema first** — One process graph schema and one training config schema (Pydantic). All consumers (env factory, training script, assistants) use canonical only.
2. **Normalizer everywhere** — Every external format (YAML, Node-RED flow, assistant edits, templates) is mapped to canonical via the normalizer. No format branching inside env factory or training.
3. **Incremental** — Each phase delivers something runnable; we keep existing `temperature_env` and `train.py` working while adding the new path.

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

**Deliverable:** `schemas/`, `normalizer/`, `config/examples/`, `test_normalizer.py`. Run (with venv): `cd /Users/jm/ai-control-agent && source venv/bin/activate && python test_normalizer.py`

---

## Phase 2: Env factory (canonical graph → Gymnasium env) ✅ (done)

**Goal:** Env factory consumes **canonical** process graph only; builds Gymnasium env. First support: temperature (thermodynamic) env matching current `TemperatureControlEnv`.

| Task | Description | Status |
|------|-------------|--------|
| 2.1 | Implement **env factory**: `build_env(process_graph: ProcessGraph, goal: GoalConfig) -> gym.Env`. | Done |
| 2.2 | For `environment_type: thermodynamic` and graph matching current temperature setup (sources, valves, tank, sensor), instantiate `TemperatureControlEnv` with params derived from canonical graph + goal. | Done |
| 2.3 | Add validation in factory: require needed units/connections for chosen env type. | Done |

**Deliverable:** `env_factory/` (`factory.py`, `__init__.py`), `test_env_factory.py`. Run: `cd /Users/jm/ai-control-agent && source venv/bin/activate && python test_env_factory.py`

**Current limitation:** We have **only one process with dynamic simulation**: the thermodynamic temperature-mixing process (2 sources, 1 tank, 3 valves, sensor). The env factory supports only `environment_type: thermodynamic` and maps to a single `TemperatureControlEnv`; it reads params from the graph but the dynamics are fixed (one tank, three valves). **No simulation** for other env types (chemical, generic_control) or for different topologies (e.g. two tanks, four valves). Adding a new process requires implementing a new env class and wiring it in the factory.

---

## Phase 3: Config-driven training (canonical config → train) ✅ (done)

**Goal:** Training script reads **canonical** training config (from file or API); creates env via env factory from canonical process graph; runs SB3. No hardcoded env params in `train.py`.

| Task | Description | Status |
|------|-------------|--------|
| 3.1 | Add **config-driven entry point**: e.g. `train.py --config config/training_config.yaml` (and optional `--process-config config/process.yaml`). Load via normalizer; build env via factory; run SB3 from canonical hyperparameters. | Done |
| 3.2 | Config-only: legacy hardcoded path removed; `--config` required. | Done |
| 3.3 | Persist used config (canonical) alongside checkpoints for reproducibility. | Done |

**Deliverable:** `train.py` supports `--config` + optional `--process-config`. Saves `models/training_config_used.yaml` and `models/process_config_used.yaml`. Run: `cd /Users/jm/ai-control-agent && source venv/bin/activate && python train.py --config config/examples/training_config.yaml --timesteps 5000` (short run to verify).

---

## Phase 4: Assistants (edits → normalizer → canonical) ✅ (done)

**Goal:** Process Assistant and Training Assistant output structured edits; backend applies edits and runs edits through normalizer to get updated canonical graph/config.

| Task | Description | Status |
|------|-------------|--------|
| 4.1 | **Process Assistant**: prompt + structured output (graph edit JSON). Backend applies edit to current graph (dict/yaml), then **normalizer.to_process_graph**(updated) → canonical. Validate; persist or pass to env factory. | Done |
| 4.2 | **Training Assistant**: prompt + structured output (config edit JSON). Backend merges edit into current config, then **normalizer.to_training_config**(merged) → canonical. Validate; save to file or pass to training. | Done |
| 4.3 | Optional: API endpoints or CLI that accept assistant output and return normalized canonical (for GUI or scripts). | Done |

**Deliverable:** `assistants/` (graph_edits, config_edits, process_assistant, training_assistant), CLI `python -m assistants apply_graph|apply_config`, `test_assistants.py`. Assistant integration always goes through normalizer; canonical only downstream.

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

### GUI (§6, §7 step 6)

| Item | VISION | Status |
|------|--------|--------|
| **Process graph editor** | Canvas with units + connections; drag from palette; double-click params. Recommended: **Node-RED** (we have the adapter; no custom nodes or running Node-RED setup yet). Alternative: React Flow / Rete.js. | Not built. Backend can accept Node-RED/template/YAML. |
| **Training panel** | Goal (setpoints/ranges), reward preset + sliders/weights, algorithm (PPO/SAC), “Run training” / “Test policy.” Forms (Streamlit/Gradio or React + schema). | Not built. All driven by YAML + CLI today. |
| **Chat panel** | “Add a tank,” “Penalize dumping more” — routed to Process or Training assistant. | Only CLI/script: `chat_with_local_ai.py`, `python -m assistants apply_*`. No GUI chat. |

**Minimal next step:** Streamlit or Gradio app: (1) load/edit process graph (form or list), (2) load/edit training config (forms), (3) “Run training” / “Test” buttons that call `train.py` and `test_model.py`. Optional: embed or link Node-RED for the process canvas.

### Process visualization (during testing/training)

**Visualization is environment-type dependent.** Thermodynamic/chemical envs are best served by a flowsheet-style viewer (e.g. IDAES Flowsheet Visualizer); generic_control by a topology graph; robotics/vision by their sim viewers. See **docs/OPEN_SOURCE_TOOLS.md** for a per-type strategy and tool options.

| Item | Current | Gap |
|------|--------|-----|
| **Topology view** | None. | No tool that takes a **canonical process graph** and draws units + connections (e.g. graph-only: NetworkX/Matplotlib or Graphviz). |
| **Live process view** | `test_model.py` has a **hardcoded** tank schematic (hot/cold valves, tank, dump, thermometer) and updates it step-by-step. Works only for the current temperature layout. | Not **graph-driven**: different process graphs (e.g. extra valve, second tank) are not visualized. No shared “process visualizer” that consumes `ProcessGraph` + optional live state. |

**Minimal next step:** (1) **Per-type choice**: thermodynamic/chemical → IDAES IFV (or bridge from ProcessGraph) when available; generic_control → NetworkX/Graphviz; fallback = generic topology for any type. (2) **Generic fallback**: script or small app that reads a process graph (YAML/JSON), builds a graph (units = nodes, connections = edges), and renders it. (3) **Live view**: extend or refactor so topology is driven by ProcessGraph and state is overlaid; for thermodynamic, keep or extend test_model-style viewer; for other types, use the appropriate viewer per OPEN_SOURCE_TOOLS.md.

### Summary

- **Done:** Data model, normalizer, env factory, config-driven training, assistants backend + CLI, Node-RED/template adapters, model-operator (chat + RL).
- **Left:** **GUI** (process editor, training panel, chat) and **process visualization** (graph-driven topology + optional live state during test/training). Both are optional for “run from config + CLI”; they become important when you want a no-code “constructor” and visual feedback.

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
  temperature_env.py             # unchanged; used by factory for thermodynamic
  train.py                       # add --config path; use normalizer + factory
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
