# PyFlow: AI data smart filter

Filter a large JSON response (e.g. **200 000 flight offers**) through an RL Agent so the output is a smaller **response_filtered.json** with the **best 200** offers.

Data flow:

- **No agent (bypass):** `response.json` → pass-through → `response.json`
- **RL Agent wired:** `response.json` → RL Agent filter → `response_filtered.json`

Reference payload shape: [Amadeus Flight Offers Search API](https://github.com/amadeus4dev/amadeus-code-examples/blob/master/flight_offers_search/v2/get/response.json) — `{ "meta": {...}, "data": [ ... offers ... ] }`.

## Flow files

- **smart_filter_pyflow_no_agent.json** — Flow **before** the RL Agent is wired. Input (response.json) is passed through unchanged.
- **smart_filter_pyflow_wired.json** — Flow **after** the Agent is wired: parse → RL Agent filter → build `response_filtered.json`. Use for **inference**.
- **smart_filter_pyflow_step.json** — Flow for **training**: same step API as the adapter (obs 4 dims, action 1 dim, reward/done from nodes). Episode: 100 synthetic offers; reward at end = −mean(price) + bonus for ~20 selected. Uses `reward_node` and `done_node` in the training config.

```
Inference:  response.json  ──→  [Parse] ──→ [RL Agent filter] ──→ response_filtered.json
Training:   step flow  ──→  obs_out, reward_out, done_out  (adapter injects action into rl_agent)
```

## Training config

- **training_config_pyflow.yaml** — For **training**: uses **smart_filter_pyflow_step.json** with `observation_sources: ["obs_out"]`, `action_targets: ["rl_agent"]`, `reward_node: "reward_out"`, `done_node: "done_out"`. After training, use the wired flow for inference.

## Train

From repo root: `python train.py --config config/examples/pyflow_runtime/pyflow_AI_data-smart-filter/training_config_pyflow.yaml`  
No external process; the PyFlow adapter runs the step graph in-process.

## Run (inference)

Use **smart_filter_pyflow_wired.json** with your payload. Input: response.json (meta + data). Output: response_filtered.json (scaffold: first 200; plug in trained policy for real selection).
