
from core.graph.utils import (
    add_connection,
    add_unit,
    default_workflow_designer_prompt_path,
)
from core.normalizer.system_comments import (
    PIPELINE_WIRING_BASE,
    PIPELINE_WIRING_LLMAGENT,
    PIPELINE_WIRING_PREFIX_LLMAGENT,
    PIPELINE_WIRING_PREFIX_RLAGENT,
    PIPELINE_WIRING_PREFIX_RLGYM,
    PIPELINE_WIRING_PREFIX_RLORACLE,
)
from core.schemas.agent_node import (
    RL_GYM_NODE_TYPE,
)
from core.schemas.process_graph import Connection, Unit
from units.registry import get_type_by_role

# Canonical topology unit ids (created automatically when adding RLAgent/LLMAgent or RLOracle)
CANONICAL_JOIN_ID = "collector"
CANONICAL_SWITCH_ID = "switch"
_CANONICAL_STEP_DRIVER_ID = "step_driver"
_CANONICAL_SPLIT_ID = "split"
_CANONICAL_STEP_REWARDS_ID = "step_rewards"
_CANONICAL_HTTP_IN_ID = "http_in"
_CANONICAL_HTTP_RESPONSE_ID = "http_response"
# Front switch (same type as Switch): 1 input from http_in, 2 outputs: 0 → step_driver, 1 → switch (action demux)
_CANONICAL_STEP_ROUTER_ID = "step_router"

# Start port index for simulator units (Split output -> unit start input)
_START_PORT_BY_TYPE: dict[str, str] = {"Source": "0", "Tank": "5"}


# LLM pipeline: Obs. sources -> Merge -> Prompt -> LLMAgent -> Switch -> action targets
_CANONICAL_MERGE_LLM_ID = "merge_llm"
_CANONICAL_PROMPT_LLM_ID = "prompt_llm"
_CANONICAL_PARSER_LLM_ID = "parser"

# RL pipeline
def ensure_canonical_topology(
    units: list[Unit],
    connections: list[Connection],
    obs_ids: list[str],
    act_ids: list[str],
    *,
    include_training_units: bool = True,
    include_http_endpoints: bool = False,
) -> None:
    """Ensure canonical units exist and are wired.

    RL training pipeline:
        observations -> Join -> ...
        StepDriver -> Split -> simulators
        Join + StepDriver -> StepRewards

    Short topology:
        observations -> Join -> Agent -> Switch -> actions

    HTTP topology is added only when ``include_http_endpoints`` is true.
    """

    # Env-agnostic units must be registered before resolving canonical types.
    try:
        from units.register_env_agnostic import register_env_agnostic_units

        register_env_agnostic_units()
    except (ImportError, AttributeError):
        return

    type_join = get_type_by_role("join")
    type_switch = get_type_by_role("switch")
    type_step_driver = get_type_by_role("step_driver")
    type_step_rewards = get_type_by_role("step_rewards")
    type_split = get_type_by_role("split")
    type_http_in = get_type_by_role("http_in")
    type_http_response = get_type_by_role("http_response")

    if not type_join or not type_switch or not type_step_driver:
        return

    unit_by_id: dict[str, Unit] = {unit.id: unit for unit in units}

    # Join: observation sources -> collector in_0, in_1, ...
    join_was_added = CANONICAL_JOIN_ID not in unit_by_id
    _ = add_unit(
        units,
        CANONICAL_JOIN_ID,
        type_join,
        params={"num_inputs": max(len(obs_ids), 1)},
    )

    if join_was_added:
        for index, source_id in enumerate(sorted(obs_ids)):
            if source_id in unit_by_id:
                _ = add_connection(
                    connections,
                    source_id,
                    CANONICAL_JOIN_ID,
                    from_port="0",
                    to_port=str(index),
                )

    # Switch: switch out_0, out_1, ... -> action targets
    switch_was_added = CANONICAL_SWITCH_ID not in unit_by_id
    _ = add_unit(
        units,
        CANONICAL_SWITCH_ID,
        type_switch,
        params={"num_outputs": max(len(act_ids), 1)},
    )

    if switch_was_added:
        for index, target_id in enumerate(sorted(act_ids)):
            if target_id in unit_by_id:
                _ = add_connection(
                    connections,
                    CANONICAL_SWITCH_ID,
                    target_id,
                    from_port=str(index),
                    to_port="0",
                )

    if include_training_units:
        # StepDriver
        _ = add_unit(
            units,
            _CANONICAL_STEP_DRIVER_ID,
            type_step_driver,
            params={},
        )

        # Split: StepDriver -> Split -> simulators
        simulator_ids = [
            unit_id
            for unit_id, unit in unit_by_id.items()
            if unit.type in ("Source", "Tank")
        ]

        if type_split:
            split_was_added = _CANONICAL_SPLIT_ID not in unit_by_id
            _ = add_unit(
                units,
                _CANONICAL_SPLIT_ID,
                type_split,
                params={"num_outputs": max(len(simulator_ids), 1)},
            )

            if split_was_added:
                _ = add_connection(
                    connections,
                    _CANONICAL_STEP_DRIVER_ID,
                    _CANONICAL_SPLIT_ID,
                    from_port="0",
                    to_port="0",
                )

                for index, simulator_id in enumerate(sorted(simulator_ids)):
                    simulator = unit_by_id[simulator_id]
                    to_port = _START_PORT_BY_TYPE.get(simulator.type, "0")

                    _ = add_connection(
                        connections,
                        _CANONICAL_SPLIT_ID,
                        simulator_id,
                        from_port=str(index),
                        to_port=to_port,
                    )

        # StepRewards: Join -> observation and StepDriver -> trigger
        if type_step_rewards:
            _ =  add_unit(
                units,
                _CANONICAL_STEP_REWARDS_ID,
                type_step_rewards,
                params={"max_steps": 600},
            )

            _ = add_connection(
                connections,
                CANONICAL_JOIN_ID,
                _CANONICAL_STEP_REWARDS_ID,
                from_port="observation",
                to_port="observation",
            )
            _ = add_connection(
                connections,
                _CANONICAL_STEP_DRIVER_ID,
                _CANONICAL_STEP_REWARDS_ID,
                from_port="2",
                to_port="1",
            )

    # HTTP endpoints: opt-in external access only.
    if include_http_endpoints and type_http_in and type_http_response:
        _ = add_unit(
            units,
            _CANONICAL_HTTP_IN_ID,
            type_http_in,
            params={},
        )
        _ = add_unit(
            units,
            _CANONICAL_STEP_ROUTER_ID,
            type_switch,
            params={"num_outputs": 2},
        )
        _ = add_unit(
            units,
            _CANONICAL_HTTP_RESPONSE_ID,
            type_http_response,
            params={},
        )

        # http_in -> step_router
        _ = add_connection(
            connections,
            _CANONICAL_HTTP_IN_ID,
            _CANONICAL_STEP_ROUTER_ID,
            from_port="0",
            to_port="0",
        )

        # step_router -> StepDriver / action Switch
        _ = add_connection(
            connections,
            _CANONICAL_STEP_ROUTER_ID,
            _CANONICAL_STEP_DRIVER_ID,
            from_port="0",
            to_port="0",
        )
        _ = add_connection(
            connections,
            _CANONICAL_STEP_ROUTER_ID,
            CANONICAL_SWITCH_ID,
            from_port="1",
            to_port="0",
        )

        # Step response
        if _CANONICAL_STEP_REWARDS_ID in unit_by_id:
            _ = add_connection(
                connections,
                _CANONICAL_STEP_REWARDS_ID,
                _CANONICAL_HTTP_RESPONSE_ID,
                from_port="payload",
                to_port="payload",
            )
        else:
            _ = add_connection(
                connections,
                _CANONICAL_STEP_DRIVER_ID,
                _CANONICAL_HTTP_RESPONSE_ID,
                from_port="1",
                to_port="0",
            )


# LLM pipeline
def ensure_llm_canonical_topology(
    units: list[Unit],
    connections: list[Connection],
    obs_ids: list[str],
    act_ids: list[str],
    llm_agent_id: str,
    *,
    prompt_template_path: str | None = None,
) -> None:
    """Ensure the canonical LLM workflow topology exists and is wired.

    Topology::

        observation sources -> Merge -> Prompt -> LLMAgent
        LLMAgent -> ProcessAgent -> action targets

    This workflow does not use a Switch, HTTP endpoints, or
    apply_edits/graph_diff processing.
    """
    if prompt_template_path is None:
        prompt_template_path = default_workflow_designer_prompt_path()

    # Env-agnostic units must be registered before resolving canonical types.
    try:
        from units.register_env_agnostic import register_env_agnostic_units

        register_env_agnostic_units()
    except (ImportError, AttributeError):
        return

    type_merge = get_type_by_role("merge")
    type_prompt = get_type_by_role("prompt")
    type_process_agent = get_type_by_role("process_agent")

    if not type_merge or not type_prompt or not type_process_agent:
        return

    unit_by_id: dict[str, Unit] = {unit.id: unit for unit in units}

    # Merge: observation sources -> in_0, in_1, ...
    observation_ids = sorted(obs_ids)[:8]
    num_inputs = max(len(observation_ids), 1)

    merge_was_added = _CANONICAL_MERGE_LLM_ID not in unit_by_id
    _ = add_unit(
        units,
        _CANONICAL_MERGE_LLM_ID,
        type_merge,
        params={
            "num_inputs": num_inputs,
            "keys": (
                list(observation_ids)
                if observation_ids
                else [f"in_{index}" for index in range(num_inputs)]
            ),
        },
    )

    if merge_was_added:
        for index, source_id in enumerate(observation_ids):
            if source_id in unit_by_id:
                _ = add_connection(
                    connections,
                    source_id,
                    _CANONICAL_MERGE_LLM_ID,
                    from_port="0",
                    to_port=str(index),
                )

    # Prompt: Merge -> Prompt
    prompt_was_added = _CANONICAL_PROMPT_LLM_ID not in unit_by_id
    _ = add_unit(
        units,
        _CANONICAL_PROMPT_LLM_ID,
        type_prompt,
        params={"template_path": prompt_template_path},
    )

    if prompt_was_added:
        _ = add_connection(
            connections,
            _CANONICAL_MERGE_LLM_ID,
            _CANONICAL_PROMPT_LLM_ID,
            from_port="data",
            to_port="data",
        )

    # Prompt -> LLMAgent
    if prompt_was_added and llm_agent_id in unit_by_id:
        _ = add_connection(
            connections,
            _CANONICAL_PROMPT_LLM_ID,
            llm_agent_id,
            from_port="system_prompt",
            to_port="system_prompt",
        )

    # ProcessAgent: LLMAgent -> edits -> action targets
    process_agent_was_added = _CANONICAL_PARSER_LLM_ID not in unit_by_id
    _ = add_unit(
        units,
        _CANONICAL_PARSER_LLM_ID,
        type_process_agent,
        params={},
    )

    if process_agent_was_added and llm_agent_id in unit_by_id:
        _ = add_connection(
            connections,
            llm_agent_id,
            _CANONICAL_PARSER_LLM_ID,
            from_port="action",
            to_port="action",
        )

    if process_agent_was_added:
        for target_id in sorted(act_ids):
            if target_id in unit_by_id:
                _ = add_connection(
                    connections,
                    _CANONICAL_PARSER_LLM_ID,
                    target_id,
                    from_port="edits",
                    to_port="0",
                )


def pipeline_wiring_guideline_message(pipeline_type: str) -> str:
    """Return a short wiring guideline message for the given pipeline type (text from normalizer.system_comments)."""
    if pipeline_type == "RLOracle":
        return f"{PIPELINE_WIRING_PREFIX_RLORACLE} {PIPELINE_WIRING_BASE}"
    if pipeline_type == RL_GYM_NODE_TYPE:  # "RLGym"
        return f"{PIPELINE_WIRING_PREFIX_RLGYM} {PIPELINE_WIRING_BASE}"
    if pipeline_type == "RLSet":
        return f"{PIPELINE_WIRING_PREFIX_RLAGENT} {PIPELINE_WIRING_BASE}"
    if pipeline_type == "LLMSet":
        return f"{PIPELINE_WIRING_PREFIX_LLMAGENT} {PIPELINE_WIRING_LLMAGENT}"
    return f"{pipeline_type} Pipeline Wiring Guidelines! {PIPELINE_WIRING_BASE}"
