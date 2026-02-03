# Current progress assessment

This document inspects the docs and codebase to assess where the project stands relative to **VISION.md** and **IMPLEMENTATION_PLAN.md**. Last updated from a full doc + code review.

---

## 1. Summary

| Area | Vision / plan | Current status |
|------|----------------|----------------|
| **Data model** | Canonical ProcessGraph + TrainingConfig; normalizer for all formats | **Done.** Schemas in `schemas/`; normalizer supports YAML, dict, Node-RED, template, PyFlow, Ryven, IDAES, n8n; code_blocks for full workflow. |
| **Env factory** | Canonical graph → Gymnasium env (thermodynamic first) | **Done.** Config-driven; thermodynamic → TemperatureControlEnv. |
| **Training** | Config-driven train/test; no hardcoded params | **Done.** `train.py --config`; params in YAML; eval_freq/save_freq etc. from config. |
| **Assistants** | **Workflow Designer** (graph) + **RL Coach** (config); apply → normalizer → canonical | **Done.** `assistants/` (graph_edits, config_edits, **prompts.py** with WORKFLOW_DESIGNER_SYSTEM and RL_COACH_SYSTEM), process_assistant, training_assistant; text-to-reward (Ollama); CLI apply_graph/apply_config. |
| **GUI** | Process canvas, training panel, chat; “Visual Studio for process/RL” | **In progress.** Streamlit app: load graph (example, Node-RED, YAML, PyFlow, Ryven, n8n, paste JSON); **React Flow** (streamlit-flow-component) for flow viz with **layered layout**; Training config + Run/Test tabs; Assistant tab (paste edit JSON). No in-GUI chat; no drag-from-palette editor. |
| **Process visualization** | Graph-driven topology; optional live view during test/training | **Partial.** Flow tab shows **topology** (units + connections) via React Flow after import. Live step-by-step view only in `water_tank_simulator` (thermodynamic, fixed layout). |
| **External runtimes** | Node-RED, PyFlow, Ryven, IDAES as envs; roundtrip import → train → deploy | **Done.** Adapters: Node-RED (HTTP/WebSocket), EdgeLinkd, PyFlow (in-process), Ryven (WebSocket/HTTP), IDAES (in-process). n8n: import + deploy; training via Node-RED-style step if workflow exposes it. Deploy: inject_agent into Node-RED, PyFlow, n8n flows. |
| **Reward rules** | Rule engine + optional text-to-reward | **Done.** RewardsConfig supports rules; rule-engine; text-to-reward via Ollama in `assistants/text_to_reward.py`. |
| **Model-operator** | LLM (speech/goals) + RL operator; middleware | **Done.** `chat_with_local_ai.py` (Ollama + PPO); target from user, RL in loop. |

---

## 2. Alignment with VISION.md

- **§1–2 Core idea:** Constructor (env type + units + connections), AI assistants, GUI — backend and minimal GUI in place; no full “canvas editor” (drag from palette, connect in-app).
- **§3 Two AI roles:** Process and Training assistants — implemented; apply edits via normalizer; no conversational chat in GUI.
- **§4 Data model:** Process graph, training config, canonical schema, normalizer, control loop — implemented; loop diagram in VISION (§4.5) matches (model → actions → simulator → feedback).
- **§5 Stack:** Gymnasium, SB3, Node-RED/IDAES/PC-Gym — Gymnasium + SB3 + config-driven train; Node-RED/IDAES/others via adapters; GUI uses Streamlit + React Flow (streamlit-flow-component).
- **§6 GUI sketch:** Left (env type), center (canvas), right (training), chat — center is “load/paste + React Flow view” only; no env-type selector in GUI; training and assistant panels present.
- **§7 Migration path:** Steps 1–3, 5, 7 done; step 4 (PC-Gym templates) adapter pattern only; step 6 (minimal GUI) partially done (load + flow viz + training + assistant).
- **§10 Model-operator:** Implemented (chat + RL).
- **§11 Generalization:** Env types (GYMNASIUM, EXTERNAL, CUSTOM); multiple adapters; one custom thermodynamic process; IDAES/Node-RED/PyFlow/Ryven/n8n in place.

---

## 3. Alignment with IMPLEMENTATION_PLAN.md

- **Phase 1 (Canonical + normalizer):** Done; all listed tasks complete.
- **Phase 2 (Env factory):** Done; thermodynamic from canonical graph.
- **Phase 3 (Config-driven training):** Done; no hardcoded training params in train.py.
- **Phase 4 (Assistants):** Done; apply edits → normalizer; CLI and text-to-reward.
- **Phase 5 (Adapters):** Done; Node-RED, template; **plus** PyFlow, Ryven, IDAES, n8n (import; n8n deploy).
- **GUI subsection:** Needs a small doc update:
  - **Process graph:** Done — and now includes **PyFlow, Ryven, n8n** upload and **React Flow** visualization with **layered layout** (fewer edge crossings).
  - **Process graph editor:** Still “not built” in the sense of drag-from-palette, in-app connect; users still load/paste/upload.
  - **Training panel / Assistant panel:** Done.
  - **Chat panel:** Only CLI; no GUI chat.
- **Process visualization:** Topology view is now in the GUI (Flow tab = ProcessGraph → React Flow). Live process view remains environment-specific (water_tank_simulator for thermodynamic).
- **Runtime adapters / deploy:** As in WORKFLOW_EDITORS_AND_CODE.md — all listed adapters implemented; deploy for Node-RED, PyFlow, n8n.

---

## 4. Gaps and next steps (from docs)

| Gap | Doc reference | Suggested next step |
|-----|----------------|----------------------|
| **In-GUI process editor** | IMPLEMENTATION_PLAN “Process graph editor” | Keep “link” flow (import from Node-RED/PyFlow/etc.); optionally add simple palette + connect in GUI later, or document “design in Node-RED, import here” as the path. |
| **GUI chat** | VISION §6, IMPLEMENTATION_PLAN “Chat panel” | Add a chat UI that routes to Process or Training assistant (or orchestrator) and shows apply result. |
| **Env type selector in GUI** | VISION §6 “Left: Environment type” | Add sidebar or step to choose environment type (thermodynamic / gymnasium / external) when loading or creating a graph. |
| **Graph-driven live view** | IMPLEMENTATION_PLAN “Live process view” | Keep per-env visualizer (e.g. water_tank_simulator); document that live view is env-specific; optional: generic “state overlay” on Flow tab later. |
| **PC-Gym templates** | IMPLEMENTATION_PLAN §7 step 4 | Add 1–2 concrete PC-Gym (or similar) templates as cloneable examples if needed. |
| **Doc updates** | — | Update IMPLEMENTATION_PLAN “Process graph” row to mention React Flow, layered layout, and PyFlow/Ryven/n8n in GUI; set “Process graph editor” to “Partial (import + view only).” |

---

## 5. Conclusion

The **backend and data path** are in good shape: canonical schemas, normalizer (all formats including code_blocks), env factory, config-driven training, assistants (graph + config + text-to-reward), external adapters (Node-RED, EdgeLinkd, PyFlow, Ryven, IDAES, n8n import/deploy), and reward rules. The **GUI** provides load/paste/upload for all supported formats, **React Flow** preview with a **layered layout**, training config, run/test, and assistant (paste-edit). What’s missing for the full “constructor” vision is an **in-app process editor** (palette + connect), **GUI chat** to the assistants, and an explicit **env type** selector; process visualization is partly addressed (topology in Flow tab; live view remains env-specific). Updating IMPLEMENTATION_PLAN to reflect the current GUI (React Flow, formats, layered layout) will keep the docs and assessment in sync.
