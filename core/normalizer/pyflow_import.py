"""PyFlow graph import: map PyFlow graph JSON to canonical process graph dict."""

from core.normalizer.shared import ensure_list_connections
from core.normalizer.system_comments import PYFLOW_SYSTEM_COMMENT
from core.schemas.primitives import (
    JsonArray,
    JsonObject,
    JsonValue,
    is_json_array,
    is_json_object,
)

_PYFLOW_STRUCTURE_KEYS = frozenset(
    {"id", "name", "type", "uuid", "nodeType", "__class__"}
)


def _pyflow_nodes_list(raw: JsonObject) -> list[JsonObject]:
    nodes = raw.get("nodes")
    if is_json_array(nodes):
        return [node for node in nodes if is_json_object(node)]

    graphs = raw.get("graphs")
    if is_json_array(graphs) and graphs:
        first_graph = graphs[0]
        if is_json_object(first_graph):
            nodes = first_graph.get("nodes")
            if is_json_array(nodes):
                return [node for node in nodes if is_json_object(node)]

    graph_manager = raw.get("graphManager") or raw.get("graph_manager")
    if is_json_object(graph_manager):
        graphs = graph_manager.get("graphs")
        if is_json_array(graphs) and graphs:
            first_graph = graphs[0]
            if is_json_object(first_graph):
                nodes = first_graph.get("nodes")
                if is_json_array(nodes):
                    return [node for node in nodes if is_json_object(node)]

    return []


def _pyflow_connections_list(
    raw: JsonObject,
    node_ids: set[str],
) -> JsonArray:
    out: JsonArray = []

    connections: JsonValue = (
        raw.get("connections")
        or raw.get("edges")
        or raw.get("wires")
    )

    if not is_json_array(connections):
        graphs = raw.get("graphs")
        if is_json_array(graphs) and graphs:
            first_graph = graphs[0]
            if is_json_object(first_graph):
                connections = (
                    first_graph.get("connections")
                    or first_graph.get("edges")
                    or first_graph.get("wires")
                )

    if not is_json_array(connections):
        return out

    for value in connections:
        if not is_json_object(value):
            continue

        from_value = (
            value.get("from")
            or value.get("from_id")
            or value.get("out")
            or value.get("source")
        )
        to_value = (
            value.get("to")
            or value.get("to_id")
            or value.get("in")
            or value.get("target")
        )

        if from_value is None or to_value is None:
            continue

        from_id = str(from_value).split(":", 1)[0]
        to_id = str(to_value).split(":", 1)[0]

        if from_id not in node_ids or to_id not in node_ids:
            continue

        from_port = (
            value.get("from_port")
            or value.get("from_slot")
            or "0"
        )
        to_port = value.get("to_port") or value.get("to_slot") or "0"

        out.append(
            {
                "from": from_id,
                "to": to_id,
                "from_port": str(from_port),
                "to_port": str(to_port),
            }
        )

    return out


def _pyflow_node_params(node: JsonObject) -> JsonObject:
    return {
        key: value
        for key, value in node.items()
        if key not in _PYFLOW_STRUCTURE_KEYS and value is not None
    }


def _pyflow_position(value: JsonValue) -> tuple[float, float] | None:
    if is_json_array(value) and len(value) >= 2:
        x, y = value[0], value[1]
        if (
            isinstance(x, (int, float))
            and not isinstance(x, bool)
            and isinstance(y, (int, float))
            and not isinstance(y, bool)
        ):
            return float(x), float(y)

    if is_json_object(value):
        x, y = value.get("x"), value.get("y")
        if (
            isinstance(x, (int, float))
            and not isinstance(x, bool)
            and isinstance(y, (int, float))
            and not isinstance(y, bool)
        ):
            return float(x), float(y)

    return None


def to_canonical_dict(raw: JsonObject) -> JsonObject:
    nodes = _pyflow_nodes_list(raw)

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
        node_value = (
            node.get("id")
            or node.get("name")
            or node.get("uuid")
        )
        if node_value is None:
            continue

        node_id = str(node_value)

        node_type_value = (
            node.get("type")
            or node.get("nodeType")
            or node.get("__class__")
            or node.get("name")
            or "Node"
        )

        if is_json_object(node_type_value):
            node_type_value = node_type_value.get("name") or "Node"

        node_type = str(node_type_value).split(".")[-1]
        unit_ids.add(node_id)

        controllable_value = node.get("controllable")
        controllable = (
            True
            if controllable_value is None
            else bool(controllable_value)
        )

        unit: JsonObject = {
            "id": node_id,
            "type": node_type,
            "controllable": controllable,
            "params": _pyflow_node_params(node),
        }

        display_name = node.get("name") or node.get("title")
        if isinstance(display_name, str) and display_name.strip():
            unit["name"] = display_name.strip()

        units.append(unit)

        source = (
            node.get("code")
            or node.get("script")
            or node.get("source")
            or node.get("expression")
        )

        if isinstance(source, str) and source.strip():
            language = node.get("language", "python")
            code_blocks.append(
                {
                    "id": node_id,
                    "language": str(language),
                    "source": source,
                }
            )

    connections = _pyflow_connections_list(raw, unit_ids)

    if not connections and nodes:
        for node in nodes:
            from_value = node.get("id") or node.get("name")
            if from_value is None:
                continue

            from_id = str(from_value)
            if from_id not in unit_ids:
                continue

            pins = node.get("pins")
            if not is_json_array(pins):
                continue

            for output_index, pin_value in enumerate(pins):
                if not is_json_object(pin_value):
                    continue

                links = (
                    pin_value.get("connections")
                    or pin_value.get("links")
                    or pin_value.get("wires")
                )
                if not is_json_array(links):
                    continue

                for link in links:
                    if isinstance(link, str):
                        to_value: JsonValue = link
                        to_port = "0"
                    elif is_json_object(link):
                        to_value = (
                            link.get("to")
                            or link.get("node")
                            or link.get("target")
                        )
                        to_port = str(
                            link.get("index")
                            or link.get("to_slot")
                            or "0"
                        )
                    else:
                        continue

                    if to_value is None:
                        continue

                    to_id = str(to_value).split(":", 1)[0]
                    if to_id not in unit_ids or to_id == from_id:
                        continue

                    connections.append(
                        {
                            "from": from_id,
                            "to": to_id,
                            "from_port": str(output_index),
                            "to_port": to_port,
                        }
                    )

    unique_connections: JsonArray = []
    seen: set[tuple[str, str]] = set()

    for value in connections:
        if not is_json_object(value):
            continue

        from_id = value.get("from")
        to_id = value.get("to")

        if not isinstance(from_id, str) or not isinstance(to_id, str):
            continue

        key = (from_id, to_id)
        if key not in seen:
            seen.add(key)
            unique_connections.append(value)

    result: JsonObject = {
        "environment_type": environment_type,
        "units": units,
        "connections": ensure_list_connections(unique_connections),
        "origin": {"pyflow": {}},
        "comments": [dict(PYFLOW_SYSTEM_COMMENT)],
    }

    if code_blocks:
        result["code_blocks"] = code_blocks

    layout: JsonObject = {}

    for node in nodes:
        node_value = (
            node.get("id")
            or node.get("name")
            or node.get("uuid")
        )
        if node_value is None:
            continue

        node_id = str(node_value)
        if node_id not in unit_ids:
            continue

        x = node.get("x")
        y = node.get("y")

        if (
            isinstance(x, (int, float))
            and not isinstance(x, bool)
            and isinstance(y, (int, float))
            and not isinstance(y, bool)
        ):
            layout[node_id] = {
                "x": float(x),
                "y": float(y),
            }
            continue

        position = node.get("position") or node.get("pos")
        coordinates = _pyflow_position(position)

        if coordinates is not None:
            layout[node_id] = {
                "x": coordinates[0],
                "y": coordinates[1],
            }

    if layout:
        result["layout"] = layout

    return result
