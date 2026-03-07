# Canonical pipelines wiring schemas

Canonical pipelines use a small set of units and fixed wiring rules so that observation sources, agents, and action targets plug together in a consistent way. Observations are always merged through a **Join** unit before going into an agent or reward logic; action outputs are always fanned out through a **Switch** unit to the targets.

1. Always connect the observation sources through the Join unit:

    observation_1 --+
    observation_n --+-> Join

2. Always connect the action targets through the Switch unit:

 Switch --+-> action_target_1
          |-> action_target_2
          |-> action_target_n

---

## AI model pipeline wiring (full)

     observation_1 --+
     observation_n --+-> Join -> RLAgent/LLMAgent -> Switch --+-> action_target_1
                                                              |-> action_target_2
                                                              |-> action_target_n

## RLOracle pipeline wiring (full)

    observation_1 --+
    observation_n --+-> Join -> StepRewards -> http_response  (observations/reward/done to client)

    http_in (external) -> step_router --+-> StepDriver --+-> Split --+-> simulator_1
                                        |                |           |-> simulator_2
                                        |                |           |-> simulator_n
                                        |                |-> StepRewards (trigger)
                                        |-> Switch --+-> action_target_1
                                                     |-> action_target_2
                                                     |-> action_target_n

## RLGym pipeline wiring (full)
  
    observation_1 --+
    observation_n --+-> Join ----------------> StepRewards
                                                 ^
                    StepDriver --+---------------'
                  (env trigger)  |-> Split --+-> simulator_1
                                              |-> simulator_2
                                              |-> simulator_n

    (external policy / training loop) -> Switch --+-> action_target_1
                                                  |-> action_target_2
                                                  |-> action_target_n
