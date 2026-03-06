# Canonical wiring schemas

The canonical scheme exists for **one reason only: one single version for all runtimes** (Node-RED, n8n, PyFlow, native, etc.). The same topology and unit roles apply everywhere; runtime-specific export maps this single graph to each editor’s format.

**RLOracle add_pipeline** uses only the canonical path: one topology, no extra Oracle units. Code for the step handler and the response (observation/reward/done) is attached to the canonical `step_driver` and `step_rewards` units via code_blocks.

---

## Breakdown: RLOracle add_pipeline (canonical only)

When `add_pipeline` with type `RLOracle` is applied:

1. **Canonical topology only** — `_ensure_canonical_topology(..., include_http_endpoints=True)` creates and wires:
   - **Join** (id `collector`), **Switch** (id `switch`), **StepDriver** (id `step_driver`), **Split**, **StepRewards** (id `step_rewards`), **http_in**, **step_router**, **http_response**.
   - All connections are the canonical ones (obs → Join → StepRewards, StepDriver → Split & StepRewards, step_router → StepDriver & Switch, StepRewards → http_response, Switch → action_targets).

2. **Code_blocks only** — `render_oracle_code_blocks_for_canonical(adapter_config, ...)` returns two code_blocks (no new units):
   - **`step_driver`**: Oracle step-driver code (handles `/step` request, parses action, drives Switch and loop).
   - **`step_rewards`**: Oracle collector code (observation from Join, reward/done, payload to http_response).

So there is **one** step driver unit and **one** observation→response path (Join → StepRewards → http_response). Export to Node-RED/n8n/PyFlow maps these canonical units and their code_blocks to the target editor.

### Connections (all from canonical topology)

| From | To | Note |
|------|----|------|
| `obs_i` | Join (`collector`) | For each observation_source_id |
| Join | StepRewards | observation port |
| StepDriver | StepRewards | trigger (port 2 → 1) |
| StepDriver | Split | then Split → simulators |
| Switch | `action_target_i` | For each action_target_id |
| http_in | step_router | |
| step_router | StepDriver | trigger |
| step_router | Switch | action input from client |
| StepRewards | http_response | payload |

No Oracle-specific units or connections. Join is the observation aggregator; StepRewards holds the collector (reward/response) code and feeds http_response.

---

## AI model pipeline wiring

     observation_1 ──┐
     observation_n ──┴──► Join ──► RLAgent/LLMAgent ──► Switch ──┬──► action_target_1
                                                                 ├──► action_target_2
                                                                 └──► action_target_n

## RLOracle pipeline wiring (canonical only)

    observation_1 ──┐
    observation_n ──┴──► Join ──► StepRewards ──► http_response  (observations/reward/done to client)

    http_in (external) ──► step_router ──┬──► StepDriver ──┬──► Split ──┬──► simulator_1
                                         |                 |            ├──► simulator_2
                                         |                 |            └──► simulator_n
                                         |                 └──► StepRewards (trigger)
                                         └──► Switch ──┬──► action_target_1
                                                       ├──► action_target_2
                                                       └──► action_target_n

## RLGym pipeline wiring
  
    observation_1 ──┐
    observation_n ──┴──► Join ──────────────► StepRewards
                                                 ▲
                    StepDriver ──┬───────────────┘ 
                  (env trigger)  └──► Split ──┬──► simulator_1
                                              ├──► simulator_2
                                              └──► simulator_n

    (external policy / training loop) ──► Switch ──┬──► action_target_1
                                                   ├──► action_target_2
                                                   └──► action_target_n
