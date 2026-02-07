# PyFlow: AI data smart filter

Filter a large JSON response (e.g. **200 000 flight offers**) through an RL Agent so the output is a smaller **response_filtered.json** with the **best 200** offers.

Data flow:

- **No agent (bypass):** `response.json` → pass-through → `response.json`
- **RL Agent wired:** `response.json` → RL Agent filter → `response_filtered.json`

Reference payload shape: [Amadeus Flight Offers Search API](https://github.com/amadeus4dev/amadeus-code-examples/blob/master/flight_offers_search/v2/get/response.json) — `{ "meta": {...}, "data": [ ... offers ... ] }`.

## Flow files

- **smart_filter_pyflow_no_agent.json** — Flow **before** the RL Agent is wired. Input (response.json) is passed through unchanged.
- **smart_filter_pyflow_wired.json** — Flow **after** the Agent is wired: parse → RL Agent filter (select best 200) → build `response_filtered.json` → output.

```
response.json  ──→  [Parse] ──→ [RL Agent filter] ──→ [Build response_filtered] ──→ response_filtered.json
                              ↑
                        (trained policy)
```

## Training config

- **training_config_pyflow.yaml** — Placeholder for training. **Training** a selection agent requires a custom environment (not in this repo) that simulates offers and rewards (e.g. relevance, diversity, price). The PyFlow flow is for **deployment**: run the wired graph with response.json in; replace the RL Agent node with your trained policy for real selection.

## Run (deployment)

From repo root, use the PyFlow adapter to run the wired flow with your payload. Input: response.json (meta + data). Output: response_filtered.json (meta + data with best 200; scaffold uses first 200 until a trained policy is plugged in).

## Training (future)

When a custom “filter” env exists: train with that env (observation = offer features, action = include/discard or score, reward = quality of selected set). Then use the resulting model in the PyFlow “RL Agent filter” node.
