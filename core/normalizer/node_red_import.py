"""
Node-RED flow import: map Node-RED JSON to canonical process graph dict.
Supports multi-tab (flows[] or tab/group nodes with z) and subflows (nested definition preserved).

Port resolution (Node-RED semantics):
- wires[i] = list of destination node IDs for output port i (index = port).
- Single port: wires = [["n1","n2"]]; multiple: wires = [["n1"],["n2"]].
- Input: one logical input per node carrying msg; input_ports name "msg", type JavaScript(object).
- Function nodes: outputs/return array index maps to port index (return [msg,null] → port 0 gets msg, port 1 skipped).
- Port type is always JavaScript(object) for msg; output port names use msg property paths (e.g. msg.parts, msg.payload[0].feedback).
"""

import copy
import re

from core.normalizer.system_comments import (
    NODE_RED_SYSTEM_COMMENT,
)
from core.schemas.primitives import (
    JsonArray,
    JsonObject,
    JsonValue,
    is_json_array,
    is_json_object,
)

# Keys that define graph structure; do not store in unit.params (handled separately).
_NODE_RED_STRUCTURE_KEYS = frozenset(
    {"id", "type", "z", "x", "y", "wires", "name", "label"}
)

# Port type for Node-RED message object (msg is a JavaScript object).
_NODE_RED_MSG_TYPE = "JavaScript(object)"


def _node_red_output_port_count(node: JsonObject) -> int:
    """Return the number of output ports defined by wires."""
    wires = node.get("wires")
    if not is_json_array(wires):
        return 0

    return len(wires)


def _node_red_switch_output_ports(
    node: JsonObject,
    num_ports: int,
) -> list[JsonValue] | None:
    """
    Return output port specifications for a switch node.

    Rule-based switches map rules[i] to output port i. Parameter-based
    switches, such as time-range-switch, use parameter values as port names.
    """
    rules = node.get("rules")

    if is_json_array(rules) and len(rules) == num_ports:
        output_ports: list[JsonValue] = []

        for rule in rules:
            if not is_json_object(rule):
                output_ports.append(
                    {
                        "name": str(len(output_ports)),
                        "type": _NODE_RED_MSG_TYPE,
                    }
                )
                continue

            rule_type = rule.get("t") or "eq"

            if rule_type == "else":
                output_ports.append(
                    {
                        "name": "else",
                        "type": _NODE_RED_MSG_TYPE,
                    }
                )
                continue

            value = rule.get("v", "")
            value_2 = rule.get("v2")

            if value_2 is not None and str(value_2) != "":
                label = f"Rule: {rule_type} {value}..{value_2}"
            elif value != "":
                label = f"Rule: {rule_type} {value}"
            else:
                label = f"Rule: {rule_type}"

            output_ports.append(
                {
                    "name": label.strip(),
                    "type": _NODE_RED_MSG_TYPE,
                }
            )

        if output_ports:
            return output_ports

    if (
        num_ports == 2
        and node.get("startTime") is not None
        and node.get("endTime") is not None
    ):
        return [
            {
                "name": str(node.get("startTime", "startTime")),
                "type": _NODE_RED_MSG_TYPE,
            },
            {
                "name": str(node.get("endTime", "endTime")),
                "type": _NODE_RED_MSG_TYPE,
            },
        ]

    return None


def _node_red_trigger_output_ports(
    node: JsonObject,
    num_ports: int,
) -> list[JsonValue] | None:
    """
    Return output port specifications for a trigger node.

    With one output, the port represents the immediate operation. With two
    outputs, the ports represent the immediate and delayed operations.
    """
    if num_ports not in (1, 2):
        return None

    operation_1 = node.get("op1")
    operation_2 = node.get("op2")

    ports: list[JsonValue] = [
        {
            "name": (
                str(operation_1)
                if operation_1 is not None
                else "immediate"
            ),
            "type": _NODE_RED_MSG_TYPE,
        }
    ]

    if num_ports == 2:
        ports.append(
            {
                "name": (
                    str(operation_2)
                    if operation_2 is not None
                    else "delayed"
                ),
                "type": _NODE_RED_MSG_TYPE,
            }
        )

    return ports


def _node_red_inject_output_port() -> JsonObject:
    """
    Return the output port specification for an inject node.

    Inject nodes always produce one message through ``msg.payload``.
    """
    return {
        "name": "msg.payload",
        "type": _NODE_RED_MSG_TYPE,
    }


def _node_red_parse_msg_property_paths(
    func_source: str,
) -> list[str]:
    """
    Extract unique msg property paths in order of first occurrence.

    For example, ``msg.payload[0].feedback`` becomes the port name
    ``msg.payload[0].feedback``.
    """
    if not func_source:
        return []

    pattern = r"msg\.(\w+(?:\[\d+\])?(?:\.\w+)*)"

    seen: set[str] = set()
    result: list[str] = []

    for match in re.finditer(pattern, func_source):
        path = match.group(1)
        full_path = f"msg.{path}"

        if full_path not in seen:
            seen.add(full_path)
            result.append(full_path)

    return result


def _node_red_nodes_list(
    raw: JsonValue,
) -> list[JsonObject]:
    """
    Extract a flat list of Node-RED nodes.

    Supported formats include:

    - A root node array.
    - ``{"nodes": [...]}``.
    - ``{"flows": [{"nodes": [...]}]}``.
    - ``{"flows": [[...]]}``.
    - ``{"flow": {"nodes": [...]}}``.
    - ``{"tab": {"nodes": [...]}}``.
    - ``{"flow": [...]}``.
    - ``{"tab": [...]}``.
    """
    if is_json_array(raw):
        return [
            node
            for node in raw
            if is_json_object(node)
        ]

    if not is_json_object(raw):
        return []

    nodes = raw.get("nodes")
    if is_json_array(nodes):
        return [
            node
            for node in nodes
            if is_json_object(node)
        ]

    flows = raw.get("flows")
    if is_json_array(flows) and flows:
        first_flow = flows[0]

        if is_json_object(first_flow):
            flow_nodes = first_flow.get("nodes")
            if is_json_array(flow_nodes):
                return [
                    node
                    for node in flow_nodes
                    if is_json_object(node)
                ]

        if is_json_array(first_flow):
            return [
                node
                for node in first_flow
                if is_json_object(node)
            ]

    for key in ("flow", "tab"):
        tab = raw.get(key)

        if is_json_object(tab):
            tab_nodes = tab.get("nodes")
            if is_json_array(tab_nodes):
                return [
                    node
                    for node in tab_nodes
                    if is_json_object(node)
                ]

        # Library / gist format: "flow" or "tab" is the nodes array.
        if is_json_array(tab):
            return [
                node
                for node in tab
                if is_json_object(node)
            ]

    return []


def _node_red_flows_list(
    raw: JsonObject,
) -> list[JsonObject] | None:
    """
    Return flow definitions for multi-tab imports.

    Each returned object contains the original flow definition, or a
    synthesized definition for a flow represented directly as a node array.
    """
    flows = raw.get("flows")

    if not is_json_array(flows) or not flows:
        return None

    output: list[JsonObject] = []

    for index, flow in enumerate(flows):
        if is_json_object(flow):
            nodes = flow.get("nodes")

            if is_json_array(nodes):
                output.append(flow)

            continue

        if is_json_array(flow):
            output.append(
                {
                    "id": f"flow_{index}",
                    "label": None,
                    "nodes": [
                        node
                        for node in flow
                        if is_json_object(node)
                    ],
                }
            )

    return output or None

def _node_red_units_connections_from_nodes(
    nodes: list[JsonObject],
) -> tuple[JsonArray, JsonArray, JsonArray]:
    """
    Build units, connections, and code blocks from Node-RED flow nodes.

    Tab and group nodes are excluded from the returned units.
    """
    unit_ids: set[str] = set()
    units: JsonArray = []
    code_blocks: JsonArray = []

    for node in nodes:
        node_id_value = node.get("id") or node.get("name")
        if node_id_value is None:
            continue

        node_id = str(node_id_value)
        raw_type = node.get("type")

        if (
            isinstance(raw_type, str)
            and raw_type.lower() in ("tab", "group")
        ):
            continue

        node_type = str(
            node.get("unitType")
            or node.get("processType")
            or raw_type
            or "node"
        )

        unit_ids.add(node_id)

        params: JsonObject = {}

        for key, value in node.items():
            if key in _NODE_RED_STRUCTURE_KEYS:
                continue

            if key in ("func", "code", "template", "command"):
                continue

            if value is None:
                continue

            params[key] = copy.deepcopy(value)

        controllable_value = node.get("controllable")
        controllable = (
            True
            if controllable_value is None
            else bool(controllable_value)
        )

        if (
            isinstance(raw_type, str)
            and raw_type.lower() == "trigger"
        ):
            controllable = True

        if (
            isinstance(raw_type, str)
            and raw_type.lower().endswith(" in")
        ):
            controllable = False

        unit: JsonObject = {
            "id": node_id,
            "type": node_type,
            "controllable": controllable,
            "params": params,
        }

        label_or_name = node.get("label") or node.get("name")
        if (
            isinstance(label_or_name, str)
            and label_or_name.strip()
        ):
            unit["name"] = label_or_name.strip()

        # Preserve subflow definitions for round-trip support.
        if (
            isinstance(raw_type, str)
            and raw_type.lower() == "subflow"
        ):
            subflow_definition: JsonObject = {}

            for key in ("in", "out", "configs", "nodes"):
                value = node.get(key)
                if value is not None:
                    subflow_definition[key] = copy.deepcopy(value)

            for key in ("name", "info", "env", "meta"):
                value = node.get(key)
                if value is not None:
                    subflow_definition[key] = copy.deepcopy(value)

            if subflow_definition:
                params["_node_red_subflow"] = subflow_definition

        num_outputs = _node_red_output_port_count(node)

        if num_outputs == 1:
            if (
                isinstance(raw_type, str)
                and raw_type.lower() == "inject"
            ):
                unit["output_ports"] = [
                    _node_red_inject_output_port()
                ]

            elif (
                isinstance(raw_type, str)
                and raw_type.lower() in ("split", "sort")
            ):
                unit["output_ports"] = [
                    {
                        "name": "msg.parts",
                        "type": _NODE_RED_MSG_TYPE,
                    }
                ]

            elif raw_type == "function":
                function_source = node.get("func") or ""

                paths = (
                    _node_red_parse_msg_property_paths(function_source)
                    if isinstance(function_source, str)
                    else []
                )

                unit["output_ports"] = [
                    {
                        "name": (
                            paths[0]
                            if paths
                            else "msg.payload"
                        ),
                        "type": _NODE_RED_MSG_TYPE,
                    }
                ]

            elif (
                isinstance(raw_type, str)
                and raw_type.lower() == "trigger"
            ):
                trigger_ports = _node_red_trigger_output_ports(
                    node,
                    1,
                )

                unit["output_ports"] = (
                    trigger_ports
                    if trigger_ports
                    else [
                        {
                            "name": "msg.payload",
                            "type": _NODE_RED_MSG_TYPE,
                        }
                    ]
                )

            else:
                unit["output_ports"] = [
                    {
                        "name": "msg.payload",
                        "type": _NODE_RED_MSG_TYPE,
                    }
                ]

        elif num_outputs > 1:
            port_specs: list[JsonValue] | None = None

            if (
                isinstance(raw_type, str)
                and "switch" in raw_type.lower()
            ):
                port_specs = _node_red_switch_output_ports(
                    node,
                    num_outputs,
                )

            elif (
                isinstance(raw_type, str)
                and raw_type.lower() == "trigger"
            ):
                port_specs = _node_red_trigger_output_ports(
                    node,
                    num_outputs,
                )

            if port_specs is not None:
                unit["output_ports"] = port_specs

            else:
                port_names = [
                    str(index)
                    for index in range(num_outputs)
                ]

                if raw_type == "function":
                    function_source = node.get("func") or ""

                    if isinstance(function_source, str):
                        paths = _node_red_parse_msg_property_paths(
                            function_source
                        )

                        if paths:
                            port_names = [
                                (
                                    paths[index]
                                    if index < len(paths)
                                    else "msg.payload"
                                )
                                for index in range(num_outputs)
                            ]
                        else:
                            port_names = [
                                "msg.payload"
                                for _ in range(num_outputs)
                            ]

                unit["output_ports"] = [
                    {
                        "name": name,
                        "type": _NODE_RED_MSG_TYPE,
                    }
                    for name in port_names
                ]

        units.append(unit)

        source = (
            node.get("func")
            or node.get("code")
            or node.get("template")
            or node.get("command")
        )

        if isinstance(source, str) and source.strip():
            language = (
                "shell"
                if node_type == "exec"
                else "javascript"
            )

            code_blocks.append(
                {
                    "id": node_id,
                    "language": language,
                    "source": source,
                }
            )

    connections: JsonArray = []

    for node in nodes:
        from_value = node.get("id") or node.get("name")
        if from_value is None:
            continue

        from_id = str(from_value)
        if from_id not in unit_ids:
            continue

        wires = node.get("wires")
        if not is_json_array(wires):
            continue

        for output_index, output_targets in enumerate(wires):
            if not is_json_array(output_targets):
                continue

            for target in output_targets:
                if target is None:
                    continue

                to_id = str(target)
                if to_id not in unit_ids:
                    continue

                connections.append(
                    {
                        "from": from_id,
                        "to": to_id,
                        "from_port": str(output_index),
                        "to_port": "0",
                    }
                )

    def _input_port_name(unit_type: JsonValue) -> str:
        if (
            isinstance(unit_type, str)
            and unit_type.lower() in ("join", "sort")
        ):
            return "msg.parts"

        return "msg"

    to_ids_with_input: set[str] = set()

    for connection_value in connections:
        if not is_json_object(connection_value):
            continue

        to_value = connection_value.get("to")
        if isinstance(to_value, str):
            to_ids_with_input.add(to_value)

    for unit_value in units:
        if not is_json_object(unit_value):
            continue

        params_value = unit_value.get("params")

        unit_params: JsonObject = {}
        if is_json_object(params_value):
            unit_params = params_value

        num_inputs = unit_params.get("inputs")
        input_name = _input_port_name(unit_value.get("type"))
        unit_id = unit_value.get("id")

        if not isinstance(unit_id, str):
            continue

        if num_inputs is not None:
            try:
                if isinstance(num_inputs, bool):
                    raise TypeError("Boolean input count is invalid")

                if isinstance(num_inputs, (int, float, str)):
                    input_count = int(num_inputs)
                else:
                    raise TypeError(
                        "Input count must be a number or numeric string"
                    )

                if input_count < 0:
                    raise ValueError(
                        "Input count cannot be negative"
                    )

                if input_count == 0:
                    unit_value["input_ports"] = []
                else:
                    unit_value["input_ports"] = [
                        {
                            "name": input_name,
                            "type": _NODE_RED_MSG_TYPE,
                        }
                        for _ in range(input_count)
                    ]

            except (TypeError, ValueError, OverflowError):
                if unit_id in to_ids_with_input:
                    unit_value["input_ports"] = [
                        {
                            "name": input_name,
                            "type": _NODE_RED_MSG_TYPE,
                        }
                    ]

        elif unit_id in to_ids_with_input:
            unit_value["input_ports"] = [
                {
                    "name": input_name,
                    "type": _NODE_RED_MSG_TYPE,
                }
            ]

    return units, connections, code_blocks


def normalize_disabled(value: JsonValue) -> JsonValue:
    if value is None:
        return None

    return bool(value)


def to_canonical_dict(
    raw: JsonValue,
) -> JsonObject:
    """
    Map Node-RED flow JSON to the canonical process graph dictionary.

    Supports multi-tab imports. The top-level ``units`` and ``connections``
    mirror the first tab for backward compatibility.
    """
    env_type = ""

    if is_json_object(raw):
        environment_value = (
            raw.get("environment_type")
            or raw.get("process_environment_type")
            or ""
        )
        env_type = str(environment_value).strip()

    all_code_blocks: JsonArray = []
    tab_meta_for_origin: JsonArray = []
    tabs_list: JsonArray = []
    layout: JsonObject = {}

    primary_units: JsonArray = []
    primary_connections: JsonArray = []

    def append_tab(
        tab_id: str,
        label: JsonValue,
        disabled: JsonValue,
        units: JsonArray,
        connections: JsonArray,
    ) -> None:
        tab_metadata: JsonObject = {
            "id": tab_id,
            "label": label,
            "disabled": disabled,
        }
        tab_meta_for_origin.append(tab_metadata)

        tab_data: JsonObject = {
            "id": tab_id,
            "label": label,
            "disabled": disabled,
            "units": units,
            "connections": connections,
        }
        tabs_list.append(tab_data)

    def set_primary_from_first_tab() -> None:
        nonlocal primary_units
        nonlocal primary_connections

        if not tabs_list:
            return

        first_tab_value = tabs_list[0]

        if not is_json_object(first_tab_value):
            return

        units_value: JsonValue = first_tab_value.get("units", [])
        connections_value: JsonValue = first_tab_value.get(
            "connections",
            [],
        )

        if is_json_array(units_value):
            primary_units = units_value

        if is_json_array(connections_value):
            primary_connections = connections_value

    flows_list = (
        _node_red_flows_list(raw)
        if is_json_object(raw)
        else None
    )

    if flows_list is not None:
        for index, flow in enumerate(flows_list):
            tab_id = str(flow.get("id") or f"flow_{index}")

            label = flow.get("label")
            if isinstance(label, str) and not label.strip():
                label = None

            tab_disabled = normalize_disabled(flow.get("disabled"))

            raw_nodes = flow.get("nodes")

            if is_json_array(raw_nodes):
                nested_flow_nodes: list[JsonObject] = [
                    node
                    for node in raw_nodes
                    if is_json_object(node)
                ]

                for node in nested_flow_nodes:
                    node_id_value = node.get("id") or node.get("name")
                    x = node.get("x")
                    y = node.get("y")

                    if (
                        node_id_value is None
                        or x is None
                        or y is None
                        or isinstance(x, bool)
                        or isinstance(y, bool)
                        or not isinstance(x, (str, int, float))
                        or not isinstance(y, (str, int, float))
                    ):
                        continue

                    try:
                        layout[str(node_id_value)] = {
                            "x": float(x),
                            "y": float(y),
                        }
                    except (
                        TypeError,
                        ValueError,
                        OverflowError,
                    ):
                        pass

                (
                    units,
                    connections,
                    code_blocks,
                ) = _node_red_units_connections_from_nodes(
                    nested_flow_nodes,
                )

                for code_block in code_blocks:
                    if is_json_object(code_block):
                        all_code_blocks.append(code_block)

                append_tab(
                    tab_id=tab_id,
                    label=label,
                    disabled=tab_disabled,
                    units=units,
                    connections=connections,
                )

            else:
                append_tab(
                    tab_id=tab_id,
                    label=label,
                    disabled=tab_disabled,
                    units=[],
                    connections=[],
                )

        set_primary_from_first_tab()

    else:
        nodes = _node_red_nodes_list(raw)

        tab_nodes_ordered: list[JsonObject] = []
        flow_nodes: list[JsonObject] = []

        for node in nodes:
            raw_type = node.get("type")

            if (
                isinstance(raw_type, str)
                and raw_type.lower() in ("tab", "group")
            ):
                tab_nodes_ordered.append(node)
            else:
                flow_nodes.append(node)

        if not tab_nodes_ordered:
            (
                primary_units,
                primary_connections,
                node_code_blocks,
            ) = _node_red_units_connections_from_nodes(flow_nodes)

            all_code_blocks.extend(node_code_blocks)

            append_tab(
                tab_id="flow_main",
                label="Process",
                disabled=None,
                units=primary_units,
                connections=primary_connections,
            )

        else:
            tab_id_order = [
                str(node.get("id") or node.get("name"))
                for node in tab_nodes_ordered
                if node.get("id") or node.get("name")
            ]

            default_zone = (
                tab_id_order[0]
                if tab_id_order
                else "flow_main"
            )

            nodes_by_zone: dict[str, list[JsonObject]] = {}

            for node in flow_nodes:
                zone = str(node.get("z") or default_zone)
                nodes_by_zone.setdefault(zone, []).append(node)

            for tab_node in tab_nodes_ordered:
                tab_id_value = (
                    tab_node.get("id")
                    or tab_node.get("name")
                )

                if tab_id_value is None:
                    continue

                tab_id = str(tab_id_value)

                label = (
                    tab_node.get("label")
                    or tab_node.get("name")
                )

                if isinstance(label, str) and not label.strip():
                    label = None

                disabled_value = tab_node.get("disabled")
                tab_disabled: JsonValue = (
                    bool(disabled_value)
                    if disabled_value is not None
                    else None
                )

                tab_nodes = nodes_by_zone.get(tab_id, [])

                (
                    units,
                    connections,
                    code_blocks,
                ) = _node_red_units_connections_from_nodes(tab_nodes)

                all_code_blocks.extend(code_blocks)

                append_tab(
                    tab_id=tab_id,
                    label=label,
                    disabled=tab_disabled,
                    units=units,
                    connections=connections,
                )

            for zone, zone_nodes in nodes_by_zone.items():
                if zone in tab_id_order:
                    continue

                (
                    units,
                    connections,
                    code_blocks,
                ) = _node_red_units_connections_from_nodes(zone_nodes)

                all_code_blocks.extend(code_blocks)

                append_tab(
                    tab_id=zone,
                    label=None,
                    disabled=None,
                    units=units,
                    connections=connections,
                )

            set_primary_from_first_tab()

        primary_unit_ids = {
            str(unit["id"])
            for unit in primary_units
            if (
                is_json_object(unit)
                and isinstance(unit.get("id"), str)
            )
        }

        for node in flow_nodes:
            node_id_value = node.get("id") or node.get("name")

            if node_id_value is None:
                continue

            node_id = str(node_id_value)

            if node_id not in primary_unit_ids:
                continue

            x = node.get("x")
            y = node.get("y")

            if (
                x is None
                or y is None
                or isinstance(x, bool)
                or isinstance(y, bool)
                or not isinstance(x, (str, int, float))
                or not isinstance(y, (str, int, float))
            ):
                continue

            try:
                layout[node_id] = {
                    "x": float(x),
                    "y": float(y),
                }
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                pass

    result: JsonObject = {
        "environment_type": env_type,
        "units": primary_units,
        "connections": primary_connections,
    }

    if all_code_blocks:
        result["code_blocks"] = all_code_blocks

    if tab_meta_for_origin:
        result["origin"] = {
            "node_red": {
                "tabs": tab_meta_for_origin,
            },
        }

    if tabs_list:
        result["tabs"] = tabs_list

    if layout:
        result["layout"] = layout

    result["comments"] = [
        dict(NODE_RED_SYSTEM_COMMENT),
    ]

    if is_json_object(raw):
        skip_keys = {
            "flow",
            "flows",
            "nodes",
            "environment_type",
            "process_environment_type",
        }

        metadata: JsonObject = {}

        for key, value in raw.items():
            if key in skip_keys or value is None:
                continue

            metadata[key] = copy.deepcopy(value)

        if metadata:
            result["metadata"] = metadata

    return result
