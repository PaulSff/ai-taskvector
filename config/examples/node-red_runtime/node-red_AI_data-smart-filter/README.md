# Node-RED: AI data smart filter

Filter a large JSON response (e.g. **200 000 flight offers**) through an RL Agent so the output is a smaller **response_filtered.json** with the **best 200** offers.

Data flow:

- **No agent (bypass):** `response.json` → pass-through → `response.json`
- **RL Agent wired:** `response.json` → RL Agent filter → `response_filtered.json`

Reference payload shape: [Amadeus Flight Offers Search API](https://github.com/amadeus4dev/amadeus-code-examples/blob/master/flight_offers_search/v2/get/response.json) — `{ "meta": {...}, "data": [ ... offers ... ] }`.

## Flow files

- **smart_filter_node_red_no_agent.json** — Flow **before** the RL Agent is wired. Request body (response.json) is returned unchanged.
- **smart_filter_node_red_wired.json** — Flow **after** the Agent is wired: parse request → RL Agent filter (select best 200) → build `response_filtered.json` → response. Use for **inference** (POST /filter).
- **smart_filter_node_red_step.json** — Flow that exposes **POST /step** for **training**: reset/action → observation, reward, done. Episode: 100 synthetic offers; obs 4 dims (price, duration, stops, index norm), action 1 dim (include if > 0.5); reward at end = −mean(price) + bonus for ~20 selected.

```
Inference:  response.json (POST /filter)  ──→  [Parse] ──→ [RL Agent filter] ──→ response_filtered.json
Training:   POST /step  { reset | action }  ──→  [Step driver]  ──→  { observation, reward, done }
```

## Training config

- **training_config_node_red.yaml** — For **training**: deploy **smart_filter_node_red_step.json** and set `step_url: http://127.0.0.1:1880/step`. Obs shape 4, action shape 1. After training, deploy the model into the wired flow for inference (POST /filter).

## Train

1. Start Node-RED and deploy **smart_filter_node_red_step.json** (so POST /step is available).
2. From repo root: `python runtime/train.py --config config/examples/node-red_runtime/node-red_AI_data-smart-filter/training_config_node_red.yaml`

## Run (inference)

1. Deploy **smart_filter_node_red_wired.json**.
2. Send `POST http://127.0.0.1:1880/filter` with body = your response.json. The flow returns a filtered response (scaffold: first 200; replace "RL Agent filter" node with your trained model for real selection).

## Running on EdgeLinkd

[EdgeLinkd](https://github.com/oldrev/edgelinkd) is Node-RED–compatible. Same flows; default port **1888**.

- **Inference:** Deploy **smart_filter_node_red_wired.json**, call `POST http://127.0.0.1:1888/filter`.
- **Training:** Deploy **smart_filter_node_red_step.json**, set `step_url: http://127.0.0.1:1888/step` in the training config, then run `runtime/train.py`.
