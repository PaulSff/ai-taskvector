"""
ComfyUI workflow import: map ComfyUI workflow JSON to canonical process graph dict.
"""

import copy

from core.normalizer.shared import ensure_list_connections
from core.normalizer.system_comments import COMFYUI_SYSTEM_COMMENT
from core.schemas.primitives import (
    JsonArray,
    JsonObject,
    is_json_array,
    is_json_object,
)

# Keys used for graph structure / identity; do not store in unit.params.
_COMFYUI_STRUCTURE_KEYS = frozenset({"id", "type", "pos", "class_type"})


def _comfyui_nodes_list(raw: JsonObject) -> list[JsonObject]:
    """Extract valid node objects from the top-level ``nodes`` array."""
    nodes = raw.get("nodes")

    if not is_json_array(nodes):
        return []

    return [node for node in nodes if is_json_object(node)]


def _comfyui_links_list(raw: JsonObject) -> list[JsonObject]:
    """Extract valid link objects from the top-level ``links`` array."""
    links = raw.get("links")

    if not is_json_array(links):
        return []

    return [link for link in links if is_json_object(link)]


def _comfyui_connections_from_links(
    links: list[JsonObject],
    node_ids: set[str],
) -> JsonArray:
    """
    Build canonical connections from ComfyUI links.

    The ComfyUI link type is preserved as ``connection_type`` when present.
    """
    out: JsonArray = []

    for link in links:
        origin_id = link.get("origin_id")
        target_id = link.get("target_id")

        if origin_id is None or target_id is None:
            continue

        origin_id_string = str(origin_id)
        target_id_string = str(target_id)

        if (
            origin_id_string not in node_ids
            or target_id_string not in node_ids
            or origin_id_string == target_id_string
        ):
            continue

        origin_slot = link.get("origin_slot")
        target_slot = link.get("target_slot")

        connection: JsonObject = {
            "from": origin_id_string,
            "to": target_id_string,
            "from_port": (
                str(origin_slot) if origin_slot is not None else "0"
            ),
            "to_port": str(target_slot) if target_slot is not None else "0",
        }

        link_type = link.get("type")
        if link_type is not None:
            if is_json_array(link_type):
                connection["connection_type"] = ",".join(
                    str(value) for value in link_type
                )
            else:
                connection["connection_type"] = str(link_type)

        out.append(connection)

    return out


def _comfyui_port_type(value: object) -> str | None:
    """Convert a ComfyUI port type to its canonical string representation."""
    if value is None:
        return None

    if isinstance(value, str):
        return value

    if is_json_array(value):
        if not value:
            return None
        return str(value[0])

    return str(value)


def _comfyui_node_params(node: JsonObject) -> JsonObject:
    """
    Preserve non-structural ComfyUI node fields as unit parameters.

    The duplicated ``_comfy_*`` fields are retained for exporter compatibility.
    """
    params: JsonObject = {}

    for key, value in node.items():
        if key in _COMFYUI_STRUCTURE_KEYS or value is None:
            continue

        params[key] = copy.deepcopy(value)

    size = params.get("size")
    if (
        "_comfy_size" not in params
        and is_json_array(size)
        and len(size) >= 2
    ):
        width, height = size[0], size[1]

        if (
            isinstance(width, (int, float, str))
            and not isinstance(width, bool)
            and isinstance(height, (int, float, str))
            and not isinstance(height, bool)
        ):
            try:
                params["_comfy_size"] = [
                    float(width),
                    float(height),
                ]
            except ValueError:
                pass

    flags = params.get("flags")
    if "_comfy_flags" not in params and is_json_object(flags):
        params["_comfy_flags"] = copy.deepcopy(flags)

    order = params.get("order")

    if (
        "_comfy_order" not in params
        and isinstance(order, (str, int, float))
        and not isinstance(order, bool)
    ):
        try:
            params["_comfy_order"] = int(order)
        except ValueError:
            pass

    mode = params.get("mode")

    if (
        "_comfy_mode" not in params
        and isinstance(mode, (str, int, float))
        and not isinstance(mode, bool)
    ):
        try:
            params["_comfy_mode"] = int(mode)
        except ValueError:
            pass

    properties = params.get("properties")
    if (
        "_comfy_properties" not in params
        and is_json_object(properties)
    ):
        params["_comfy_properties"] = copy.deepcopy(properties)

    return params


def _comfyui_position(node: JsonObject) -> tuple[float, float] | None:
    """Extract a valid two-dimensional node position."""
    position = node.get("pos")

    if is_json_array(position) and len(position) >= 2:
        x, y = position[0], position[1]
    elif is_json_object(position):
        x = position.get("0")
        y = position.get("1")
    else:
        return None

    if (
        not isinstance(x, (int, float))
        or isinstance(x, bool)
        or not isinstance(y, (int, float))
        or isinstance(y, bool)
    ):
        return None

    return float(x), float(y)


def _comfyui_layout(
    nodes: list[JsonObject],
    node_ids: set[str],
) -> JsonObject:
    """Extract ComfyUI node positions into canonical layout objects."""
    layout: JsonObject = {}

    for node in nodes:
        node_id = node.get("id")
        if node_id is None or str(node_id) not in node_ids:
            continue

        position = _comfyui_position(node)
        if position is None:
            continue

        x, y = position
        layout[str(node_id)] = {"x": x, "y": y}

    return layout


def _comfyui_controllable(node: JsonObject) -> bool:
    """Normalize the optional controllable flag."""
    value = node.get("controllable")

    if value is None:
        return True

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0

    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no"}

    return bool(value)


def to_canonical_dict(raw: JsonObject) -> JsonObject:
    """
    Map ComfyUI workflow JSON to a canonical process graph object.

    Supports the ComfyUI workflow format containing ``nodes`` and ``links``.
    ComfyUI node IDs are used as canonical unit IDs.
    """
    nodes = _comfyui_nodes_list(raw)
    links = _comfyui_links_list(raw)

    environment_value = (
        raw.get("environment_type")
        or raw.get("process_environment_type")
        or ""
    )
    environment_type = str(environment_value).strip()

    unit_ids: set[str] = set()
    units: JsonArray = []
    code_blocks: JsonArray = []

    for node in nodes:
        node_id = node.get("id")
        if node_id is None:
            continue

        unit_id = str(node_id)
        if unit_id in unit_ids:
            continue

        unit_ids.add(unit_id)

        node_type = node.get("type") or node.get("class_type") or "Node"

        unit: JsonObject = {
            "id": unit_id,
            "type": str(node_type),
            "controllable": _comfyui_controllable(node),
            "params": _comfyui_node_params(node),
        }

        title = node.get("title") or node.get("name")
        if isinstance(title, str) and title.strip():
            unit["name"] = title.strip()

        inputs = node.get("inputs")
        if is_json_array(inputs) and inputs:
            input_ports: JsonArray = []

            for index, value in enumerate(inputs):
                if not is_json_object(value):
                    continue

                input_ports.append(
                    {
                        "name": str(
                            value.get("name", f"input_{index}")
                        ),
                        "type": _comfyui_port_type(value.get("type")),
                    }
                )

            if input_ports:
                unit["input_ports"] = input_ports

        outputs = node.get("outputs")
        if is_json_array(outputs) and outputs:
            output_ports: JsonArray = []

            for index, value in enumerate(outputs):
                if not is_json_object(value):
                    continue

                output_ports.append(
                    {
                        "name": str(
                            value.get("name", f"output_{index}")
                        ),
                        "type": _comfyui_port_type(value.get("type")),
                    }
                )

            if output_ports:
                unit["output_ports"] = output_ports

        units.append(unit)

        parameters = node.get("parameters")
        source = node.get("source") or node.get("code")

        if not isinstance(source, str) and is_json_object(parameters):
            parameter_source = parameters.get("source")
            if isinstance(parameter_source, str):
                source = parameter_source

        if isinstance(source, str) and source.strip():
            language = node.get("language", "python")
            code_blocks.append(
                {
                    "id": unit_id,
                    "language": str(language),
                    "source": source,
                }
            )

    connections = _comfyui_connections_from_links(links, unit_ids)

    result: JsonObject = {
        "environment_type": environment_type,
        "units": units,
        "connections": ensure_list_connections(connections),
        "origin": {
            "comfyui": {},
        },
        "comments": [
            dict(COMFYUI_SYSTEM_COMMENT),
        ],
    }

    if code_blocks:
        result["code_blocks"] = code_blocks

    layout = _comfyui_layout(nodes, unit_ids)
    if layout:
        result["layout"] = layout

    return result
