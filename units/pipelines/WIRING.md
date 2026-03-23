# Canonical pipelines wiring schemas

Canonical pipelines use a small set of units and fixed wiring rules so that observation sources, agents, and action targets plug together in a consistent way.

For LLM models, both user message and all components of the system prompt are merged through the **Aggregate** unit an then assembled by the **Promt** unit, which leverages {placeholders} to put together the final prompt and send it to LLM; action JSON outputs are parsed by the **ProcessAgent** unit all the acction targets are suppoosed to be connected to.

## LLMSet pipeline wiring

         (Inject) user_message --+
    (Inject) follow-up-context --+-> Aggregate -> Prompt -> LLMAgent -> ProcessAgent --+-> action_target_1
                                                                                       |-> action_target_2
                                                                                       |-> action_target_n

For RL models bservations are always merged through the **Join** unit before going into an agent or reward logic; action outputs are always fanned out through the **Switch** unit to the targets.

## RL model pipeline wiring

     observation_1 --+
     observation_n --+-> Join -> RLAgent -> Switch --+-> action_target_1
                                                              |-> action_target_2
                                                              |-> action_target_n

## RLOracle pipeline wiring

    observation_1 --+
    observation_n --+-> Join -> StepRewards -> http_response  (observations/reward/done to client)

    http_in (external) -> step_router --+-> StepDriver --+-> Split --+-> simulator_1
                                        |                |           |-> simulator_2
                                        |                |           |-> simulator_n
                                        |                |-> StepRewards (trigger)
                                        |-> Switch --+-> action_target_1
                                                     |-> action_target_2
                                                     |-> action_target_n

## RLGym pipeline wiring
  
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
