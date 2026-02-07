# Node-RED: AI data smart filter

Filter a large JSON response (e.g. **200 000 flight offers**) through an RL Agent so the output is a smaller **response_filtered.json** with the **best 200** offers.

Data flow:

- **No agent (bypass):** `response.json` → pass-through → `response.json`
- **RL Agent wired:** `response.json` → RL Agent filter → `response_filtered.json`

Reference payload shape: [Amadeus Flight Offers Search API](https://github.com/amadeus4dev/amadeus-code-examples/blob/master/flight_offers_search/v2/get/response.json) — `{ "meta": {...}, "data": [ ... offers ... ] }`.

## Flow files

- **smart_filter_node_red_no_agent.json** — Flow **before** the RL Agent is wired. Request body (response.json) is returned unchanged.
- **smart_filter_node_red_wired.json** — Flow **after** the Agent is wired: parse request → RL Agent filter (select best 200) → build `response_filtered.json` → response.

```
response.json (POST /filter)  ──→  [Parse] ──→ [RL Agent filter] ──→ [Build response_filtered] ──→ response_filtered.json
                                            ↑
                                    (load trained .zip)
```

## Training config

- **training_config_node_red.yaml** — Placeholder for training. **Training** a selection agent requires a custom environment (not in this repo) that simulates offers and rewards (e.g. relevance, diversity, price). The Node-RED flow is for **deployment**: deploy the wired flow and call `POST /filter` with your response body; replace the “RL Agent filter” node with one that loads your trained model and outputs the selected offers.

## Run (deployment)

1. Start Node-RED and deploy **smart_filter_node_red_wired.json**.
2. Send `POST http://127.0.0.1:1880/filter` with body = your response.json (e.g. Amadeus-style `{ meta, data }`). The flow returns a filtered response (scaffold: first 200; replace with trained policy for real selection).

## Training (future)

When a custom “filter” env exists: train with that env (observation = offer features, action = include/discard or score, reward = quality of selected set). Then deploy the resulting model into the Node-RED “RL Agent filter” node.
