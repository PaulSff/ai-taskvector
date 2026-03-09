# Config

## Roundtrip (train → deploy)

Same idea across pipelines: 
- **process graph** and **training config** define the env; 
- training produces a **model**; 
- you **deploy** that model back into the flow so the RL Agent node runs the policy. 

```
[Process graph]    ──┐
(YAML or JSON)       │
                     ├──► Train RL Agent (custom | Node-RED | PyFlow) ──► Model (.zip)
[Training config] ───┘         │                                        │
(environment, goal,                 uses same observation/action        │
 rewards, algorithm)                    wiring as deploy                │
                                                                        ▼
[Flow with RL Agent node]  ◄──  Deploy (inject agent into flow, load .zip)
     │
     ├── inputs:  [Setpoint], [Observation 1], [Observation 2], …
     └── outputs: [Action 1], [Action 2], [Action 3], …
```

So: **train** with a wired graph + config → **deploy** the resulting model into that (or the same) flow; the RL Agent node then receives observations and outputs actions in the same order as during training.

---

- **[TRAINING_CONFIG_GUIDE.md](TRAINING_CONFIG_GUIDE.md)** — How to create a training config for each pipeline (custom, Node-RED, PyFlow, ComfyUI) and how to set reward options (preset+weights, formula DSL, rule-engine rules; plus standalone text-to-reward CLI).
- **examples/** — Example process graphs and training configs:
  - **native_runtime_factory/** — Native env (env_factory) with YAML process graph.
  - **node-red_runtime/** — Node-RED flows + training config (temperature control; AI data smart filter).
  - **pyflow_runtime/** — PyFlow in-process flows + training config (temperature control; AI data smart filter).
