"""
Ryven project import: map Ryven project JSON to canonical process graph dict.
"""

from core.normalizer.shared import ensure_list_connections
from core.normalizer.system_comments import RYVEN_SYSTEM_COMMENT
from core.schemas.primitives import (
    JsonArray,
    JsonObject,
    JsonValue,
    is_json_array,
    is_json_object,
)

_RYVEN_STRUCTURE_KEYS = frozenset(
    {
        "id",
        "name",
        "type",
        "title",
        "identifier",
        "GID",
        "__class__",
        "node_type",
    }
)

_RYVEN_PRESENTATION_KEYS = frozenset(
    {
        "x",
        "y",
        "position",
        "pos",
        "geometry",
        "selected",
        "collapsed",
    }
)


def _first_present(
    value: JsonObject,
    *keys: str,
) -> JsonValue:
    for key in keys:
        candidate = value.get(key)
        if candidate is not None:
            return candidate

    return None


def _string_value(
    value: JsonValue,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value)


def _node_id(node: JsonObject) -> str | None:
    value = _first_present(
        node,
        "id",
        "name",
        "identifier",
        "GID",
    )

    if value is None:
        return None

    return str(value)


def _node_type(node: JsonObject) -> str:
    value = _first_present(
        node,
        "type",
        "title",
        "node_type",
        "identifier",
        "__class__",
    )

    if is_json_object(value):
        value = value.get("name") or "Node"

    return str(value or "Node").split(".")[-1]


def _nodes_from_flow(flow: JsonObject) -> list[JsonObject]:
    nodes = _first_present(
        flow,
        "nodes",
        "node_list",
        "nodes_list",
    )

    if not is_json_array(nodes):
        return []

    return [
        value
        for value in nodes
        if is_json_object(value)
    ]


def _ryven_flow_and_nodes(
    raw: JsonObject,
) -> tuple[JsonObject | None, list[JsonObject]]:
    """Extract the first Ryven flow and its nodes."""

    scripts = raw.get("scripts")

    if is_json_array(scripts) and scripts:
        first_script = scripts[0]

        if is_json_object(first_script):
            flow = first_script.get("flow")

            if is_json_object(flow):
                return flow, _nodes_from_flow(flow)

    flow = raw.get("flow")

    if is_json_object(flow):
        return flow, _nodes_from_flow(flow)

    nodes = _nodes_from_flow(raw)

    return raw, nodes


def _split_endpoint(
    value: JsonValue,
) -> tuple[str, str]:
    text = str(value)
    parts = text.split(":", 1)

    node_id = parts[0]
    port = parts[1] if len(parts) == 2 and parts[1] else "0"

    return node_id, port


def _connection_endpoint(
    connection: JsonObject,
    *keys: str,
) -> JsonValue:
    return _first_present(connection, *keys)


def _ryven_connections_list(
    flow: JsonObject | None,
    node_ids: set[str],
) -> JsonArray:
    if flow is None:
        return []

    connections = _first_present(
        flow,
        "connections",
        "links",
        "edges",
        "wires",
    )

    if not is_json_array(connections):
        return []

    output: JsonArray = []

    for value in connections:
        if not is_json_object(value):
            continue

        from_value = _connection_endpoint(
            value,
            "from",
            "from_node",
            "from_id",
            "source",
        )
        to_value = _connection_endpoint(
            value,
            "to",
            "to_node",
            "to_id",
            "target",
        )

        if from_value is None or to_value is None:
            continue

        from_id, embedded_from_port = _split_endpoint(from_value)
        to_id, embedded_to_port = _split_endpoint(to_value)

        if from_id not in node_ids or to_id not in node_ids:
            continue

        from_port = _first_present(
            value,
            "from_port",
            "from_slot",
            "out_port",
            "out_slot",
        )
        to_port = _first_present(
            value,
            "to_port",
            "to_slot",
            "in_port",
            "in_slot",
        )

        output.append(
            {
                "from": from_id,
                "to": to_id,
                "from_port": (
                    embedded_from_port
                    if from_port is None
                    else str(from_port)
                ),
                "to_port": (
                    embedded_to_port
                    if to_port is None
                    else str(to_port)
                ),
            }
        )

    return output


def _ryven_node_params(node: JsonObject) -> JsonObject:
    params: JsonObject = {}

    for key, value in node.items():
        if value is None:
            continue

        if key in _RYVEN_STRUCTURE_KEYS:
            continue

        if key in _RYVEN_PRESENTATION_KEYS:
            continue

        params[key] = value

    return params


def _as_bool(
    value: JsonValue,
    default: bool = True,
) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"false", "0", "no", "off"}:
            return False

        if normalized in {"true", "1", "yes", "on"}:
            return True

    return bool(value)


def _nested_object(
    value: JsonValue,
) -> JsonObject | None:
    return value if is_json_object(value) else None


def _code_source(
    node: JsonObject,
    params: JsonObject,
) -> tuple[str, str] | None:
    data = _nested_object(node.get("data"))

    source = _first_present(
        node,
        "source",
        "code",
        "script",
    )

    if source is None and data is not None:
        source = _first_present(
            data,
            "source",
            "code",
            "script",
        )

    if source is None:
        source = _first_present(
            params,
            "source",
            "code",
        )

    if not isinstance(source, str) or not source.strip():
        return None

    language = _first_present(node, "language")

    if language is None and data is not None:
        language = data.get("language")

    if language is None:
        language = params.get("language") or "python"

    return str(language), source


def _unique_connections(
    connections: JsonArray,
) -> JsonArray:
    output: JsonArray = []
    seen: set[tuple[str, str, str, str]] = set()

    for value in connections:
        if not is_json_object(value):
            continue

        from_id = value.get("from")
        to_id = value.get("to")

        if not isinstance(from_id, str) or not isinstance(to_id, str):
            continue

        from_port = str(value.get("from_port", "0"))
        to_port = str(value.get("to_port", "0"))

        key = (
            from_id,
            to_id,
            from_port,
            to_port,
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(
            {
                "from": from_id,
                "to": to_id,
                "from_port": from_port,
                "to_port": to_port,
            }
        )

    return output


def to_canonical_dict(raw: JsonObject) -> JsonObject:
    """
    Map a Ryven project JSON object to the canonical process graph format.
    """

    flow, nodes = _ryven_flow_and_nodes(raw)

    environment_value = _first_present(
        raw,
        "environment_type",
        "process_environment_type",
    )
    environment_type = _string_value(environment_value).strip()

    units: JsonArray = []
    code_blocks: JsonArray = []
    unit_ids: set[str] = set()
    accepted_nodes: list[tuple[JsonObject, str]] = []

    for node in nodes:
        node_id = _node_id(node)

        if node_id is None or node_id in unit_ids:
            continue

        unit_ids.add(node_id)
        accepted_nodes.append((node, node_id))

        params = _ryven_node_params(node)

        unit: JsonObject = {
            "id": node_id,
            "type": _node_type(node),
            "controllable": _as_bool(node.get("controllable")),
            "params": params,
        }

        display_name = _first_present(
            node,
            "title",
            "name",
        )

        if isinstance(display_name, str) and display_name.strip():
            unit["name"] = display_name.strip()

        units.append(unit)

        code = _code_source(node, params)

        if code is not None:
            language, source = code
            code_blocks.append(
                {
                    "id": node_id,
                    "language": language,
                    "source": source,
                }
            )

    connections = _unique_connections(
        _ryven_connections_list(flow, unit_ids)
    )

    result: JsonObject = {
        "environment_type": environment_type,
        "units": units,
        "connections": ensure_list_connections(connections),
        "origin": {"ryven": {}},
        "comments": [dict(RYVEN_SYSTEM_COMMENT)],
    }

    if code_blocks:
        result["code_blocks"] = code_blocks

    return result
