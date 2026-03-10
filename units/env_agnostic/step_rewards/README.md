# StepRewards

Canonical observation, reward, and done for the step. Receives observation from Join and trigger from the executor; outputs observation (pass-through), reward, done, and a payload (e.g. for HTTP response).

## Purpose

Single unit that combines observation pass-through, step counting, done (max_steps), and reward computation. The executor injects trigger (reset/step) and optionally full graph outputs for the rewards DSL. Used in both inline (RLGym) and external (RLOracle) flows; payload is sent to HttpResponse when HTTP is present.

## Interface

| Port / Param   | Direction | Type   | Description                                    |
|----------------|-----------|--------|------------------------------------------------|
| **Inputs**     | observation | vector | From Join                              |
|                | trigger   | any    | Injected (reset/step)                         |
|                | outputs   | any    | Optional; full graph outputs for rewards DSL   |
| **Outputs**    | observation | vector | Pass-through                             |
|                | reward    | float  | Computed reward                              |
|                | done      | bool   | True when step_count >= max_steps             |
|                | payload   | any    | {observation, reward, done} for http_response |
| **Params**     | config    | —      | `max_steps` (default 600), `reward` (RewardsConfig) |

## Example

**Params:** `{"max_steps": 100}`

**Inputs:** `{"observation": [0.5, 0.8], "trigger": "step"}`  
**Outputs:** `{"observation": [0.5, 0.8], "reward": 0.0, "done": false, "payload": {"observation": [0.5, 0.8], "reward": 0.0, "done": false}}`

With `reward` config (rewards DSL), reward is computed from formula/rules using observation, step_count, max_steps, and optional goal/outputs.
