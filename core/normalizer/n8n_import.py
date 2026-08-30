"""
n8n workflow import: map n8n workflow JSON to canonical process graph dict.
"""

from core.normalizer.shared import ensure_list_connections
from core.normalizer.system_comments import N8N_SYSTEM_COMMENT
from core.schemas.primitives import (
    JsonArray,
    JsonObject,
    is_json_array,
    is_json_object,
)

_N8N_STRUCTURE_KEYS = frozenset({"id", "name", "type", "position"})


def _n8n_nodes_list(raw: JsonObject) -> list[JsonObject]:
    """Extract the nodes array from an n8n workflow object."""
    nodes = raw.get("nodes")

    if not is_json_array(nodes):
        return []

    return [node for node in nodes if is_json_object(node)]


def _n8n_connections_to_list(
    raw: JsonObject,
    node_names: set[str],
) -> JsonArray:
    """
    Flatten n8n connections into connection objects.

    n8n connections are keyed by source node name and connection type:

        {
            "SourceName": {
                "main": [
                    [
                        {
                            "node": "TargetName",
                            "type": "main",
                            "index": 0
                        }
                    ]
                ]
            }
        }
    """

    out: JsonArray = []
    conns = raw.get("connections")

    if not is_json_object(conns):
        return out

    for source_name, outputs in conns.items():
        if source_name not in node_names or not is_json_object(outputs):
            continue

        for output_type, indices_list in outputs.items():
            if not is_json_array(indices_list):
                continue

            connection_type = str(output_type) if output_type else None

            for from_port_idx, targets in enumerate(indices_list):
                if not is_json_array(targets):
                    continue

                for target in targets:
                    if not is_json_object(target):
                        continue

                    to_name = target.get("node")
                    to_port = target.get("index", 0)

                    if (
                        not to_name
                        or not isinstance(to_name, (str, int, float, bool))
                        or str(to_name) not in node_names
                        or str(to_name) == source_name
                    ):
                        continue

                    connection: JsonObject = {
                        "from": source_name,
                        "to": str(to_name),
                        "from_port": str(from_port_idx),
                        "to_port": str(to_port),
                    }

                    if connection_type:
                        connection["connection_type"] = connection_type

                    out.append(connection)

    return out


def _n8n_code_source(node: JsonObject) -> str | None:
    """Extract JavaScript source from an n8n Code or Function node."""
    parameters = node.get("parameters")

    if not is_json_object(parameters):
        return None

    source = parameters.get("jsCode") or parameters.get("code")

    if isinstance(source, str) and source.strip():
        return source

    return None


def _n8n_node_params(node: JsonObject) -> JsonObject:
    """Preserve non-structural n8n node fields as unit parameters."""
    params: JsonObject = {}

    for key, value in node.items():
        if key in _N8N_STRUCTURE_KEYS or value is None:
            continue

        params[key] = value

    full_type = node.get("type")
    if isinstance(full_type, str) and full_type.strip():
        params["_n8n_type"] = full_type.strip()

    return params


def _n8n_layout(nodes: list[JsonObject], unit_ids: set[str]) -> JsonObject:
    """Extract n8n node positions into canonical layout objects."""
    layout: JsonObject = {}

    for node in nodes:
        node_id = node.get("name") or node.get("id")
        if node_id is None or str(node_id) not in unit_ids:
            continue

        position = node.get("position")

        if is_json_array(position) and len(position) >= 2:
            x = position[0]
            y = position[1]

            if (
                isinstance(x, (int, float))
                and not isinstance(x, bool)
                and isinstance(y, (int, float))
                and not isinstance(y, bool)
            ):
                layout[str(node_id)] = {
                    "x": float(x),
                    "y": float(y),
                }


        elif is_json_object(position):
            x = position.get("x")
            y = position.get("y")

            if (
                isinstance(x, (int, float))
                and not isinstance(x, bool)
                and isinstance(y, (int, float))
                and not isinstance(y, bool)
            ):
                layout[str(node_id)] = {
                    "x": float(x),
                    "y": float(y),
                }


    return layout


def to_canonical_dict(raw: JsonObject) -> JsonObject:
    """
    Map n8n workflow JSON to a canonical process graph object.

    n8n node names are used as canonical unit IDs so that connection references
    remain stable. JavaScript code is preserved in code_blocks.
    """
    nodes = _n8n_nodes_list(raw)

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
        node_id = node.get("name") or node.get("id")
        if node_id is None:
            continue

        unit_id = str(node_id)
        unit_ids.add(unit_id)

        node_type = node.get("type") or "node"
        node_type_string = str(node_type)

        if "." in node_type_string:
            node_type_string = node_type_string.rsplit(".", 1)[-1]

        controllable_value = node.get("controllable")
        controllable = (
            True
            if controllable_value is None
            else bool(controllable_value)
        )

        unit: JsonObject = {
            "id": unit_id,
            "type": node_type_string,
            "controllable": controllable,
            "params": _n8n_node_params(node),
        }

        node_name = node.get("name")
        if isinstance(node_name, str) and node_name.strip():
            unit["name"] = node_name.strip()

        units.append(unit)

        code_source = _n8n_code_source(node)
        if code_source is not None:
            code_blocks.append(
                {
                    "id": unit_id,
                    "language": "javascript",
                    "source": code_source,
                }
            )

    connections = _n8n_connections_to_list(raw, unit_ids)

    output_types_by_node: dict[str, list[str]] = {}

    for connection in connections:
        if not is_json_object(connection):
            continue

        unit_id = connection.get("from")
        if not isinstance(unit_id, str) or unit_id not in unit_ids:
            continue

        connection_type = connection.get("connection_type") or "main"
        connection_type_string = str(connection_type)

        node_types = output_types_by_node.setdefault(unit_id, [])
        if connection_type_string not in node_types:
            node_types.append(connection_type_string)

    for value in units:
        if not is_json_object(value):
            continue

        unit_id = value.get("id")
        if not isinstance(unit_id, str):
            continue

        output_types = output_types_by_node.get(unit_id)
        if output_types:
            value["output_ports"] = [
                {
                    "name": connection_type,
                    "type": connection_type,
                }
                for connection_type in sorted(output_types)
            ]


    result: JsonObject = {
        "environment_type": environment_type,
        "units": units,
        "connections": ensure_list_connections(connections),
        "origin": {
            "n8n": {},
        },
        "comments": [
            dict(N8N_SYSTEM_COMMENT),
        ],
    }

    if code_blocks:
        result["code_blocks"] = code_blocks

    layout = _n8n_layout(nodes, unit_ids)
    if layout:
        result["layout"] = layout

    return result
