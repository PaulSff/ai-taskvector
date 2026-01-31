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

---

## Phase 3: Config-driven training (canonical config → train)

**Goal:** Training script reads **canonical** training config (from file or API); creates env via env factory from canonical process graph; runs SB3. No hardcoded env params in `train.py`.

| Task | Description | Status |
|------|-------------|--------|
| 3.1 | Add **config-driven entry point**: e.g. `train.py --config config/training_config.yaml` (and optional `--process-config config/process.yaml`). Load via normalizer; build env via factory; run SB3 from canonical hyperparameters. | Pending |
| 3.2 | Keep existing `train.py` behavior when no `--config` (backward compatible). | Pending |
| 3.3 | Persist used config (canonical) alongside checkpoints for reproducibility. | Pending |

**Deliverable:** `train.py` supports `--config` + optional process config; full path: YAML → normalizer → canonical → env factory → SB3.

---

## Phase 4: Assistants (edits → normalizer → canonical)

**Goal:** Process Assistant and Training Assistant output structured edits; backend applies edits and runs edits through normalizer to get updated canonical graph/config.

| Task | Description | Status |
|------|-------------|--------|
| 4.1 | **Process Assistant**: prompt + structured output (graph edit JSON). Backend applies edit to current graph (dict/yaml), then **normalizer.to_process_graph**(updated) → canonical. Validate; persist or pass to env factory. | Pending |
| 4.2 | **Training Assistant**: prompt + structured output (config edit JSON). Backend merges edit into current config, then **normalizer.to_training_config**(merged) → canonical. Validate; save to file or pass to training. | Pending |
| 4.3 | Optional: API endpoints or CLI that accept assistant output and return normalized canonical (for GUI or scripts). | Pending |

**Deliverable:** Assistant integration that always goes through normalizer; canonical only downstream.

---

## Phase 5: Additional adapters (Node-RED, templates)

**Goal:** Add more input formats to the normalizer so new UIs or templates feed the same pipeline.

| Task | Description | Status |
|------|-------------|--------|
| 5.1 | **Node-RED adapter**: map Node-RED flow JSON → canonical process graph. Add `format="node_red"` to `to_process_graph`. | Pending |
| 5.2 | **Template adapter**: load PC-Gym / IDAES-style template (if we have a schema for them); map to canonical. | Pending |

**Deliverable:** Normalizer supports multiple formats; env factory and training unchanged.

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
